# santecpro

Cross-platform Python driver for the **Santec TSL-550** tunable laser and **MPM-210** optical power meter, with a scanning/sweep workflow, CSV export, real-time plotting, and an optional PyQt5 UI.

## Features

- **Instrument drivers** — TSL-550 laser and MPM-210 power meter over VISA (`santecpro/instruments/`)
- **Scanner** — wavelength sweep orchestration and triggering (`santecpro/scanner.py`)
- **Export & plotting** — CSV export (`santecpro/exporter.py`) and real-time plots (`santecpro/plotter.py`)
- **Remote control** — drive a Windows-hosted instrument bench over HTTP (`santecpro/remote.py`, `windows_server/`)
- **UI** — optional PyQt5 desktop app (`santecpro/ui_app.py`)

## Installation

```bash
pip install -e .
# or
pip install -r requirements.txt
```

Requires Python 3.10+.

## Usage

See [`examples/basic_scan.py`](examples/basic_scan.py) for a minimal scan, and other scripts under `examples/`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
