# Qt Signals and Slots Overview

This document lists the Qt signals and the slots they are connected to in `main_pyqt.py`.

## Timers
- `poll_timer.timeout` → `MainWindow.poll_serial`
- `plot_timer.timeout` → `MainWindow.update_plot`
- `cpu_timer.timeout` → `MainWindow.update_cpu`

## Controls (checkboxes)
- `cb_hp.toggled` → `MainWindow.on_filters_changed`
- `cb_no.toggled` → `MainWindow.on_filters_changed`
- `cb_tp.toggled` → `MainWindow.on_filters_changed`
- `cb_am.toggled` → `MainWindow.on_filters_changed`
- `cb_thr.toggled` → `MainWindow.on_thr_changed`

## Buttons
- `toggle_btn.clicked` (Play/Pause) → `MainWindow.on_toggle_run`

## Menu actions
- `QAction("Save").triggered` → `MainWindow.on_save`
- `QAction("About").triggered` → `MainWindow.on_about`

## Slots and purpose
- `poll_serial`: request a frame from serial, feed data into `DataStream`.
- `update_plot`: redraw waveform and threshold line, update BPM/Polarity label.
- `update_cpu`: refresh CPU load label.
- `on_filters_changed`: enable/disable HP/Notch/TP/AM filters in `DataStream`.
- `on_thr_changed`: show/hide threshold line.
- `on_toggle_run`: pause/resume polling and clear buffers on pause.
- `on_save`: export buffered samples/timestamps to CSV.
- `on_about`: show app info dialog.
