"""CSV export for scan and insertion-loss data."""

from __future__ import annotations

import csv
from datetime import datetime

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from santecpro.results import ScanResult, ILMeasurement


def _parse_idn(idn: str) -> dict:
    """Parse a ``*IDN?`` response string into its components.

    Args:
        idn: Response like ``"SANTEC,TSL-550,12345,1.00"``.

    Returns:
        Dictionary with keys ``vendor``, ``model``, ``serial``, ``firmware``.
    """
    parts = [part.strip() for part in idn.split(",")]
    return {
        "vendor": parts[0] if len(parts) > 0 else "",
        "model": parts[1] if len(parts) > 1 else "",
        "serial": parts[2] if len(parts) > 2 else "",
        "firmware": parts[3] if len(parts) > 3 else "",
    }


def _write_header(writer, tsl_idn: str, mpm_idn: str, params: dict, timestamp: str, *, mpm_range: int):
    """Write the 14-line metadata header common to both CSV formats.

    Args:
        writer: A ``csv.writer`` instance.
        tsl_idn: ``*IDN?`` response from the TSL.
        mpm_idn: ``*IDN?`` response from the MPM.
        params: Scan parameters dictionary.
        timestamp: ISO-8601 timestamp string.
        mpm_range: MPM range index stored with this scan (not a dBm value).
    """
    from santecpro import __version__

    try:
        stamp = datetime.fromisoformat(timestamp)
        date_part = f"{stamp.year}/{stamp.month}/{stamp.day}"
        time_part = stamp.strftime("%H:%M:%S")
    except ValueError:
        date_part, time_part = timestamp, ""
    tsl, mpm = _parse_idn(tsl_idn), _parse_idn(mpm_idn)
    module = int(params.get("mpm_module", 0)) + 1
    rows = [
        [date_part, time_part, "", "", ""],
        ["Software", "santecpro", f"Ver.{__version__}", "", ""],
        ["TSL", tsl["vendor"], tsl["model"], tsl["serial"], tsl["firmware"], "", "", ""],
        ["PowerMeter", mpm["vendor"], mpm["model"], mpm["serial"], mpm["firmware"], "", "", ""],
        [" ", f"Module{module}", params.get("module_model", ""), params.get("module_serial", ""), params.get("module_info", "")],
        ["PowerMonitor", params.get("power_monitor_idn", ""), "", "", ""],
        ["Start", f"{params.get('start_wl', 0):.6f}", "nm", "", ""],
        ["Stop", f"{params.get('stop_wl', 0):.6f}", "nm", "", ""],
        ["Step", f"{params.get('step', 0):.6f}", "nm", "", ""],
        ["Speed", f"{params.get('speed', 0):.6f}", "nm/s", "", ""],
        ["Source power", f"{params.get('power', 0):.6f}", "dBm", "", ""],
        ["Averaging Time", f"{params['mpm_averaging_time_ms'] / 1000:.6f}" if "mpm_averaging_time_ms" in params else "", "s", "", ""],
        ["Power meter range", params.get("power_meter_range_dbm", ""), "dBm", "MPM range", mpm_range],
        ["TSL PM- range", params.get("tsl_pm_range", ""), "", "", ""],
    ]
    writer.writerows(rows)


def _validate_columns(wavelengths, columns):
    n = len(wavelengths)
    if not n or not np.all(np.isfinite(wavelengths)):
        raise ValueError("Missing or invalid wavelength data")
    for values in columns:
        if len(values) != n or not np.all(np.isfinite(values)):
            raise ValueError("Missing, invalid or mismatched spectral data")


def save_raw_csv(
    scan: "ScanResult",
    tsl_idn: str,
    mpm_idn: str,
    filepath: str,
) -> None:
    """Save raw scan data to a CSV file.

    The file contains a 14-line metadata header followed by data columns:
    ``Wavelength(nm),Monitor-R1(dBm),Raw_M1-Ch1-R1(dBm),,``

    Args:
        scan: The ``ScanResult`` to export.
        tsl_idn: ``*IDN?`` response from the TSL.
        mpm_idn: ``*IDN?`` response from the MPM.
        filepath: Destination file path.
    """
    channels = scan.channels()
    module = int(scan.scan_params.get("mpm_module", 0)) + 1
    powers = [scan.powers_for_channel(ch) for ch in channels]
    _validate_columns(scan.wavelengths, [scan.monitor_powers, *powers])
    # R1 is the exported range-trace index, not the MPM hardware range setting.
    headers = ["Wavelength(nm)", "Monitor-R1(dBm)",
               *[f"Raw_M{module}-Ch{ch}-R1(dBm)" for ch in channels], "", ""]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        _write_header(writer, tsl_idn, mpm_idn, scan.scan_params, scan.timestamp,
                      mpm_range=scan.mpm_range)
        writer.writerow(headers)
        for i, wl in enumerate(scan.wavelengths):
            writer.writerow([f"{wl:.5f}", f"{scan.monitor_powers[i]:.5f}",
                             *[f"{power[i]:.5f}" for power in powers], "", ""])


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
    scan = il_measurement.measurement
    channel = scan.channels()[0]
    _save_loss_columns(scan, {channel: il_measurement.il}, tsl_idn, mpm_idn, filepath,
                       wavelengths=il_measurement.wavelengths)


def _save_loss_columns(scan, losses, tsl_idn, mpm_idn, filepath, *, wavelengths=None):
    wavelengths = scan.wavelengths if wavelengths is None else wavelengths
    channels = sorted(losses)
    if not channels:
        raise ValueError("Loss is unavailable; scan and set a reference first")
    _validate_columns(wavelengths, [losses[ch] for ch in channels])
    module = int(scan.scan_params.get("mpm_module", 0)) + 1
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        _write_header(writer, tsl_idn, mpm_idn, scan.scan_params, scan.timestamp,
                      mpm_range=scan.mpm_range)
        headers = ["Wavelength(nm)", *[f"IL_M{module}_CH{ch}" for ch in channels]]
        padding = [""] * max(0, 5 - len(headers))
        writer.writerow(headers + padding)
        for i, wl in enumerate(wavelengths):
            writer.writerow([f"{wl:.8f}", *[f"{losses[ch][i]:.8f}" for ch in channels]] + padding)


def save_record_csv(record, filepath: str, kind: str = "raw") -> None:
    """Export stored data, never recalculate using a newer reference."""
    scan = record.raw
    tsl_idn = scan.scan_params.get("tsl_idn", "")
    mpm_idn = scan.scan_params.get("mpm_idn", "")
    if kind == "raw":
        save_raw_csv(scan, tsl_idn, mpm_idn, filepath)
    elif kind == "loss":
        if record.is_reference or not record.loss:
            raise ValueError(record.loss_error or "Reference only supports raw export")
        _save_loss_columns(scan, record.loss, tsl_idn, mpm_idn, filepath)
    else:
        raise ValueError(f"Unknown export kind: {kind}")
