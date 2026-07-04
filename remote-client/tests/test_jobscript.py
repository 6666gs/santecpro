"""Tests for the scan-job DSL parser."""

from __future__ import annotations

import pytest

from santecpro.jobscript import JobScriptError, JobSpec, Segment, parse_job


def test_minimal_single_scan():
    job = parse_job("scan broadband 1500 1600 step=20pm speed=50")
    assert isinstance(job, JobSpec)
    assert len(job.segments) == 1
    seg = job.segments[0]
    assert seg.label == "broadband"
    assert seg.start_wl == 1500.0
    assert seg.stop_wl == 1600.0
    assert seg.step == pytest.approx(0.02)  # 20 pm -> nm
    assert seg.speed == 50.0
    assert seg.direction == "fwd"
    # built-in defaults
    assert seg.power == 0.0
    assert seg.mpm_range == 1
    assert seg.mpm_channels == (1,)
    assert seg.mpm_averaging_time_ms == pytest.approx(0.01)


def test_job_line_sets_name():
    job = parse_job("job deviceA\nscan s 1500 1510 step=1pm speed=10")
    assert job.name == "deviceA"


def test_default_name_when_no_job_line():
    job = parse_job("scan s 1500 1510 step=1pm speed=10", default_name="mystem")
    assert job.name == "mystem"


def test_duplicate_job_line_errors():
    with pytest.raises(JobScriptError, match="line 2"):
        parse_job("job a\njob b")


def test_step_nm_unit_passes_through():
    seg = parse_job("scan s 1500 1520 step=0.02nm speed=50").segments[0]
    assert seg.step == pytest.approx(0.02)


def test_step_without_unit_errors():
    with pytest.raises(JobScriptError, match="line 1"):
        parse_job("scan s 1500 1520 step=20 speed=50")


def test_set_defaults_applied_and_overridden():
    text = (
        "set power=3 channels=1,2 range=2 averaging=0.05\n"
        "scan a 1500 1510 step=1pm speed=10\n"
        "scan b 1500 1510 step=1pm speed=10 power=7 channels=3\n"
    )
    a, b = parse_job(text).segments
    assert a.power == 3.0 and a.mpm_channels == (1, 2) and a.mpm_range == 2
    assert a.mpm_averaging_time_ms == pytest.approx(0.05)
    assert b.power == 7.0 and b.mpm_channels == (3,)  # overrides


def test_set_can_change_midway():
    text = (
        "set channels=1\n"
        "scan a 1500 1510 step=1pm speed=10\n"
        "set channels=2\n"
        "scan b 1500 1510 step=1pm speed=10\n"
    )
    a, b = parse_job(text).segments
    assert a.mpm_channels == (1,)
    assert b.mpm_channels == (2,)


def test_reverse_swaps_start_stop():
    seg = parse_job("scan s 1549 1551 step=1pm speed=10 dir=reverse").segments[0]
    assert seg.start_wl == 1551.0
    assert seg.stop_wl == 1549.0
    assert seg.direction == "rev"


def test_both_expands_to_fwd_then_rev():
    segs = parse_job("scan res 1549 1551 step=1pm speed=10 dir=both").segments
    assert len(segs) == 2
    fwd, rev = segs
    assert fwd.direction == "fwd" and (fwd.start_wl, fwd.stop_wl) == (1549.0, 1551.0)
    assert rev.direction == "rev" and (rev.start_wl, rev.stop_wl) == (1551.0, 1549.0)
    assert fwd.label == rev.label == "res"


def test_comments_and_blank_lines_ignored():
    text = "# a comment\n\n   \nscan s 1500 1510 step=1pm speed=10  \n# trailing\n"
    job = parse_job(text)
    assert len(job.segments) == 1


def test_invalid_step_errors_with_line():
    with pytest.raises(JobScriptError, match="line 1"):
        parse_job("scan s 1500 1510 step=3pm speed=10")


def test_invalid_speed_for_step_errors():
    # 1 pm step only allows speed choices from the full table; 999 is invalid
    with pytest.raises(JobScriptError, match="line 1"):
        parse_job("scan s 1500 1510 step=1pm speed=999")


def test_missing_step_errors():
    with pytest.raises(JobScriptError, match="step"):
        parse_job("scan s 1500 1510 speed=10")


def test_missing_speed_errors():
    with pytest.raises(JobScriptError, match="speed"):
        parse_job("scan s 1500 1510 step=1pm")


def test_unknown_key_errors():
    with pytest.raises(JobScriptError, match="spede"):
        parse_job("scan s 1500 1510 step=1pm spede=10")


def test_bad_channel_errors():
    with pytest.raises(JobScriptError, match="line 1"):
        parse_job("scan s 1500 1510 step=1pm speed=10 channels=5")


def test_non_numeric_start_errors():
    with pytest.raises(JobScriptError, match="line 1"):
        parse_job("scan s abc 1510 step=1pm speed=10")


def test_invalid_dir_errors():
    with pytest.raises(JobScriptError, match="line 1"):
        parse_job("scan s 1500 1510 step=1pm speed=10 dir=sideways")


def test_unknown_directive_errors():
    with pytest.raises(JobScriptError, match="line 1"):
        parse_job("wibble s 1500 1510")


def test_scan_missing_positionals_errors():
    with pytest.raises(JobScriptError, match="line 1"):
        parse_job("scan s 1500 step=1pm speed=10")
