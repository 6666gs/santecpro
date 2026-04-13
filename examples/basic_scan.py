#!/usr/bin/env python3
"""Basic scan example for Santec TSL-550 + MPM-210.

Usage:
    python examples/basic_scan.py

Prerequisites:
    - NI-VISA runtime installed
    - TSL-550 connected via GPIB (default address: 10)
    - MPM-210 connected via GPIB (default address: 17)
"""

import pyvisa
from santecpro import TSLInstrument, MPMInstrument, Scanner


def main():
    # Initialize VISA resource manager
    rm = pyvisa.ResourceManager()

    # Print available resources
    print("Available VISA resources:")
    for r in rm.list_resources():
        print(f"  {r}")

    # Connect to instruments
    print("\nConnecting to TSL-550...")
    tsl = TSLInstrument(rm)
    tsl.connect("GPIB0::10::INSTR")
    print(f"  TSL IDN: {tsl.idn}")

    print("Connecting to MPM-210...")
    mpm = MPMInstrument(rm)
    mpm.connect("GPIB0::17::INSTR")
    print(f"  MPM IDN: {mpm.idn}")

    # Turn on laser
    tsl.laser_on()
    tsl.shutter_open()

    # Configure and run a basic scan
    scanner = Scanner(tsl, mpm)
    scanner.configure(
        start_wl=1550.0,
        stop_wl=1560.0,
        step=0.01,
        speed=20.0,
        power=0.0,
        sweep_mode="CONTINUOUS_ONE_WAY",
        ranges=[1],
    )

    print("\nStarting scan...")
    result = scanner.run_single_scan(
        mpm_range=1,
        plot=True,
        save_csv="scan_result_raw.csv",
    )
    print(f"Scan complete: {len(result.wavelengths)} data points")
    print(f"Wavelength range: {result.wavelengths[0]:.3f} - {result.wavelengths[-1]:.3f} nm")
    print(f"Power range: {result.powers.min():.2f} - {result.powers.max():.2f} dBm")

    # Cleanup
    tsl.shutter_close()
    tsl.laser_off()
    tsl.disconnect()
    mpm.disconnect()
    rm.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
