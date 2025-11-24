"""
CI/CD Pipeline Analyzer - Detects flaky tests from historical CI execution data
Supports GitHub Actions and GitLab CI
"""

import requests
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict


@dataclass
class CITestRun:
    """Single test execution in CI"""
    test_name: str
    status: str  # passed, failed, skipped
    run_id: str
    run_number: int
    commit_sha: str
    branch: str
    timestamp: datetime
    duration: float = 0.0


@dataclass
class CIFlakyTest:
    """Test detected as flaky from CI history"""
    test_name: str
    total_runs: int
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    runs: List[CITestRun] = field(default_factory=list)
    branches: set = field(default_factory=set)

    @property
    def flakiness_score(self) -> float:
        """Calculate flakiness score based on CI history"""
        if self.total_runs == 0:
            return 0.0
        pass_ratio = self.pass_count / self.total_runs
        fail_ratio = self.fail_count / self.total_runs
        return min(pass_ratio, fail_ratio) * 2

    @property
    def is_flaky(self) -> bool:
        """Test is flaky if it has inconsistent results"""
        return self.pass_count > 0 and self.fail_count > 0

    @property
    def failure_rate(self) -> float:
        """Percentage of failures"""
        if self.total_runs == 0:
            return 0.0
        return self.fail_count / self.total_runs


class GitHubActionsAnalyzer:
    """Analyze test history from GitHub Actions"""

    def __init__(self, repo: str, token: str, workflow_name: str = "tests"):
        """
        Args:
            repo: Repository in format "owner/repo"
            token: GitHub personal access token
            workflow_name: Name of workflow file (without .yml)
        """
        self.repo = repo
        self.token = token
        self.workflow_name = workflow_name
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def fetch_workflow_runs(self, days: int = 30, branch: str = "main") -> List[Dict]:
        """Fetch workflow runs from last N days"""
        since = (datetime.now() - timedelta(days=days)).isoformat()

        url = f"{self.base_url}/repos/{self.repo}/actions/runs"
        params = {
            "per_page": 100,
            "branch": branch,
            "created": f">={since}"
        }

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            all_runs = response.json().get("workflow_runs", [])

            # Filter by workflow name if specified
            if self.workflow_name:
                # Match workflow name (case-insensitive, handles both "tests" and "tests.yml")
                filtered_runs = [
                    run for run in all_runs
                    if self.workflow_name.lower() in run.get('name', '').lower()
                ]
                return filtered_runs

            return all_runs
        except requests.RequestException as e:
            print(f"Error fetching workflow runs: {e}")
            return []

    def fetch_job_logs(self, run_id: int) -> Optional[str]:
        """Fetch logs for a specific workflow run"""
        url = f"{self.base_url}/repos/{self.repo}/actions/runs/{run_id}/logs"

        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching logs for run {run_id}: {e}")
            return None

    def parse_pytest_output(self, logs: str) -> List[Dict]:
        """Parse pytest output from CI logs"""
        tests = []

        # Look for pytest output patterns
        lines = logs.split('\n')
        for i, line in enumerate(lines):
            # Match pytest test results: "test_file.py::test_name PASSED"
            if '::' in line and any(status in line for status in ['PASSED', 'FAILED', 'SKIPPED', 'ERROR']):
                parts = line.split()
                if len(parts) >= 2:
                    test_id = parts[0]
                    status = parts[1].lower()

                    # Extract test name
                    if '::' in test_id:
                        test_name = test_id.split('::')[-1]
                        tests.append({
                            'test_name': test_name,
                            'test_id': test_id,
                            'status': status
                        })

        return tests

    def analyze(self, days: int = 30, branch: str = "main") -> Dict[str, CIFlakyTest]:
        """Analyze CI history for flaky tests"""
        print(f"Fetching GitHub Actions runs for {self.repo} (last {days} days)...")

        workflow_runs = self.fetch_workflow_runs(days, branch)
        test_results = defaultdict(lambda: CIFlakyTest(test_name="", total_runs=0))

        print(f"Found {len(workflow_runs)} workflow runs")

        for i, run in enumerate(workflow_runs[:20], 1):  # Limit to 20 runs for API quota
            run_id = run['id']
            run_number = run['run_number']
            commit_sha = run['head_sha']
            run_branch = run['head_branch']
            timestamp = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))

            print(f"  Analyzing run {i}/20 (#{run_number})...", end=" ", flush=True)

            logs = self.fetch_job_logs(run_id)
            if not logs:
                print("❌ No logs")
                continue

            tests = self.parse_pytest_output(logs)
            print(f"✓ {len(tests)} tests")

            for test_data in tests:
                test_name = test_data['test_name']
                status = test_data['status']

                if test_name not in test_results:
                    test_results[test_name] = CIFlakyTest(
                        test_name=test_name,
                        total_runs=0
                    )

                test_result = test_results[test_name]
                test_result.total_runs += 1
                test_result.branches.add(run_branch)

                ci_run = CITestRun(
                    test_name=test_name,
                    status=status,
                    run_id=str(run_id),
                    run_number=run_number,
                    commit_sha=commit_sha,
                    branch=run_branch,
                    timestamp=timestamp
                )
                test_result.runs.append(ci_run)

                if status == 'passed':
                    test_result.pass_count += 1
                elif status in ['failed', 'error']:
                    test_result.fail_count += 1
                elif status == 'skipped':
                    test_result.skip_count += 1

        return dict(test_results)


class GitLabCIAnalyzer:
    """Analyze test history from GitLab CI"""

    def __init__(self, project_id: str, token: str, gitlab_url: str = "https://gitlab.com"):
        """
        Args:
            project_id: GitLab project ID or "namespace/project"
            token: GitLab personal access token
            gitlab_url: GitLab instance URL
        """
        self.project_id = project_id
        self.token = token
        self.base_url = f"{gitlab_url}/api/v4"
        self.headers = {
            "PRIVATE-TOKEN": token
        }

    def fetch_pipelines(self, days: int = 30, ref: str = "main") -> List[Dict]:
        """Fetch pipelines from last N days"""
        since = (datetime.now() - timedelta(days=days)).isoformat()

        url = f"{self.base_url}/projects/{self.project_id}/pipelines"
        params = {
            "per_page": 100,
            "ref": ref,
            "updated_after": since
        }

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching pipelines: {e}")
            return []

    def fetch_job_log(self, job_id: int) -> Optional[str]:
        """Fetch logs for a specific job"""
        url = f"{self.base_url}/projects/{self.project_id}/jobs/{job_id}/trace"

        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching job log {job_id}: {e}")
            return None

    def fetch_pipeline_jobs(self, pipeline_id: int) -> List[Dict]:
        """Fetch all jobs for a pipeline"""
        url = f"{self.base_url}/projects/{self.project_id}/pipelines/{pipeline_id}/jobs"

        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching jobs for pipeline {pipeline_id}: {e}")
            return []

    def parse_pytest_output(self, logs: str) -> List[Dict]:
        """Parse pytest output from CI logs"""
        tests = []

        lines = logs.split('\n')
        for line in lines:
            if '::' in line and any(status in line for status in ['PASSED', 'FAILED', 'SKIPPED', 'ERROR']):
                parts = line.split()
                if len(parts) >= 2:
                    test_id = parts[0]
                    status = parts[1].lower()

                    if '::' in test_id:
                        test_name = test_id.split('::')[-1]
                        tests.append({
                            'test_name': test_name,
                            'test_id': test_id,
                            'status': status
                        })

        return tests

    def analyze(self, days: int = 30, ref: str = "main") -> Dict[str, CIFlakyTest]:
        """Analyze CI history for flaky tests"""
        print(f"Fetching GitLab CI pipelines (last {days} days)...")

        pipelines = self.fetch_pipelines(days, ref)
        test_results = defaultdict(lambda: CIFlakyTest(test_name="", total_runs=0))

        print(f"Found {len(pipelines)} pipelines")

        for i, pipeline in enumerate(pipelines[:20], 1):  # Limit to 20 for API quota
            pipeline_id = pipeline['id']
            commit_sha = pipeline['sha']
            pipeline_ref = pipeline['ref']
            timestamp = datetime.fromisoformat(pipeline['created_at'].replace('Z', '+00:00'))

            print(f"  Analyzing pipeline {i}/20 (#{pipeline_id})...", end=" ", flush=True)

            jobs = self.fetch_pipeline_jobs(pipeline_id)
            test_job = next((j for j in jobs if 'test' in j['name'].lower()), None)

            if not test_job:
                print("❌ No test job")
                continue

            logs = self.fetch_job_log(test_job['id'])
            if not logs:
                print("❌ No logs")
                continue

            tests = self.parse_pytest_output(logs)
            print(f"✓ {len(tests)} tests")

            for test_data in tests:
                test_name = test_data['test_name']
                status = test_data['status']

                if test_name not in test_results:
                    test_results[test_name] = CIFlakyTest(
                        test_name=test_name,
                        total_runs=0
                    )

                test_result = test_results[test_name]
                test_result.total_runs += 1
                test_result.branches.add(pipeline_ref)

                ci_run = CITestRun(
                    test_name=test_name,
                    status=status,
                    run_id=str(pipeline_id),
                    run_number=pipeline_id,
                    commit_sha=commit_sha,
                    branch=pipeline_ref,
                    timestamp=timestamp
                )
                test_result.runs.append(ci_run)

                if status == 'passed':
                    test_result.pass_count += 1
                elif status in ['failed', 'error']:
                    test_result.fail_count += 1
                elif status == 'skipped':
                    test_result.skip_count += 1

        return dict(test_results)


def get_flaky_tests(test_results: Dict[str, CIFlakyTest], min_runs: int = 3) -> List[CIFlakyTest]:
    """Filter and return flaky tests"""
    flaky_tests = []

    for test_name, test_data in test_results.items():
        if test_data.total_runs >= min_runs and test_data.is_flaky:
            flaky_tests.append(test_data)

    # Sort by flakiness score
    flaky_tests.sort(key=lambda t: t.flakiness_score, reverse=True)

    return flaky_tests
