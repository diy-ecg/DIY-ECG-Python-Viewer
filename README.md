# ECG Data Streamer (Arduino + Python)

This repo streams ECG samples from an Arduino and visualizes them with a Python/Qt viewer.

## Arduino firmware
- Sketch: `ECG_Arduino_Request_Frame/ECG_Arduino_Request_Frame.ino`
- Upload at 115200 baud. It samples A0 every 5 ms (~200 Hz) into a ring buffer and, on receiving `'R'`, sends a binary frame with all unsent samples plus timestamps.
- Frame layout (little-endian): `[uint8 count][count * uint16 sample][count * uint32 t_ms][uint16 crc16]` (CRC-16/IBM, low byte first). Effective buffer depth is `RING_SIZE - 1`.

## Python viewer (PySide6 + pyqtgraph)
- Requirements: Python 3.11, `pip install -r requirements.txt` (PySide6, pyqtgraph, pyserial, numpy, scipy, psutil).
- Create/activate venv (optional but recommended):
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate  # or .venv\Scripts\activate on Windows
  pip install -r requirements.txt
  ```
- Run the GUI:
  ```bash
  python main_pyqt.py
  ```
  - Auto-scans serial ports, requests frames every ~50 ms, plots last 800 samples with OpenGL acceleration.
  - UI: checkboxes for HP/Notch/TP/Adaptive mean, optional threshold line, BPM + polarity display, CPU load.
- Minimal console loop (no GUI): `python main.py`

## Installation on any OS (ZIP or clone)
1) Install Python 3.11+ if missing (from https://python.org). On Windows, ensure “Add Python to PATH” is checked.
2) Get the code:
   - Git: `git clone https://github.com/<your-user>/ECG_CODEX.git` (replace with your fork).
   - Or download ZIP from GitHub (“Code” → “Download ZIP”) and extract.
3) Open a terminal in the project folder.
4) (Recommended) Create a virtual env and install deps:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
5) Connect the Arduino (flashed with the provided sketch) via USB.
6) Start the viewer: `python main_pyqt.py` (or `python main.py` for CLI test).

## Notes
- Filters are tuned for ~200 Hz sampling. If you change the Arduino sampling interval, retune the filter cutoffs accordingly.
- The protocol is binary request/response; ensure no other serial monitor is open to avoid CRC errors.
