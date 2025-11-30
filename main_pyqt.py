"""
Qt/pyqtgraph live viewer for the ECG Arduino stream.

Dependencies: PySide6, pyqtgraph, pyserial, numpy (and scipy later for filters).
"""
from __future__ import annotations

import sys
from typing import Optional

import numpy as np
from PySide6 import QtCore, QtWidgets, QtGui
import pyqtgraph as pg
import psutil

# Enable OpenGL acceleration if available
pg.setConfigOptions(useOpenGL=True)

from data_stream import DataStream
from serial_port import SerialPort, open_serial

# Set a light theme for the plot
pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")

PORT_INTERVAL_MS = 20    # matches Octave's Port_Time
PLOT_INTERVAL_MS = 30
PLOT_WINDOW = 800        # number of samples to display


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DIY-ECG (Python)")

        self.stream = DataStream(name="EKG", length=2000)
        self.sp: Optional[SerialPort] = None
        self.t0: Optional[float] = None  # first timestamp seen
        self.proc = psutil.Process()
        self.proc.cpu_percent(interval=None)  # prime CPU measurement baseline

        # UI setup
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        self.plot = pg.PlotWidget(title="EKG")
        self.plot.showGrid(x=True, y=True, alpha=0.3)  # add grid for readability
        self.curve = self.plot.plot(pen=pg.mkPen(color="r", width=2))
        self.thr_curve = self.plot.plot(pen=pg.mkPen(color="b", style=QtCore.Qt.DashLine))
        layout.addWidget(self.plot)

        # Controls
        ctrl_layout = QtWidgets.QHBoxLayout()
        self.cb_hp = QtWidgets.QCheckBox("HP"); self.cb_hp.setChecked(True)
        self.cb_no = QtWidgets.QCheckBox("Notch"); self.cb_no.setChecked(True)
        self.cb_tp = QtWidgets.QCheckBox("TP"); self.cb_tp.setChecked(True)
        self.cb_am = QtWidgets.QCheckBox("AM"); self.cb_am.setChecked(True)
        self.cb_thr = QtWidgets.QCheckBox("THR"); self.cb_thr.setChecked(False)
        # Pause button (starts in running state, so icon shows action to pause)
        self.toggle_btn = QtWidgets.QPushButton("⏸")
        for cb in (self.cb_hp, self.cb_no, self.cb_tp, self.cb_am, self.cb_thr):
            ctrl_layout.addWidget(cb)
        ctrl_layout.addWidget(self.toggle_btn)
        ctrl_layout.addStretch(1)
        layout.addLayout(ctrl_layout)

        self.status_label = QtWidgets.QLabel("Not connected")
        self.bpm_label = QtWidgets.QLabel("BPM: -  Polarity: -")
        self.cpu_label = QtWidgets.QLabel("CPU: - %")
        layout.addWidget(self.status_label)
        layout.addWidget(self.bpm_label)
        layout.addWidget(self.cpu_label)

        # Timers
        self.poll_timer = QtCore.QTimer(self, interval=PORT_INTERVAL_MS)
        # poll_timer is connected to poll_serial
        self.poll_timer.timeout.connect(self.poll_serial)

        self.plot_timer = QtCore.QTimer(self, interval=PLOT_INTERVAL_MS)
        #plot_timer is connected to update_plot
        self.plot_timer.timeout.connect(self.update_plot)

        self.cpu_timer = QtCore.QTimer(self, interval=2000)
        self.cpu_timer.timeout.connect(self.update_cpu)

        # Try to open serial
        self.try_open_serial()

        # Connect toggles
        self.cb_hp.toggled.connect(self.on_filters_changed)
        self.cb_no.toggled.connect(self.on_filters_changed)
        self.cb_tp.toggled.connect(self.on_filters_changed)
        self.cb_am.toggled.connect(self.on_filters_changed)
        self.cb_thr.toggled.connect(self.on_thr_changed)
        self.toggle_btn.clicked.connect(self.on_toggle_run)

        self.paused = False
        self._build_menu()

    def try_open_serial(self) -> None:
        try:
            self.sp = open_serial()
            self.status_label.setText("Connected")
            self.poll_timer.start()
            self.plot_timer.start()
            self.cpu_timer.start()
        except Exception as exc:
            self.status_label.setText(f"Not connected: {exc}")
            self.sp = None

    @QtCore.Slot()
    def poll_serial(self) -> None:
        if self.sp is None:
            return
        samples, timestamps = self.sp.request_frame()
        if samples:
            if self.t0 is None:
                self.t0 = float(timestamps[0])
            self.stream.add_samples(samples, timestamps)
            self.status_label.setText(f"count={len(samples)}")

    @QtCore.Slot()
    def update_plot(self) -> None:
        if len(self.stream) == 0:
            return
        if self.t0 is None:
            return
        y, t = self.stream.last(PLOT_WINDOW)
        if len(y) == 0:
            return
        # Use relative timestamps from first sample to keep the axis moving
        t_rel = t - self.t0
        # This is the update of the plotgraph
        self.curve.setData(t_rel, y)
        # Keep the view window scrolled to the latest data
        span = t_rel[-1] - t_rel[0]
        self.plot.setXRange(t_rel[-1] - span, t_rel[-1], padding=0)
        if self.cb_thr.isChecked() and self.stream.dynamic_threshold is not None:
            thr = self.stream.dynamic_threshold
            self.thr_curve.setData([t_rel[0], t_rel[-1]], [thr, thr])
        else:
            self.thr_curve.setData([], [])

        bpm_data = self.stream.consume_new_bpm()
        if bpm_data is not None:
            bpm, polarity = bpm_data
            self.bpm_label.setText(f"BPM: {bpm}  Polarity: {polarity}")

    @QtCore.Slot()
    def on_filters_changed(self) -> None:
        self.stream.set_filter_enabled(
            hp=self.cb_hp.isChecked(),
            no=self.cb_no.isChecked(),
            tp=self.cb_tp.isChecked(),
            am=self.cb_am.isChecked(),
        )

    @QtCore.Slot()
    def on_thr_changed(self, checked: bool) -> None:
        if not checked:
            self.thr_curve.setData([], [])

    @QtCore.Slot()
    def update_cpu(self) -> None:
        cpu = self.proc.cpu_percent(interval=None)
        self.cpu_label.setText(f"CPU: {cpu:.1f}%")

    @QtCore.Slot()
    def on_toggle_run(self) -> None:
        """Pause/resume polling; button toggles between play/pause symbols."""
        if self.paused:
            self.poll_timer.start()
            self.paused = False
            self.toggle_btn.setText("⏸")
            self.status_label.setText("Connected")
        else:
            self.poll_timer.stop()
            self.paused = True
            self.toggle_btn.setText("▶")
            self.status_label.setText("Paused")

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        # On macOS the menu is native (top bar); disable if you want it inside the window.
        menubar.setNativeMenuBar(False)
        file_menu = menubar.addMenu("Datei")
        info_menu = menubar.addMenu("Info")

        save_action = QtGui.QAction("Save", self)
        save_action.triggered.connect(self.on_save)
        file_menu.addAction(save_action)

        about_action = QtGui.QAction("About", self)
        about_action.triggered.connect(self.on_about)
        info_menu.addAction(about_action)

    @QtCore.Slot()
    def on_save(self) -> None:
        if len(self.stream) == 0:
            QtWidgets.QMessageBox.information(self, "Save", "No data to save.")
            return
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not fname:
            return
        y, t = self.stream.last(len(self.stream))
        data = np.column_stack((t, y))
        try:
            np.savetxt(fname, data, delimiter=",", header="timestamp_ms,sample", comments="")
            QtWidgets.QMessageBox.information(self, "Save", f"Saved {len(y)} samples to {fname}.")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Save error", f"Could not save file:\n{exc}")

    @QtCore.Slot()
    def on_about(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "About",
            "DIY-ECG Python Viewer\nArduino binary stream @115200 baud\nPySide6 + pyqtgraph",
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.sp is not None:
            self.sp.close()
        event.accept()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.resize(800, 600)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
