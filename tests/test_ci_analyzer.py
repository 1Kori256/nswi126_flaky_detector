import io
import zipfile

import pytest
import requests

from flaky_test_detector.ci_analyzer import (
    CIAnalysisError, GitHubActionsAnalyzer, GitLabCIAnalyzer, get_flaky_tests, parse_pytest_output,
)


def test_parser_preserves_full_ids_and_ignores_summary_duplicates():
    records = parse_pytest_output('''2026-11-04T00:00:00Z tests/a.py::TestA::test_same[with spaces] PASSED [ 50%]
\x1b[31m2026-11-04T00:00:01Z tests/b.py::TestB::test_same[with spaces] FAILED [100%]\x1b[0m
FAILED tests/b.py::TestB::test_same[with spaces] - AssertionError
''')
    assert len(records) == 2
    assert records[0]['test_id'] == 'tests/a.py::TestA::test_same[with spaces]'
    assert records[1]['test_id'] == 'tests/b.py::TestB::test_same[with spaces]'
    assert records[1]['status'] == 'failed'


def test_ambiguous_matrix_observations_are_omitted_and_duplicates_collapsed():
    records = parse_pytest_output('''tests/x.py::test_case PASSED [100%]
tests/x.py::test_case FAILED [100%]
tests/y.py::test_case PASSED [100%]
tests/y.py::test_case PASSED [100%]
''')
    assert len(records) == 1
    assert records[0]['test_id'] == 'tests/y.py::test_case'


def test_history_never_combines_different_commits_or_different_test_files():
    results = {}
    analyzer = GitHubActionsAnalyzer('owner/repo', 'test-only')
    def record(nodeid, status, sha, run):
        analyzer._record(results, [{'test_id': nodeid, 'status': status}], run, run,
                         sha, 'main', '2026-11-04T00:00:00Z')
    record('tests/a.py::test_same', 'passed', 'commit-a', 1)
    record('tests/a.py::test_same', 'failed', 'commit-b', 2)
    record('tests/b.py::test_same', 'failed', 'commit-a', 3)
    assert get_flaky_tests(results, min_runs=2) == []
    record('tests/a.py::test_same', 'failed', 'commit-a', 4)
    candidates = get_flaky_tests(results, min_runs=2)
    assert len(candidates) == 1
    assert candidates[0].test_name == 'tests/a.py::test_same'
    assert candidates[0].commit_sha == 'commit-a'
    assert candidates[0].total_runs == 2


def test_http_errors_are_propagated_with_a_timeout(monkeypatch):
    def request(*args, **kwargs):
        assert kwargs['timeout'] == 30
        raise requests.HTTPError('401 Unauthorized')
    monkeypatch.setattr(requests, 'get', request)
    with pytest.raises(CIAnalysisError, match='401'):
        GitHubActionsAnalyzer('owner/repo', 'test-only').fetch_workflow_runs()


def test_github_pagination_is_followed(monkeypatch):
    calls = []
    class Response:
        def __init__(self, page):
            self.page = page
            self.links = {'next': {'url': 'https://api.github.com/next'}} if page == 1 else {}
        def raise_for_status(self):
            pass
        def json(self):
            return {'workflow_runs': [{'id': self.page, 'name': 'Tests'}]}
    def request(url, **kwargs):
        calls.append((url, kwargs))
        return Response(len(calls))
    monkeypatch.setattr(requests, 'get', request)
    records = GitHubActionsAnalyzer('owner/repo', 'test-only').fetch_workflow_runs()
    assert [record['id'] for record in records] == [1, 2]
    assert calls[1][1]['params'] is None


def test_github_log_archive_is_read_without_extracting_files(monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('job/step.txt', 'tests/test_x.py::test_case PASSED [100%]')
    analyzer = GitHubActionsAnalyzer('owner/repo', 'test-only')
    class Response:
        content = archive.getvalue()
    monkeypatch.setattr(analyzer, '_get', lambda *args: Response())
    assert 'tests/test_x.py' in analyzer.fetch_job_logs(1)


def test_gitlab_namespaced_project_is_url_encoded():
    analyzer = GitLabCIAnalyzer('group/project', 'test-only', 'https://gitlab.example/')
    assert analyzer.project_id == 'group%2Fproject'
    assert analyzer.base_url == 'https://gitlab.example/api/v4'
