"""CLI plan and path checks: never connect to instruments."""
import importlib.util
from pathlib import Path

from santecpro.jobscript import parse_job

_spec = importlib.util.spec_from_file_location('job_cli', Path(__file__).parents[1] / 'run_job.py')
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def test_script_relative_output_and_cli_override(tmp_path):
    script = tmp_path / 'scripts' / 'a.scan'
    job = parse_job('output "../data with spaces"')
    assert cli.resolve_output(job, script, None) == tmp_path / 'data with spaces'
    assert cli.resolve_output(job, script, str(tmp_path / 'override')) == tmp_path / 'override'


def test_output_expands_home(tmp_path):
    job = parse_job('output "~/Measurements"')
    assert cli.resolve_output(job, tmp_path / 'a.scan', None) == Path.home() / 'Measurements'


def test_example_dry_run_has_filenames_wait_and_no_network(monkeypatch, capsys):
    import santecpro.remote
    from unittest.mock import MagicMock
    scanner = MagicMock(side_effect=AssertionError('dry run must not connect'))
    monkeypatch.setattr(santecpro.remote, 'RemoteScanner', scanner)
    example = Path(__file__).parents[1] / 'jobs' / 'device_two_pass.scan'
    monkeypatch.setattr('sys.argv', ['run_job.py', str(example), '--dry-run'])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert '1500-1630nm_1pm_20nms_fwd_raw.csv' in output
    assert '1545-1555nm_0.1pm_1nms_fwd_raw.csv' in output
    assert 'wait 5s after saving' in output
    scanner.assert_not_called()
