"""Read CI logs for same-commit outcome changes, which remain investigation candidates."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import io
import re
from urllib.parse import quote
import zipfile

import requests


class CIAnalysisError(RuntimeError):
    pass


@dataclass
class CITestRun:
    test_name: str
    status: str
    run_id: str
    run_number: int
    commit_sha: str
    branch: str
    timestamp: datetime
    duration: float = 0.0


@dataclass
class CIFlakyTest:
    test_name: str
    total_runs: int
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    runs: list = field(default_factory=list)
    branches: set = field(default_factory=set)
    commit_sha: str = ''

    @property
    def flakiness_score(self):
        attempts = self.pass_count + self.fail_count
        return 2 * min(self.pass_count, self.fail_count) / attempts if attempts else 0.0

    @property
    def is_flaky(self):
        return self.pass_count > 0 and self.fail_count > 0

    @property
    def failure_rate(self):
        attempts = self.pass_count + self.fail_count
        return self.fail_count / attempts if attempts else 0.0


_RESULT = re.compile(r'(?P<nodeid>\S+::.+?)\s+(?P<status>PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)'
                     r'(?:\s+\[\s*\d+%\])?\s*$')
_ANSI = re.compile(r'\x1b\[[0-9;]*m')


def parse_pytest_output(logs):
    observations = {}
    for line in logs.splitlines():
        match = _RESULT.search(_ANSI.sub('', line))
        if not match:
            continue
        nodeid = match['nodeid']
        status = {'ERROR': 'failed', 'XFAIL': 'skipped', 'XPASS': 'passed'}.get(
            match['status'], match['status'].lower())
        observations.setdefault(nodeid, set()).add(status)
    # Logs may repeat summaries or combine matrix jobs. Conflicting outcomes within
    # one CI run cannot be assigned to a single execution context, so omit them.
    return [{'test_name': nodeid, 'test_id': nodeid, 'status': next(iter(statuses))}
            for nodeid, statuses in observations.items() if len(statuses) == 1]


class _HistoryAnalyzer:
    def _get(self, url, params=None):
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            raise CIAnalysisError(f'CI request failed: {error}') from error

    def _pages(self, url, params, key=None, limit=None):
        values = []
        while url:
            response = self._get(url, params)
            try:
                payload = response.json()
                page = payload[key] if key else payload
                if not isinstance(page, list):
                    raise ValueError('Expected a list of CI records')
            except (ValueError, KeyError, TypeError) as error:
                raise CIAnalysisError(f'Invalid CI response: {error}') from error
            values.extend(page)
            if limit is not None and len(values) >= limit:
                return values[:limit]
            url = response.links.get('next', {}).get('url')
            params = None
        return values

    parse_pytest_output = staticmethod(parse_pytest_output)

    @staticmethod
    def _record(results, tests, run_id, run_number, sha, branch, created):
        timestamp = datetime.fromisoformat(created.replace('Z', '+00:00'))
        for test in tests:
            key = (test['test_id'], sha)
            entry = results.setdefault(key, CIFlakyTest(test['test_id'], 0, commit_sha=sha))
            entry.total_runs += 1
            entry.branches.add(branch)
            entry.runs.append(CITestRun(test['test_id'], test['status'], str(run_id),
                                        run_number, sha, branch, timestamp))
            attribute = {'passed': 'pass_count', 'failed': 'fail_count', 'skipped': 'skip_count'}[test['status']]
            setattr(entry, attribute, getattr(entry, attribute) + 1)


class GitHubActionsAnalyzer(_HistoryAnalyzer):
    def __init__(self, repo, token, workflow_name=None):
        if len(repo.split('/')) != 2 or not all(repo.split('/')):
            raise ValueError('Repository must be owner/repo')
        self.repo = repo
        self.workflow_name = workflow_name
        self.base_url = 'https://api.github.com'
        self.headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}

    def fetch_workflow_runs(self, days=30, branch='main'):
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
        runs = self._pages(f'{self.base_url}/repos/{self.repo}/actions/runs',
                           {'per_page': 100, 'branch': branch, 'created': f'>={since}',
                            'status': 'completed'}, key='workflow_runs', limit=100)
        if self.workflow_name:
            runs = [run for run in runs if self.workflow_name.lower() in run.get('name', '').lower()]
        return runs[:20]

    def fetch_job_logs(self, run_id):
        response = self._get(f'{self.base_url}/repos/{self.repo}/actions/runs/{run_id}/logs')
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                return '\n'.join(archive.read(name).decode('utf-8', errors='replace')
                                 for name in archive.namelist() if not name.endswith('/'))
        except zipfile.BadZipFile as error:
            raise CIAnalysisError(f'Invalid log archive for run {run_id}') from error

    def analyze(self, days=30, branch='main'):
        results = {}
        for run in self.fetch_workflow_runs(days, branch):
            tests = self.parse_pytest_output(self.fetch_job_logs(run['id']))
            self._record(results, tests, run['id'], run['run_number'], run['head_sha'],
                         run['head_branch'], run['created_at'])
        return results


class GitLabCIAnalyzer(_HistoryAnalyzer):
    def __init__(self, project_id, token, gitlab_url='https://gitlab.com'):
        self.project_id = quote(str(project_id), safe='')
        self.base_url = f'{gitlab_url.rstrip("/")}/api/v4'
        self.headers = {'PRIVATE-TOKEN': token}

    def fetch_pipelines(self, days=30, ref='main'):
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return self._pages(f'{self.base_url}/projects/{self.project_id}/pipelines',
                           {'per_page': 100, 'ref': ref, 'updated_after': since}, limit=20)

    def fetch_pipeline_jobs(self, pipeline_id):
        return self._pages(f'{self.base_url}/projects/{self.project_id}/pipelines/{pipeline_id}/jobs',
                           {'per_page': 100})

    def fetch_job_log(self, job_id):
        return self._get(f'{self.base_url}/projects/{self.project_id}/jobs/{job_id}/trace').text

    def analyze(self, days=30, ref='main'):
        results = {}
        for pipeline in self.fetch_pipelines(days, ref):
            if pipeline.get('status') not in ('success', 'failed'):
                continue
            logs = [self.fetch_job_log(job['id']) for job in self.fetch_pipeline_jobs(pipeline['id'])
                    if job.get('status') in ('success', 'failed')]
            tests = self.parse_pytest_output('\n'.join(logs))
            self._record(results, tests, pipeline['id'], pipeline['id'], pipeline['sha'],
                         pipeline['ref'], pipeline['created_at'])
        return results


def get_flaky_tests(test_results, min_runs=3):
    return sorted((test for test in test_results.values() if test.pass_count + test.fail_count >= min_runs and test.is_flaky),
                  key=lambda test: (-test.flakiness_score, test.test_name, test.commit_sha))
