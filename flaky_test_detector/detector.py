"""
Core flaky test detection engine
"""

import subprocess
import json
import tempfile
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class TestResult:
    """Single test execution result"""
    test_id: str
    outcome: str  # passed, failed, skipped, error
    duration: float
    error_message: str = ""


@dataclass
class FlakyTest:
    """Detected flaky test with execution history"""
    test_id: str
    test_file: str
    test_function: str
    pass_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    skip_count: int = 0
    outcomes: List[str] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)

    @property
    def flakiness_score(self) -> float:
        """
        Calculate flakiness score (0-1, higher = more flaky)
        Based on outcome entropy - maximum when results are evenly split
        """
        total = len(self.outcomes)
        if total == 0:
            return 0.0

        # Calculate entropy-based measure
        pass_ratio = self.pass_count / total
        fail_ratio = self.fail_count / total

        # Maximum flakiness at 50/50 split
        return min(pass_ratio, fail_ratio) * 2

    @property
    def is_flaky(self) -> bool:
        """Test is flaky if it has inconsistent outcomes"""
        unique_outcomes = set(self.outcomes)
        # Flaky if we have both passed and (failed or error)
        has_pass = 'passed' in unique_outcomes
        has_fail = 'failed' in unique_outcomes or 'error' in unique_outcomes
        return has_pass and has_fail

    @property
    def failure_pattern(self) -> str:
        """Describe the failure pattern"""
        if not self.is_flaky:
            return "stable"

        # Check for patterns
        outcomes_str = ''.join('P' if o == 'passed' else 'F' for o in self.outcomes)

        if outcomes_str.startswith('F') and 'P' in outcomes_str:
            return "initially_failing"
        elif outcomes_str.startswith('P') and 'F' in outcomes_str:
            return "initially_passing"
        elif outcomes_str.count('F') < 3:
            return "rarely_failing"
        elif outcomes_str.count('P') < 3:
            return "rarely_passing"
        else:
            return "intermittent"


class FlakyDetector:
    """Main detection engine"""

    def __init__(self, test_path: str, runs: int = 10, verbose: bool = False):
        self.test_path = Path(test_path).resolve()
        self.runs = runs
        self.verbose = verbose
        self.results: Dict[str, FlakyTest] = {}
        self.temp_dir = tempfile.mkdtemp()
        # Store current working directory - pytest runs from here
        self.pytest_cwd = Path.cwd()

    def run_detection(self) -> Dict[str, FlakyTest]:
        """Execute detection by running tests multiple times"""
        if self.verbose:
            print(f"Running tests {self.runs} times...")
            print(f"Test path: {self.test_path}")
            print("-" * 60)

        for run_num in range(1, self.runs + 1):
            if self.verbose:
                print(f"Run {run_num}/{self.runs}...", end=" ", flush=True)

            results = self._execute_single_run()
            self._process_results(results)

            if self.verbose:
                print(f"✓ ({len(results)} tests)")

        return self.results

    def _execute_single_run(self) -> List[TestResult]:
        """Execute a single test run"""
        report_file = Path(self.temp_dir) / f"report_{id(self)}.json"

        cmd = [
            "pytest",
            str(self.test_path),
            "--json-report",
            f"--json-report-file={report_file}",
            "-v",
            "--tb=short",
            "-q",
            "--disable-warnings",
        ]

        # Run pytest (suppress output unless verbose)
        # Don't change cwd - run from current directory so paths match
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        # Parse JSON report
        try:
            with open(report_file, "r") as f:
                report = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            if self.verbose:
                print(f"\nWarning: Could not read report: {e}")
            return []

        # Extract test results
        test_results = []
        for test in report.get("tests", []):
            error_msg = ""
            if test["outcome"] in ["failed", "error"]:
                error_msg = test.get("call", {}).get("longrepr", "")[:200]

            test_results.append(TestResult(
                test_id=test["nodeid"],
                outcome=test["outcome"],
                duration=test.get("duration", 0.0),
                error_message=error_msg
            ))

        return test_results

    def _process_results(self, results: List[TestResult]) -> None:
        """Process results from a single run"""
        for result in results:
            test_id = result.test_id

            # Parse test ID
            parts = test_id.split("::")
            test_file = parts[0] if parts else "unknown"
            test_function = parts[-1] if parts else "unknown"

            # Initialize if new test
            if test_id not in self.results:
                self.results[test_id] = FlakyTest(
                    test_id=test_id,
                    test_file=test_file,
                    test_function=test_function
                )

            # Update test data
            flaky_test = self.results[test_id]
            flaky_test.outcomes.append(result.outcome)

            if result.outcome == "passed":
                flaky_test.pass_count += 1
            elif result.outcome == "failed":
                flaky_test.fail_count += 1
                flaky_test.error_messages.append(result.error_message)
            elif result.outcome == "error":
                flaky_test.error_count += 1
                flaky_test.error_messages.append(result.error_message)
            elif result.outcome == "skipped":
                flaky_test.skip_count += 1

    def get_flaky_tests(self) -> List[FlakyTest]:
        """Return detected flaky tests sorted by flakiness score"""
        flaky = [test for test in self.results.values() if test.is_flaky]
        return sorted(flaky, key=lambda t: t.flakiness_score, reverse=True)

    def get_stable_tests(self) -> List[FlakyTest]:
        """Return stable (non-flaky) tests"""
        return [test for test in self.results.values() if not test.is_flaky]
