"""Repeat pytest runs and distinguish observed flakes from persistent failures."""

from collections import Counter
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Dict, List


class DetectionError(RuntimeError):
    """A run could not produce a complete, usable pytest report."""


@dataclass
class TestResult:
    test_id: str
    outcome: str
    duration: float
    error_message: str = ''
    test_file: str = ''


@dataclass
class FlakyTest:
    test_id: str
    test_file: str
    test_function: str
    pass_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    skip_count: int = 0
    missing_count: int = 0
    outcomes: List[str] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)
    durations: List[float] = field(default_factory=list)

    @property
    def flakiness_score(self) -> float:
        """Outcome balance, not a probability: 1 means equal passes and failures."""
        failures = self.fail_count + self.error_count
        attempts = self.pass_count + failures
        return 2 * min(self.pass_count, failures) / attempts if attempts else 0.0

    @property
    def is_flaky(self) -> bool:
        return self.pass_count > 0 and self.fail_count + self.error_count > 0

    @property
    def status(self) -> str:
        if self.is_flaky:
            return 'flaky'
        if self.fail_count + self.error_count:
            return 'failing'
        if self.missing_count:
            return 'incomplete'
        return 'passed' if self.pass_count else 'skipped'

    @property
    def failure_pattern(self) -> str:
        if not self.is_flaky:
            return 'not_flaky'
        sequence = [value for value in self.outcomes if value in ('passed', 'failed', 'error')]
        failed = self.fail_count + self.error_count
        if len(sequence) >= 5 and failed / len(sequence) <= 0.2:
            return 'rarely_failing'
        if len(sequence) >= 5 and self.pass_count / len(sequence) <= 0.2:
            return 'rarely_passing'
        transitions = sum((a == 'passed') != (b == 'passed') for a, b in zip(sequence, sequence[1:]))
        if transitions == 1:
            return 'initially_passing' if sequence[0] == 'passed' else 'initially_failing'
        return 'intermittent'


class FlakyDetector:
    def __init__(self, test_path: str, runs: int = 10, verbose: bool = False, timeout: float = 300):
        path, separator, selector = str(test_path).partition('::')
        self.test_path = Path(path).resolve()
        if not self.test_path.exists():
            raise ValueError(f'Test path does not exist: {path}')
        if not isinstance(runs, int) or runs < 2:
            raise ValueError('At least two runs are required')
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Timeout must be a positive, finite number')
        self.target = str(self.test_path) + (separator + selector if separator else '')
        self.runs = runs
        self.verbose = verbose
        self.timeout = timeout
        self.pytest_cwd = Path.cwd()
        self.results: Dict[str, FlakyTest] = {}
        self.completed_runs = 0

    def run_detection(self) -> Dict[str, FlakyTest]:
        self.results.clear()
        self.completed_runs = 0
        for run_number in range(1, self.runs + 1):
            if self.verbose:
                print(f'Run {run_number}/{self.runs}', file=sys.stderr, flush=True)
            results = self._execute_single_run(run_number)
            self._process_results(results)
        return self.results

    def _execute_single_run(self, run_number: int) -> List[TestResult]:
        with tempfile.TemporaryDirectory(prefix='flaky-detector-') as directory:
            report_file = Path(directory) / 'report.json'
            command = [sys.executable, '-m', 'pytest', self.target, '--json-report',
                       f'--json-report-file={report_file}', '-q', '--tb=short', '--disable-warnings']
            environment = dict(os.environ, FLAKY_DETECTOR_RUN=str(run_number))
            try:
                process = subprocess.run(command, cwd=self.pytest_cwd, env=environment,
                                         capture_output=True, text=True, timeout=self.timeout)
            except subprocess.TimeoutExpired as error:
                raise DetectionError(f'Pytest run {run_number} timed out after {self.timeout:g}s') from error
            except OSError as error:
                raise DetectionError(f'Could not start pytest: {error}') from error
            if process.returncode not in (0, 1):
                detail = (process.stderr or process.stdout).strip()[-1500:]
                raise DetectionError(f'Pytest run {run_number} exited with code {process.returncode}.\n{detail}')
            try:
                report = json.loads(report_file.read_text(encoding='utf-8'))
                if not isinstance(report, dict) or report.get('exitcode') != process.returncode:
                    raise ValueError('Report exit code does not match pytest')
                tests = report.get('tests')
                if not isinstance(tests, list) or not tests:
                    raise ValueError('Report contains no test results')
                root = Path(report.get('root', self.pytest_cwd))
                parsed = [self._parse_result(test, root) for test in tests]
                if len({test.test_id for test in parsed}) != len(parsed):
                    raise ValueError('Report contains duplicate test IDs')
                return parsed
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise DetectionError(f'Invalid or missing report for run {run_number}: {error}') from error

    @staticmethod
    def _parse_result(test, root: Path) -> TestResult:
        if not isinstance(test, dict):
            raise ValueError('Invalid test record')
        node_id = test['nodeid']
        outcome = {'xfailed': 'skipped', 'xpassed': 'passed'}.get(test['outcome'], test['outcome'])
        if not isinstance(node_id, str) or not node_id or outcome not in ('passed', 'failed', 'error', 'skipped'):
            raise ValueError('Invalid test ID or outcome')
        error_message = ''
        duration = 0.0
        for stage in ('setup', 'call', 'teardown'):
            detail = test.get(stage, {})
            if not isinstance(detail, dict):
                raise ValueError('Invalid test stage')
            duration += float(detail.get('duration', 0))
            if detail.get('outcome') == 'failed':
                if stage != 'call':
                    outcome = 'error'
                explanation = detail.get('longrepr', '')
                error_message += str(explanation)[:1000] + '\n'
        file_path = Path(node_id.partition('::')[0])
        if not file_path.is_absolute():
            file_path = root / file_path
        return TestResult(node_id, outcome, duration, error_message.strip(), str(file_path))

    def _process_results(self, results: List[TestResult]) -> None:
        observed = {result.test_id for result in results}
        for test in self.results.values():
            if test.test_id not in observed:
                test.outcomes.append('missing')
                test.missing_count += 1
        for result in results:
            if result.test_id not in self.results:
                self.results[result.test_id] = FlakyTest(
                    test_id=result.test_id,
                    test_file=result.test_file or result.test_id.partition('::')[0],
                    test_function=result.test_id.partition('::')[2],
                    missing_count=self.completed_runs,
                    outcomes=['missing'] * self.completed_runs,
                )
            test = self.results[result.test_id]
            test.outcomes.append(result.outcome)
            test.durations.append(result.duration)
            attribute = {'passed': 'pass_count', 'failed': 'fail_count',
                         'error': 'error_count', 'skipped': 'skip_count'}[result.outcome]
            setattr(test, attribute, getattr(test, attribute) + 1)
            if result.error_message and result.error_message not in test.error_messages:
                test.error_messages.append(result.error_message)
        self.completed_runs += 1

    def get_flaky_tests(self) -> List[FlakyTest]:
        return sorted((test for test in self.results.values() if test.is_flaky),
                      key=lambda test: (-test.flakiness_score, test.test_id))

    def get_stable_tests(self) -> List[FlakyTest]:
        """Compatibility helper: tests with passes and no observed failures or omissions."""
        return [test for test in self.results.values() if test.status == 'passed']

    def to_report(self) -> dict:
        counts = Counter(test.status for test in self.results.values())
        tests = []
        for test in sorted(self.results.values(), key=lambda test: test.test_id):
            tests.append({
                'nodeid': test.test_id, 'file': test.test_file, 'status': test.status,
                'outcomes': test.outcomes, 'passed': test.pass_count, 'failed': test.fail_count,
                'errors': test.error_count, 'skipped': test.skip_count, 'missing': test.missing_count,
                'balance_score': test.flakiness_score, 'pattern': test.failure_pattern,
                'duration_seconds': sum(test.durations), 'failure_messages': test.error_messages,
            })
        return {
            'schema_version': 1,
            'status': 'incomplete' if any(test.missing_count for test in self.results.values()) else 'complete',
            'runs_requested': self.runs, 'runs_completed': self.completed_runs,
            'summary': {'total': len(tests),
                        'missing_observations': sum(test.missing_count for test in self.results.values()),
                        **{name: counts[name] for name in
                        ('flaky', 'failing', 'incomplete', 'passed', 'skipped')}},
            'tests': tests,
        }
