import json
import subprocess
from pathlib import Path

import pytest

from flaky_test_detector.detector import DetectionError, FlakyDetector, FlakyTest, TestResult as Result


def target(tmp_path, source):
    path = tmp_path / 'test_sample.py'
    path.write_text(source, encoding='utf-8')
    return path


@pytest.mark.parametrize('counts,status,score', [
    ((2, 2, 0, 0), 'flaky', 1), ((2, 0, 2, 5), 'flaky', 1),
    ((0, 3, 0, 0), 'failing', 0), ((0, 0, 3, 0), 'failing', 0),
    ((3, 0, 0, 0), 'passed', 0), ((0, 0, 0, 3), 'skipped', 0),
])
def test_outcome_classification_includes_errors_and_excludes_skips(counts, status, score):
    passed, failed, errors, skipped = counts
    test = FlakyTest('x.py::test_x', 'x.py', 'test_x', pass_count=passed,
                     fail_count=failed, error_count=errors, skip_count=skipped)
    assert test.status == status
    assert test.flakiness_score == score


def test_report_is_rooted_at_pytest_root_and_uses_all_stage_durations(tmp_path):
    result = FlakyDetector._parse_result({
        'nodeid': 'tests/test_x.py::TestA::test_x[with spaces]', 'outcome': 'error',
        'setup': {'duration': 0.1, 'outcome': 'passed'},
        'call': {'duration': 0.2, 'outcome': 'passed'},
        'teardown': {'duration': 0.3, 'outcome': 'failed', 'longrepr': 'cleanup failed'},
    }, tmp_path)
    assert result.duration == pytest.approx(0.6)
    assert result.outcome == 'error'
    assert result.error_message == 'cleanup failed'
    assert result.test_file == str(tmp_path / 'tests/test_x.py')


def test_missing_observations_are_kept_in_run_order(tmp_path):
    detector = FlakyDetector(str(tmp_path), runs=3)
    detector._process_results([Result('x.py::test_a', 'passed', 0)])
    detector._process_results([Result('x.py::test_b', 'passed', 0)])
    detector._process_results([Result('x.py::test_a', 'passed', 0)])
    assert detector.results['x.py::test_a'].outcomes == ['passed', 'missing', 'passed']
    assert detector.results['x.py::test_b'].outcomes == ['missing', 'passed', 'missing']
    report = detector.to_report()
    assert report['status'] == 'incomplete'
    assert report['summary']['missing_observations'] == 3
    assert detector.get_stable_tests() == []


def test_local_integration_distinguishes_mixed_and_persistent_failures(tmp_path):
    path = target(tmp_path, '''import os

def test_passes():
    assert True

def test_alternates():
    assert int(os.environ['FLAKY_DETECTOR_RUN']) % 2 == 1

def test_fails():
    assert False
''')
    detector = FlakyDetector(str(path), runs=4)
    detector.run_detection()
    by_function = {test.test_function: test for test in detector.results.values()}
    assert by_function['test_alternates'].outcomes == ['passed', 'failed', 'passed', 'failed']
    assert by_function['test_fails'].status == 'failing'
    assert by_function['test_passes'].status == 'passed'
    assert len(detector.get_flaky_tests()) == 1
    assert detector.completed_runs == 4
    # Reusing the object must not accumulate a second history.
    detector.runs = 2
    detector.run_detection()
    assert len(next(iter(detector.results.values())).outcomes) == 2


def test_real_setup_and_teardown_errors_are_counted(tmp_path):
    path = target(tmp_path, '''import pytest

@pytest.fixture
def broken_setup():
    raise RuntimeError('setup problem')

@pytest.fixture
def broken_teardown():
    yield
    raise RuntimeError('teardown problem')

def test_setup(broken_setup):
    pass

def test_teardown(broken_teardown):
    pass
''')
    detector = FlakyDetector(str(path), runs=2)
    detector.run_detection()
    assert len(detector.results) == 2
    for test in detector.results.values():
        assert test.error_count == 2
        assert test.status == 'failing'
        assert 'problem' in test.error_messages[0]


def test_node_id_selection_and_parameterized_ids_are_preserved(tmp_path):
    path = target(tmp_path, '''import pytest
class TestA:
    @pytest.mark.parametrize('value', [1, 2], ids=['one', 'two'])
    def test_same(self, value):
        assert value > 0
class TestB:
    def test_same(self):
        assert False
''')
    detector = FlakyDetector(f'{path}::TestA', runs=2)
    detector.run_detection()
    assert len(detector.results) == 2
    assert {test.test_function for test in detector.results.values()} == {
        'TestA::test_same[one]', 'TestA::test_same[two]'}
    assert all(test.status == 'passed' for test in detector.results.values())


def test_collection_failure_is_an_error_not_a_clean_scan(tmp_path):
    path = target(tmp_path, 'import no_such_dependency_for_detector_test\n')
    with pytest.raises(DetectionError, match='exited with code'):
        FlakyDetector(str(path), runs=2).run_detection()


def test_no_tests_is_an_error(tmp_path):
    path = target(tmp_path, 'VALUE = 1\n')
    with pytest.raises(DetectionError, match='exited with code 5'):
        FlakyDetector(str(path), runs=2).run_detection()


def test_subprocess_timeout_stops_detection(tmp_path):
    path = target(tmp_path, 'import time\ndef test_slow(): time.sleep(20)\n')
    with pytest.raises(DetectionError, match='timed out'):
        FlakyDetector(str(path), runs=2, timeout=0.05).run_detection()


@pytest.mark.parametrize('mode', ['missing', 'malformed', 'empty', 'duplicate'])
def test_invalid_reports_fail_and_temporary_files_are_cleaned(tmp_path, monkeypatch, mode):
    path = target(tmp_path, 'def test_ok(): pass\n')
    reports = []
    def fake_run(command, **kwargs):
        assert command[1:3] == ['-m', 'pytest']
        report_path = Path(next(value.split('=', 1)[1] for value in command if value.startswith('--json-report-file=')))
        reports.append(report_path)
        if mode == 'malformed':
            report_path.write_text('not json')
        elif mode == 'empty':
            report_path.write_text(json.dumps({'exitcode': 0, 'tests': []}))
        elif mode == 'duplicate':
            record = {'nodeid': 'x.py::test_ok', 'outcome': 'passed'}
            report_path.write_text(json.dumps({'exitcode': 0, 'tests': [record, record]}))
        return subprocess.CompletedProcess(command, 0, stdout='', stderr='')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    with pytest.raises(DetectionError, match='report'):
        FlakyDetector(str(path), runs=2).run_detection()
    assert all(not report.parent.exists() for report in reports)


@pytest.mark.parametrize('runs,timeout', [(1, 1), (0, 1), (2, 0), (2, float('inf'))])
def test_invalid_options_are_rejected(tmp_path, runs, timeout):
    with pytest.raises(ValueError):
        FlakyDetector(str(tmp_path), runs=runs, timeout=timeout)
