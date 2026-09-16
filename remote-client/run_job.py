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
from santecpro.job_runner import run_job, csv_filename
from santecpro.jobscript import JobScriptError, parse_job


def _print_plan(job, save_kind="raw", reference_first=False) -> None:
    print(f"job '{job.name}': {len(job.segments)} segment(s)")
    for i, seg in enumerate(job.segments, start=1):
        channels = ",".join(str(c) for c in seg.mpm_channels)
        print(
            f"  {i:02d}. {seg.label} ({seg.direction})  {seg.start_wl:g} -> {seg.stop_wl:g} nm  "
            f"step={seg.step * 1000:g}pm speed={seg.speed:g}nm/s  "
            f"power={seg.power:g}dBm range={seg.mpm_range} ch={channels}"
        )

        kind = "raw" if reference_first and i == 1 else save_kind
        print(f"      -> {csv_filename(job, seg, i, kind)}")
        if seg.wait_after_s:
            print(f"      wait {seg.wait_after_s:g}s after saving")


def resolve_output(job, script: Path, override: str | None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    if job.output:
        output = Path(job.output).expanduser()
        return (script.resolve().parent / output).resolve()
    return Path("scan_results").resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a scan-job script against the Santec server.")
    parser.add_argument("script", help="path to a .scan job script")
    parser.add_argument("--url", default=config.SERVER_URL,
                        help="server URL (default: config.SERVER_URL)")
    parser.add_argument("--tsl", default=config.TSL_ADDRESS, help="TSL GPIB address")
    parser.add_argument("--mpm", default=config.MPM_ADDRESS, help="MPM GPIB address")
    parser.add_argument("--outdir",
                        help="override script output directory (fallback: ./scan_results)")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse + validate + print the plan; do not connect or scan")
    parser.add_argument("--keep-going", action="store_true",
                        help="continue after a segment fails (default: stop)")
    parser.add_argument("--reference-first", action="store_true",
                        help="scan and set the first segment as reference; always save it as raw")
    parser.add_argument("--save", choices=("raw", "loss"), default="raw",
                        help="format to export; memory keeps both when a reference exists")
    args = parser.parse_args()
    if args.save == "loss" and not args.reference_first:
        parser.error("--save loss requires --reference-first")

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

    outdir = resolve_output(job, path, args.outdir)
    print(f"output: {outdir}")
    _print_plan(job, args.save, args.reference_first)

    if args.dry_run:
        print("\ndry run: script is valid; not connecting to the server.")
        return 0
    if not job.segments:
        print("\nno scan segments; nothing to do.")
        return 0

    from santecpro.remote import RemoteScanner

    scanner = RemoteScanner(args.url)
    scanner.set_addresses(args.tsl, args.mpm)
    try:
        status = scanner.check_instruments()
        scanner.prepare_laser(progress=print)
    except Exception as exc:
        print(f"\ncannot reach server at {args.url}: {exc}", file=sys.stderr)
        print("is server.py running on the Windows PC? (verify with: python check_setup.py)", file=sys.stderr)
        return 2
    print(f"\nconnected: {args.url}  TSL={status.get('tsl_idn') or '?'}  MPM={status.get('mpm_idn') or '?'}\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
        results = run_job(job, scanner, outdir, timestamp=timestamp, keep_going=args.keep_going,
                          reference_first=args.reference_first, save_kind=args.save,
                          reference_ready=lambda: input("Reference 已保存。请切换到待测器件光路，按 Enter 继续（Ctrl+C 退出）："))
    except KeyboardInterrupt:
        try:
            scanner.cancel_scan()
            print("Cancellation requested; check /api/scan/state for completion.", file=sys.stderr)
        except Exception as exc:
            print(f"Cannot confirm cancellation: {exc}", file=sys.stderr)
        return 130

    except OSError as exc:
        print(f"Cannot write job output: {exc}", file=sys.stderr)
        return 1

    ok = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok)
    skipped = len(job.segments) - len(results)
    out = outdir / f"{job.name}_{timestamp}"
    print(f"\ndone: {ok} ok, {failed} failed, {skipped} skipped  ->  {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
