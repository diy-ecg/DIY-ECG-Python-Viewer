# ECG CODEX Python Viewer — Data Structures and Functions

## Architecture Overview
- **Arduino**: Samples A0 at 5 ms, serves frames on `'R'`.
- **serial_port.py**: Opens serial, requests frames, CRC-16/IBM validation, unpacks samples/timestamps.
- **data_stream.py**: Holds samples/timestamps in a NumPy ring buffer, applies IIR filters, adaptive mean, R-peak/BPM detection.
- **diy-ecg-Viewer-V1.py**: Qt/pyqtgraph GUI with live plot, filter toggles, threshold line, BPM/polarity, CPU meter, save/export, pause/resume.

## Data Structures
- **Frame format (Arduino → PC)**: `[uint8 count][count * uint16 samples][count * uint32 t_ms][uint16 crc16]` (little-endian, CRC-16/IBM poly 0xA001 init 0x0000, low byte first).
- **DataStream ring buffer** (`data_stream.py`):
  - `samples: np.ndarray`, `timestamps: np.ndarray` of fixed length (`length`), circular write via `write_idx`, `filled`.
  - Filter flags: `hp_enabled`, `no_enabled`, `tp_enabled`, `am_enabled`.
  - IIR states: `(hp_b, hp_a, hp_z)`, `(tp_b, tp_a, tp_z)`, `(no_b, no_a, no_z)`.
  - Adaptive mean / R-peak state: `buffer`, `buffer_index`, `sum_val`, `filter_disable`, `inhibit_counter`, `max_buffer`, `max_index`, `peak_polarity`, `last_r_peak_time`, `prev_r_peak_time`, `BPM`, `newBPM`, `dynamic_threshold`, `last_bpm`.

## Key Functions and Methods
- **serial_port.py**
  - `crc16_ibm(data)`: CRC-16/IBM over bytes.
  - `SerialPort.open_first()`: Scan ports (reverse order), probe device by requesting a frame.
  - `_probe()`: Wait for Arduino reboot, try up to 3 requests, ensure valid frame.
  - `request_frame()`: Send `'R'`, read count/payload, CRC-check, unpack to Python lists.
  - `open_serial()`: Convenience wrapper; prints scan status, returns connected `SerialPort`.

- **data_stream.py**
  - `DataStream.add_samples(samples, timestamps)`: Apply Notch → Lowpass → Highpass (if enabled), adaptive mean (if enabled), append to ring buffer.
  - `_process_adaptive_mean(sample, timestamp)`: Dynamic thresholding with polarity detection, refractory window, BPM computation, adaptive mean filter update.
  - `set_filter_enabled(...)`: Toggle HP/Notch/TP/AM flags.
  - `last(n)`: Return last `n` samples/timestamps (handles wrap).
  - `consume_new_bpm()`: Return `(BPM, polarity)` once per detected beat; clears `newBPM`.
  - `clear()`: Reset buffers and detection state.

- **main.py**
  - `main()`: Open serial, poll frames every `PORT_INTERVAL`, feed `DataStream`, print `count` and last timestamp, graceful `Ctrl+C` exit.

- **main_pyqt.py**
  - UI elements: `PlotWidget` with `curve` (signal) and `thr_curve` (threshold); checkboxes (HP/Notch/TP/AM/THR); play/pause button; status/BPM/CPU labels; menu (Datei: Save, Info: About).
  - Timers: `poll_timer` (serial request), `plot_timer` (redraw), `cpu_timer` (psutil CPU %).
  - Slots:
    - `poll_serial()`: Request frame, feed `DataStream`, update count status.
    - `update_plot()`: Fetch last window, set plot data, scroll x-range, draw threshold, update BPM/polarity label.
    - `update_cpu()`: Refresh CPU label.
    - `on_filters_changed()`: Apply checkbox states to `DataStream`.
    - `on_thr_changed()`: Show/hide threshold line.
    - `on_toggle_run()`: Pause/resume polling, clear buffers/plot on pause.
    - `on_save()`: Save full buffer to CSV (timestamp_ms, sample).
    - `on_about()`: Show info dialog.
  - Menu: `Datei` → Save; `Info` → About (native menubar disabled to show inside window on macOS).

## Control Flow
1) `diy-ecg-Viewer-V1.py` starts Qt app, builds UI, opens serial via `open_serial()`.
2) `poll_timer` fires: sends `'R'`, gets frame, pushes into `DataStream`.
3) `plot_timer` fires: grabs last `PLOT_WINDOW` samples, updates pyqtgraph curves, scrolls x-axis, updates BPM/polarity if new beat detected.
4) Filters/threshold toggles change `DataStream` behavior; pause clears buffers and halts polling until resumed.
5) Save action exports current buffer; About shows app info; CPU timer updates load.
