"""
Core data stream logic: ring buffer, filtering, adaptive mean, and R-peak/BPM detection.
Mirrors the Octave dataStreamClass.m behavior, but implemented with NumPy/SciPy.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
from scipy import signal


class DataStream:
    def __init__(self, name: str = "EKG", length: int = 2000, fs: float = 200.0) -> None:
        self.name = name
        self.length = length
        self.fs = fs
        # NumPy ring buffer (circular overwrite) for samples/timestamps
        self.samples = np.zeros(self.length, dtype=float)
        self.timestamps = np.zeros(self.length, dtype=float)
        self.write_idx = 0
        self.filled = 0

        # Filter enable flags
        self.hp_enabled = True
        self.no_enabled = True
        self.tp_enabled = True
        self.am_enabled = True

        # IIR filter coeffs/states
        self.hp_b, self.hp_a, self.hp_z = self._design_highpass()
        self.no_b, self.no_a, self.no_z = self._design_notch()
        self.tp_b, self.tp_a, self.tp_z = self._design_lowpass()

        # Adaptive mean / R-peak detection state
        self.window_size = int(round(0.2 * self.fs))
        self.inhibit_time = int(round(0.05 * self.fs))
        self.max_window_size = int(round(2 * self.fs))
        self.buffer = np.zeros(self.window_size, dtype=float)
        self.buffer_index = 0
        self.sum_val = 0.0
        self.filter_disable = False
        self.inhibit_counter = 0
        self.max_buffer = np.zeros(self.max_window_size, dtype=float)
        self.max_index = 0
        self.peak_polarity = 1
        self.last_r_polarity = 1
        self.last_r_peak_time = 0.0
        self.prev_r_peak_time = 0.0
        self.BPM = 0
        self.newBPM = False
        self.dynamic_threshold: float | None = None
        self.last_bpm = 0

    def _design_highpass(self):
        # 2nd-order Butter highpass at 2 Hz (tuned for 200 Hz sampling)
        b, a = signal.butter(2, 2.0 / (self.fs / 2.0), btype="high")
        z = signal.lfilter_zi(b, a) * 0.0
        return b, a, z

    def _design_lowpass(self):
        # 2nd-order Butter lowpass at 40 Hz (tuned for 200 Hz sampling)
        b, a = signal.butter(2, 40.0 / (self.fs / 2.0), btype="low")
        z = signal.lfilter_zi(b, a) * 0.0
        return b, a, z

    def _design_notch(self):
        # 50 Hz notch (Q=30) for mains interference
        w0 = 50.0 / (self.fs / 2.0)
        b, a = signal.iirnotch(w0=w0, Q=30.0)
        z = signal.lfilter_zi(b, a) * 0.0
        return b, a, z

    def set_filter_enabled(self, hp: bool | None = None, no: bool | None = None,
                           tp: bool | None = None, am: bool | None = None) -> None:
        if hp is not None:
            self.hp_enabled = hp
        if no is not None:
            self.no_enabled = no
        if tp is not None:
            self.tp_enabled = tp
        if am is not None:
            self.am_enabled = am

    def add_samples(self, samples: List[int], timestamps: List[int]) -> None:
        """Append samples/timestamps to the ring buffer with optional filtering and BPM detection."""
        if not samples:
            return
        x = np.asarray(samples, dtype=float)
        t_arr = np.asarray(timestamps, dtype=float)

        # Notch -> Lowpass -> Highpass (same order as Octave)
        if self.no_enabled:
            x, self.no_z = signal.lfilter(self.no_b, self.no_a, x, zi=self.no_z)
        if self.tp_enabled:
            x, self.tp_z = signal.lfilter(self.tp_b, self.tp_a, x, zi=self.tp_z)
        if self.hp_enabled:
            x, self.hp_z = signal.lfilter(self.hp_b, self.hp_a, x, zi=self.hp_z)

        x[np.abs(x) < 0.001] = 0.0

        for s_val, t_val in zip(x, t_arr):
            # Adaptive mean and R-peak detection per sample
            y = self._process_adaptive_mean(s_val, t_val) if self.am_enabled else s_val
            self._append_sample(float(y), float(t_val))

    def _append_sample(self, sample: float, timestamp: float) -> None:
        """Write one sample into the circular buffer."""
        self.samples[self.write_idx] = sample
        self.timestamps[self.write_idx] = timestamp
        self.write_idx = (self.write_idx + 1) % self.length
        if self.filled < self.length:
            self.filled += 1

    def _process_adaptive_mean(self, sample: float, timestamp: float) -> float:
        # Update dynamic threshold based on last 2 seconds
        self.max_buffer[self.max_index] = sample
        self.max_index = (self.max_index + 1) % self.max_window_size

        local_max = self.max_buffer.max()
        local_min = self.max_buffer.min()
        local_mean = self.max_buffer.mean()
        dist_max = local_max - local_mean
        dist_min = local_mean - local_min

        if dist_max >= dist_min:
            self.peak_polarity = 1
            self.dynamic_threshold = local_mean + 0.5 * dist_max
            is_r_candidate = sample > self.dynamic_threshold
        else:
            self.peak_polarity = -1
            self.dynamic_threshold = local_mean - 0.5 * dist_min
            is_r_candidate = sample < self.dynamic_threshold

        if is_r_candidate and (timestamp - self.last_r_peak_time) > 250.0:
            self.prev_r_peak_time = self.last_r_peak_time
            self.last_r_peak_time = timestamp
            if self.prev_r_peak_time > 0:
                rr_interval = self.last_r_peak_time - self.prev_r_peak_time
                if rr_interval > 0:
                    self.BPM = int(round(60000.0 / rr_interval))
                    self.newBPM = True
                    self.last_r_polarity = self.peak_polarity
            self.filter_disable = True
            self.inhibit_counter = self.inhibit_time

        if self.filter_disable and self.inhibit_counter > 0:
            self.inhibit_counter -= 1
        else:
            self.filter_disable = False

        if self.filter_disable:
            return sample

        # Adaptive mean filter
        self.sum_val = self.sum_val - self.buffer[self.buffer_index] + sample
        self.buffer[self.buffer_index] = sample
        out = self.sum_val / self.window_size
        self.buffer_index = (self.buffer_index + 1) % self.window_size
        return out

    def consume_new_bpm(self) -> tuple[int, int] | None:
        """Return (BPM, polarity) if a new beat was detected since last call."""
        if self.newBPM:
            self.newBPM = False
            self.last_bpm = self.BPM
            return self.BPM, self.last_r_polarity
        return None

    def last(self, n: int) -> Tuple[np.ndarray, np.ndarray]:
        """Return last n samples/timestamps as numpy arrays."""
        if n <= 0 or self.filled == 0:
            return np.array([]), np.array([])
        n = min(n, self.filled)
        start = (self.write_idx - n) % self.length
        end = self.write_idx
        if start < end:
            return self.samples[start:end].copy(), self.timestamps[start:end].copy()
        return (
            np.concatenate((self.samples[start:], self.samples[:end])),
            np.concatenate((self.timestamps[start:], self.timestamps[:end])),
        )

    def __len__(self) -> int:
        return self.filled
