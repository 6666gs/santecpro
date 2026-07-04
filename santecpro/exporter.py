"""CSV export for scan and insertion-loss data."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from santecpro.scanner import ScanResult, ILMeasurement


def _parse_idn(idn: str) -> dict:
    """Parse a ``*IDN?`` response string into its components.

    Args:
        idn: Response like ``"SANTEC,TSL-550,12345,1.00"``.

    Returns:
        Dictionary with keys ``vendor``, ``model``, ``serial``, ``firmware``.
    """
    parts = idn.split(",")
    return {
        "vendor": parts[0] if len(parts) > 0 else "",
        "model": parts[1] if len(parts) > 1 else "",
        "serial": parts[2] if len(parts) > 2 else "",
        "firmware": parts[3] if len(parts) > 3 else "",
    }


def _write_header(writer, tsl_idn: str, mpm_idn: str, params: dict, timestamp: str):
    """Write the 14-line metadata header common to both CSV formats.

    Args:
        writer: A ``csv.writer`` instance.
        tsl_idn: ``*IDN?`` response from the TSL.
        mpm_idn: ``*IDN?`` response from the MPM.
        params: Scan parameters dictionary.
        timestamp: ISO-8601 timestamp string.
    """
    from santecpro import __version__

    # Parse timestamp into date and time parts
    if "T" in timestamp:
        date_part, time_part = timestamp.split("T", 1)
    else:
        date_part, time_part = timestamp, ""

    tsl = _parse_idn(tsl_idn)
    mpm = _parse_idn(mpm_idn)

    start_wl = params.get("start_wl", 0.0)
    stop_wl = params.get("stop_wl", 0.0)
    step = params.get("step", 0.0)
    speed = params.get("speed", 0.0)
    power = params.get("power", 0.0)
    sweep_mode = params.get("sweep_mode", "")

    # line 1
    writer.writerow([date_part, time_part, "", ""])
    # line 2
    writer.writerow(["Software", "santecpro", f"Ver.{__version__}", "", ""])
    # line 3
    writer.writerow(["TSL", tsl["vendor"], tsl["model"], tsl["serial"], tsl["firmware"], "", "", ""])
    # line 4
    writer.writerow(["PowerMeter", mpm["vendor"], mpm["model"], mpm["serial"], mpm["firmware"], "", "", ""])
    # line 5
    writer.writerow(["", "Module1", "MPM-211", "", "", ""])
    # line 6 (blank)
    writer.writerow([])
    # line 7
    writer.writerow(["Start", f"{start_wl:.6f}", "nm", ""])
    # line 8
    writer.writerow(["Stop", f"{stop_wl:.6f}", "nm", ""])
    # line 9
    writer.writerow(["Step", f"{step:.6f}", "nm", ""])
    # line 10
    writer.writerow(["Speed", f"{speed:.6f}", "nm/s", ""])
    # line 11
    writer.writerow(["Source power", f"{power:.6f}", "dBm", ""])
    # line 12
    writer.writerow(["Averaging Time", "", "s", ""])
    # line 13
    writer.writerow(["Power meter range", "", "dBm", ""])
    # line 14
    writer.writerow(["Sweep mode", sweep_mode, "", ""])


def save_raw_csv(
    scan: "ScanResult",
    tsl_idn: str,
    mpm_idn: str,
    filepath: str,
) -> None:
    """Save raw scan data to a CSV file.

    The file contains a 14-line metadata header followed by data columns:
    ``Wavelength(nm),Monitor(dBm),M1-Ch1(dBm),,``

    Args:
        scan: The ``ScanResult`` to export.
        tsl_idn: ``*IDN?`` response from the TSL.
        mpm_idn: ``*IDN?`` response from the MPM.
        filepath: Destination file path.
    """
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        _write_header(writer, tsl_idn, mpm_idn, scan.scan_params, scan.timestamp)

        # Data header
        writer.writerow(["Wavelength(nm)", "Monitor(dBm)", "M1-Ch1(dBm)", "", ""])

        # Data rows
        for wl, mon, pwr in zip(scan.wavelengths, scan.monitor_powers, scan.powers):
            writer.writerow([f"{wl:.6f}", f"{mon:.6f}", f"{pwr:.6f}", "", ""])


def save_loss_csv(
    il_measurement: "ILMeasurement",
    tsl_idn: str,
    mpm_idn: str,
    filepath: str,
) -> None:
    """Save insertion-loss data to a CSV file.

    The file contains a 14-line metadata header followed by data columns:
    ``Wavelength(nm),IL_M1_CH1,,,``

    Args:
        il_measurement: The ``ILMeasurement`` to export.
        tsl_idn: ``*IDN?`` response from the TSL.
        mpm_idn: ``*IDN?`` response from the MPM.
        filepath: Destination file path.
    """
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Use the reference scan's params and timestamp for the header
        params = il_measurement.reference.scan_params
        timestamp = il_measurement.reference.timestamp
        _write_header(writer, tsl_idn, mpm_idn, params, timestamp)

        # Data header
        writer.writerow(["Wavelength(nm)", "IL_M1_CH1", "", "", ""])

        # Data rows
        for wl, il in zip(il_measurement.wavelengths, il_measurement.il):
            writer.writerow([f"{wl:.6f}", f"{il:.6f}", "", "", ""])
