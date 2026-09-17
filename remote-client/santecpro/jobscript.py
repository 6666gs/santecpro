"""Parser for the scan-job DSL (`.scan` files).

Turns a line-based script into a validated :class:`JobSpec`. Pure logic — no
hardware, no network — so it is fully unit-testable and used by both the CLI
(`run_job.py`) and `job_runner`.

Grammar (one directive per line; ``#`` starts a full-line comment)::

    job <name>
    device "device name"
    output "~/Measurements"
    wait 5s                              # after the preceding scan
    set <key>=<value> ...                 # defaults: power range channels
    scan <label> <start> <stop> step=<v>{pm|nm} speed=<v> [power= range= channels= dir=]

``dir`` is one of forward (default) / reverse / both. ``reverse`` swaps
start/stop so the laser physically sweeps down; ``both`` expands to a forward
segment followed by a reverse segment.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import shlex
import math

from santecpro.sweep_rules import validate_sts_sweep_params

_BUILTIN_DEFAULTS = {"power": 0.0, "range": (1,), "channels": (1,), "averaging": 0.01}


class JobScriptError(Exception):
    """Raised when a scan script cannot be parsed or validated."""

    def __init__(self, line: int, message: str):
        self.line = line
        self.message = message
        super().__init__(f"line {line}: {message}")


@dataclass(frozen=True)
class Segment:
    """One resolved scan pass (direction already applied to start/stop)."""

    label: str
    start_wl: float
    stop_wl: float
    step: float                       # nm
    speed: float                      # nm/s
    power: float                      # dBm
    mpm_range: int
    mpm_channels: tuple[int, ...]
    mpm_averaging_time_ms: float
    direction: str                    # "fwd" | "rev"
    wait_after_s: float = 0.0
    mpm_ranges: tuple[int, ...] = ()


@dataclass(frozen=True)
class JobSpec:
    name: str
    segments: tuple[Segment, ...]
    device: str | None = None
    output: str | None = None


def parse_job(text: str, *, default_name: str = "job") -> JobSpec:
    """Parse a scan script into a validated :class:`JobSpec`.

    Raises:
        JobScriptError: on any syntax or validation problem, with the 1-based
            line number of the offending line.
    """
    name: str | None = None
    device = output = None
    defaults = dict(_BUILTIN_DEFAULTS)
    segments: list[Segment] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            raise JobScriptError(lineno, str(exc)) from None
        keyword, args = tokens[0], tokens[1:]

        if keyword == "job":
            if len(args) != 1:
                raise JobScriptError(lineno, "job needs exactly one name: job <name>")
            if name is not None:
                raise JobScriptError(lineno, "job already set earlier")
            name = _filename(args[0], lineno)
        elif keyword in ("device", "output"):
            if len(args) != 1 or not args[0].strip():
                raise JobScriptError(lineno, f'{keyword} needs one value; quote values containing spaces')
            if keyword == "device":
                if device is not None:
                    raise JobScriptError(lineno, "device already set earlier")
                device = _filename(args[0], lineno)
            else:
                if output is not None:
                    raise JobScriptError(lineno, "output already set earlier")
                output = args[0]
        elif keyword == "wait":
            if not segments or len(args) != 1 or not args[0].endswith("s"):
                raise JobScriptError(lineno, "wait needs a preceding scan and seconds, e.g. wait 5s")
            seconds = _num(args[0][:-1], lineno, "wait")
            if seconds < 0:
                raise JobScriptError(lineno, "wait must be non-negative")
            segments[-1] = replace(segments[-1], wait_after_s=segments[-1].wait_after_s + seconds)
        elif keyword == "set":
            _apply_set(defaults, args, lineno)
        elif keyword == "scan":
            segments.extend(_parse_scan(args, lineno, defaults))
        else:
            raise JobScriptError(lineno, f"unknown directive '{keyword}' (expected job/device/output/set/scan/wait)")

    return JobSpec(name=name or _filename(default_name, 0), segments=tuple(segments),
                   device=device, output=output)


# --- helpers ---------------------------------------------------------------


def _split_kv(token: str, lineno: int) -> tuple[str, str]:
    if "=" not in token:
        raise JobScriptError(lineno, f"expected key=value (got '{token}')")
    key, _, value = token.partition("=")
    return key.strip(), value.strip()


def _filename(value: str, lineno: int) -> str:
    if not value.strip() or value in (".", "..") or any(char in value for char in '/\\:*?"<>|'):
        raise JobScriptError(lineno, "job names and scan labels must be valid filenames")
    return value


def _num(value: str, lineno: int, what: str) -> float:
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite")
        return number
    except ValueError:
        raise JobScriptError(lineno, f"{what} must be a number (got '{value}')") from None


def _int(value: str, lineno: int, what: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise JobScriptError(lineno, f"{what} must be an integer (got '{value}')") from None


def _parse_step(value: str, lineno: int) -> float:
    v = value.strip().lower()
    if v.endswith("pm"):
        return _num(v[:-2], lineno, "step") / 1000.0
    if v.endswith("nm"):
        return _num(v[:-2], lineno, "step")
    raise JobScriptError(lineno, f"step needs a unit, e.g. 20pm or 0.02nm (got '{value}')")


def _parse_ranges(value: str, lineno: int) -> tuple[int, ...]:
    values = tuple(_int(v, lineno, "range") for v in value.split(","))
    if not values or any(v not in range(1, 6) for v in values) or len(set(values)) != len(values):
        raise JobScriptError(lineno, "range must list distinct ranges 1-5, e.g. range=2,3,4,5")
    return tuple(sorted(values))


def _parse_channels(value: str, lineno: int) -> tuple[int, ...]:
    channels: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        ch = _int(part, lineno, "channel")
        if ch < 1 or ch > 4:
            raise JobScriptError(lineno, f"channel must be 1-4 (got {ch})")
        channels.append(ch)
    if not channels:
        raise JobScriptError(lineno, "channels must list at least one channel, e.g. channels=1,2")
    return tuple(dict.fromkeys(channels))  # de-duplicate, preserve order


def _apply_set(defaults: dict, args: list[str], lineno: int) -> None:
    if not args:
        raise JobScriptError(lineno, "set needs at least one key=value")
    for token in args:
        key, value = _split_kv(token, lineno)
        if key == "power":
            defaults["power"] = _num(value, lineno, "power")
        elif key == "range":
            defaults["range"] = _parse_ranges(value, lineno)
        elif key == "channels":
            defaults["channels"] = _parse_channels(value, lineno)
        elif key == "averaging":
            defaults["averaging"] = _num(value, lineno, "averaging")
        else:
            raise JobScriptError(lineno, f"unknown set key '{key}' (power|range|channels|averaging)")


def _parse_scan(args: list[str], lineno: int, defaults: dict) -> list[Segment]:
    if len(args) < 3:
        raise JobScriptError(
            lineno, "scan needs: scan <label> <start> <stop> step=<v>pm|nm speed=<v>"
        )
    label = _filename(args[0], lineno)
    start = _num(args[1], lineno, "start")
    stop = _num(args[2], lineno, "stop")

    params = dict(defaults)
    step: float | None = None
    speed: float | None = None
    direction = "forward"

    for token in args[3:]:
        key, value = _split_kv(token, lineno)
        if key == "step":
            step = _parse_step(value, lineno)
        elif key == "speed":
            speed = _num(value, lineno, "speed")
        elif key == "power":
            params["power"] = _num(value, lineno, "power")
        elif key == "range":
            params["range"] = _parse_ranges(value, lineno)
        elif key == "channels":
            params["channels"] = _parse_channels(value, lineno)
        elif key == "averaging":
            params["averaging"] = _num(value, lineno, "averaging")
        elif key == "dir":
            direction = value.strip().lower()
        else:
            raise JobScriptError(lineno, f"unknown key '{key}'")

    if step is None:
        raise JobScriptError(lineno, "missing required 'step=<v>pm|nm'")
    if speed is None:
        raise JobScriptError(lineno, "missing required 'speed=<v>'")
    if direction not in ("forward", "reverse", "both"):
        raise JobScriptError(lineno, f"invalid dir '{direction}' (forward|reverse|both)")

    if params["averaging"] <= 0:
        raise JobScriptError(lineno, "range must be 1-5 and averaging must be positive")
    try:
        validate_sts_sweep_params(start, stop, step, speed)
    except ValueError as exc:
        raise JobScriptError(lineno, str(exc)) from None

    return _expand_direction(label, start, stop, step, speed, params, direction)


def _expand_direction(
    label: str,
    start: float,
    stop: float,
    step: float,
    speed: float,
    params: dict,
    direction: str,
) -> list[Segment]:
    def make(a: float, b: float, tag: str) -> Segment:
        return Segment(
            label=label,
            start_wl=a,
            stop_wl=b,
            step=step,
            speed=speed,
            power=params["power"],
            mpm_range=params["range"][0],
            mpm_ranges=params["range"] if len(params["range"]) > 1 else (),
            mpm_channels=params["channels"],
            mpm_averaging_time_ms=params["averaging"],
            direction=tag,
        )

    if direction == "forward":
        return [make(start, stop, "fwd")]
    if direction == "reverse":
        return [make(stop, start, "rev")]
    return [make(start, stop, "fwd"), make(stop, start, "rev")]
