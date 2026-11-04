import json
from pathlib import Path

from typer.testing import CliRunner

from flaky_test_detector.cli import app

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_documented_demo_has_reproducible_counts_and_json_file(tmp_path):
    output = tmp_path / 'report.json'
    result = runner.invoke(app, ['detect', str(ROOT / 'example_project/tests/test_demo.py'),
                                 '--runs', '4', '--json', '--output', str(output), '--no-analyze'])
    assert result.exit_code == 1, result.output
    report = json.loads(result.stdout)
    assert json.loads(output.read_text()) == report
    assert report['summary'] == {'total': 3, 'missing_observations': 0, 'flaky': 1,
                                 'failing': 1, 'incomplete': 0, 'passed': 1, 'skipped': 0}
    assert all('hints' not in entry and 'suggestions' not in entry for entry in report['tests'])


def test_all_passing_suite_exits_zero_without_claiming_stability(tmp_path):
    path = tmp_path / 'test_ok.py'
    path.write_text('def test_ok(): assert True\n')
    result = runner.invoke(app, ['detect', str(path), '-n', '2'])
    assert result.exit_code == 0, result.output
    assert '0 flaky' in result.output
    assert 'cannot prove stability' in result.output


def test_persistent_failure_is_not_called_stable(tmp_path):
    path = tmp_path / 'test_fail.py'
    path.write_text('def test_fail(): assert False\n')
    result = runner.invoke(app, ['detect', str(path), '-n', '2', '--json'])
    assert result.exit_code == 1, result.output
    report = json.loads(result.stdout)
    assert report['tests'][0]['status'] == 'failing'
    assert report['tests'][0]['failed'] == 2
    assert report['summary']['flaky'] == 0


def test_missing_path_returns_structured_error(tmp_path):
    result = runner.invoke(app, ['detect', str(tmp_path / 'missing.py'), '--json'])
    assert result.exit_code == 2
    assert json.loads(result.stdout)['status'] == 'error'


def test_analysis_resolves_class_and_parameterized_test(tmp_path):
    path = tmp_path / 'test_param.py'
    path.write_text('''import os
import random as rng
import pytest
class TestExample:
    @pytest.mark.parametrize('value', [1], ids=['example'])
    def test_case(self, value):
        rng.seed(42)
        assert int(os.environ['FLAKY_DETECTOR_RUN']) % 2 == 1
        assert rng.randint(0, 1) == 0
''')
    result = runner.invoke(app, ['detect', str(path), '-n', '2', '--json', '--no-suggest'])
    assert result.exit_code == 1, result.output
    entry = json.loads(result.stdout)['tests'][0]
    assert entry['status'] == 'flaky'
    assert any(hint['type'] == 'random_dependent' for hint in entry['hints'])
    assert 'suggestions' not in entry
    assert all('confidence' not in hint for hint in entry['hints'])


def test_parameter_labels_are_rendered_literally(tmp_path):
    path = tmp_path / 'test_labels.py'
    path.write_text('''import pytest
@pytest.mark.parametrize('value', [1], ids=['[/]'])
def test_case(value):
    assert False
''')
    result = runner.invoke(app, ['detect', str(path), '-n', '2', '--no-analyze'])
    assert result.exit_code == 1, result.output
    assert 'failing' in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_ci_empty_history_is_not_a_clean_result(monkeypatch):
    from flaky_test_detector.ci_analyzer import GitHubActionsAnalyzer
    monkeypatch.setattr(GitHubActionsAnalyzer, 'analyze', lambda *args: {})
    result = runner.invoke(app, ['ci-github', 'owner/repo', '--token', 'test-only'])
    assert result.exit_code == 2
    assert 'No usable per-test observations' in result.output
