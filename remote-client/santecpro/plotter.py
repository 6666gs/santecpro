"""Real-time plotting for scan and insertion-loss results."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from santecpro.results import ScanResult, ILMeasurement


def plot_scan_result(scan: "ScanResult") -> None:
    """Plot wavelength vs power for a scan result.

    Args:
        scan: The ``ScanResult`` to plot.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(scan.wavelengths, scan.powers)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Power (dBm)")
    start = scan.wavelengths[0]
    stop = scan.wavelengths[-1]
    ax.set_title(f"Scan Result  {start:.1f} - {stop:.1f} nm")
    ax.grid(True)
    plt.tight_layout()
    plt.show()


def plot_il_result(il_measurement: "ILMeasurement") -> None:
    """Plot wavelength vs insertion loss for an IL measurement.

    Args:
        il_measurement: The ``ILMeasurement`` to plot.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(il_measurement.wavelengths, il_measurement.il)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Insertion Loss (dB)")
    ax.set_title("IL Measurement")
    ax.grid(True)
    plt.tight_layout()
    plt.show()
