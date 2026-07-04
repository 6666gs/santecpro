#!/usr/bin/env python3
"""Run a scan-job script (``.scan``) against the Windows server.

Usage::

    python run_job.py my_job.scan                       # run
    python run_job.py my_job.scan --dry-run             # parse + validate + print plan, no hardware
    python run_job.py my_job.scan --url http://IP:5000 --outdir ./scan_results --keep-going
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from santecpro.job_runner import run_job
from santecpro.jobscript import JobScriptError, parse_job


def _print_plan(job) -> None:
    print(f"job '{job.name}': {len(job.segments)} segment(s)")
    for i, seg in enumerate(job.segments, start=1):
        channels = ",".join(str(c) for c in seg.mpm_channels)
        print(
            f"  {i:02d}. {seg.label} ({seg.direction})  {seg.start_wl:g} -> {seg.stop_wl:g} nm  "
            f"step={seg.step * 1000:g}pm speed={seg.speed:g}nm/s  "
            f"power={seg.power:g}dBm range={seg.mpm_range} ch={channels}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a scan-job script against the Santec server.")
    parser.add_argument("script", help="path to a .scan job script")
    parser.add_argument("--url", default=config.SERVER_URL,
                        help="server URL (default: config.SERVER_URL)")
    parser.add_argument("--outdir", default="scan_results",
                        help="output base directory (default: scan_results)")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse + validate + print the plan; do not connect or scan")
    parser.add_argument("--keep-going", action="store_true",
                        help="continue after a segment fails (default: stop)")
    args = parser.parse_args()

    path = Path(args.script)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 2

    try:
        job = parse_job(text, default_name=path.stem)
    except JobScriptError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 2

    _print_plan(job)

    if args.dry_run:
        print("\ndry run: script is valid; not connecting to the server.")
        return 0
    if not job.segments:
        print("\nno scan segments; nothing to do.")
        return 0

    from santecpro.remote import RemoteScanner

    scanner = RemoteScanner(args.url)
    try:
        status = scanner.status()
    except Exception as exc:
        print(f"\ncannot reach server at {args.url}: {exc}", file=sys.stderr)
        print("is server.py running on the Windows PC? (verify with: python check_setup.py)", file=sys.stderr)
        return 2
    print(f"\nconnected: {args.url}  TSL={status.get('tsl_idn') or '?'}  MPM={status.get('mpm_idn') or '?'}\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = run_job(job, scanner, args.outdir, timestamp=timestamp, keep_going=args.keep_going)

    ok = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok)
    skipped = len(job.segments) - len(results)
    out = Path(args.outdir) / f"{job.name}_{timestamp}"
    print(f"\ndone: {ok} ok, {failed} failed, {skipped} skipped  ->  {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
