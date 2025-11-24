"""
Root cause analyzer - Identifies likely causes of test flakiness
"""

import ast
import re
from pathlib import Path
from typing import List, Dict, Set
from dataclasses import dataclass
from enum import Enum


class FlakinessType(Enum):
    """Types of flakiness causes"""
    TIME_DEPENDENT = "time_dependent"
    RANDOM_DEPENDENT = "random_dependent"
    ORDER_DEPENDENT = "order_dependent"
    CONCURRENCY = "concurrency"
    EXTERNAL_DEPENDENCY = "external_dependency"
    FLOATING_POINT = "floating_point"
    UNORDERED_COLLECTION = "unordered_collection"
    GLOBAL_STATE = "global_state"
    UNKNOWN = "unknown"


@dataclass
class RootCause:
    """Identified root cause of flakiness"""
    type: FlakinessType
    description: str
    line_numbers: List[int]
    code_snippets: List[str]
    confidence: float  # 0-1


class RootCauseAnalyzer:
    """Analyzes test code to identify likely causes of flakiness"""

    # Patterns indicating different types of flakiness
    TIME_PATTERNS = [
        r'\bdatetime\.now\(\)',
        r'\btime\.time\(\)',
        r'\btime\.sleep\(',
        r'\btimestamp\b',
        r'\btoday\(\)',
        r'\butcnow\(\)',
    ]

    RANDOM_PATTERNS = [
        r'\brandom\.',
        r'\buuid\.uuid4\(\)',
        r'\bgenerate_uuid\(',
        r'\bgenerate_user_id\(',
        r'\bshuffle\(',
        r'\bshuffle_list\(',
        r'\bchoice\(',
        r'\brandint\(',
        r'\brandrange\(',
        r'\buuid4\(',
    ]

    CONCURRENCY_PATTERNS = [
        r'\bthreading\.',
        r'\bThread\(',
        r'\basyncio\.',
        r'\basync def\b',
        r'\bawait\b',
        r'\bmultiprocessing\.',
        r'\bPool\(',
    ]

    ORDER_PATTERNS = [
        r'\bset\(',
        r'\bdict\.keys\(\)',
        r'\bdict\.values\(\)',
        r'\bdict\.items\(\)',
        r'\.json\(\)',  # JSON dict ordering can vary
    ]

    EXTERNAL_PATTERNS = [
        r'\brequests\.',
        r'\bhttp',
        r'\burl',
        r'\bapi',
        r'\bsocket\.',
        r'\bopen\(',
        r'\.read\(',
        r'\.write\(',
    ]

    FLOAT_PATTERNS = [
        r'assert.*==.*\d+\.\d+',
        r'assertEqual.*\d+\.\d+',
    ]

    GLOBAL_STATE_PATTERNS = [
        r'\bglobal\b',
        r'\b__class__\.',
        r'\bsys\.',
        r'\bos\.environ',
    ]

    def __init__(self, test_file: Path):
        self.test_file = test_file
        self.source_code = ""
        self.tree = None

        if test_file.exists():
            self.source_code = test_file.read_text()
            try:
                self.tree = ast.parse(self.source_code)
            except SyntaxError:
                pass

    def analyze(self, test_function_name: str) -> List[RootCause]:
        """Analyze a specific test function for flakiness causes"""
        if not self.tree:
            return [RootCause(
                type=FlakinessType.UNKNOWN,
                description="Could not parse test file",
                line_numbers=[],
                code_snippets=[],
                confidence=0.0
            )]

        # Extract the test function
        test_func = self._find_function(test_function_name)
        if not test_func:
            return []

        causes = []

        # Extract function source
        func_source = ast.get_source_segment(self.source_code, test_func)
        if not func_source:
            return []

        func_lines = func_source.split('\n')
        func_start_line = test_func.lineno

        # Check for different patterns
        causes.extend(self._check_time_dependency(func_source, func_lines, func_start_line))
        causes.extend(self._check_random_dependency(func_source, func_lines, func_start_line))
        causes.extend(self._check_concurrency(func_source, func_lines, func_start_line))
        causes.extend(self._check_order_dependency(func_source, func_lines, func_start_line))
        causes.extend(self._check_external_dependency(func_source, func_lines, func_start_line))
        causes.extend(self._check_floating_point(func_source, func_lines, func_start_line))
        causes.extend(self._check_global_state(func_source, func_lines, func_start_line))

        return causes if causes else [RootCause(
            type=FlakinessType.UNKNOWN,
            description="No obvious flakiness pattern detected",
            line_numbers=[],
            code_snippets=[],
            confidence=0.1
        )]

    def _find_function(self, func_name: str) -> ast.FunctionDef:
        """Find function definition in AST"""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                return node
        return None

    def _check_pattern(self, source: str, patterns: List[str],
                       lines: List[str], start_line: int) -> List[tuple]:
        """Check for pattern matches and return (line_num, snippet) tuples"""
        matches = []
        for i, line in enumerate(lines):
            for pattern in patterns:
                if re.search(pattern, line):
                    matches.append((start_line + i, line.strip()))
                    break
        return matches

    def _check_time_dependency(self, source: str, lines: List[str],
                                start_line: int) -> List[RootCause]:
        """Check for time-dependent code"""
        matches = self._check_pattern(source, self.TIME_PATTERNS, lines, start_line)
        if matches:
            return [RootCause(
                type=FlakinessType.TIME_DEPENDENT,
                description="Test uses current time/date which changes between runs",
                line_numbers=[m[0] for m in matches],
                code_snippets=[m[1] for m in matches],
                confidence=0.9
            )]
        return []

    def _check_random_dependency(self, source: str, lines: List[str],
                                  start_line: int) -> List[RootCause]:
        """Check for random number generation"""
        matches = self._check_pattern(source, self.RANDOM_PATTERNS, lines, start_line)
        if matches:
            return [RootCause(
                type=FlakinessType.RANDOM_DEPENDENT,
                description="Test uses random values without setting seed",
                line_numbers=[m[0] for m in matches],
                code_snippets=[m[1] for m in matches],
                confidence=0.95
            )]
        return []

    def _check_concurrency(self, source: str, lines: List[str],
                           start_line: int) -> List[RootCause]:
        """Check for concurrency issues"""
        matches = self._check_pattern(source, self.CONCURRENCY_PATTERNS, lines, start_line)
        if matches:
            return [RootCause(
                type=FlakinessType.CONCURRENCY,
                description="Test involves threading/async code with potential race conditions",
                line_numbers=[m[0] for m in matches],
                code_snippets=[m[1] for m in matches],
                confidence=0.8
            )]
        return []

    def _check_order_dependency(self, source: str, lines: List[str],
                                 start_line: int) -> List[RootCause]:
        """Check for unordered collection usage"""
        matches = self._check_pattern(source, self.ORDER_PATTERNS, lines, start_line)
        if matches:
            return [RootCause(
                type=FlakinessType.UNORDERED_COLLECTION,
                description="Test relies on ordering of sets/dicts which is not guaranteed",
                line_numbers=[m[0] for m in matches],
                code_snippets=[m[1] for m in matches],
                confidence=0.7
            )]
        return []

    def _check_external_dependency(self, source: str, lines: List[str],
                                    start_line: int) -> List[RootCause]:
        """Check for external dependencies"""
        matches = self._check_pattern(source, self.EXTERNAL_PATTERNS, lines, start_line)
        if matches:
            return [RootCause(
                type=FlakinessType.EXTERNAL_DEPENDENCY,
                description="Test depends on external resources (network, filesystem, etc.)",
                line_numbers=[m[0] for m in matches],
                code_snippets=[m[1] for m in matches],
                confidence=0.6
            )]
        return []

    def _check_floating_point(self, source: str, lines: List[str],
                               start_line: int) -> List[RootCause]:
        """Check for floating point comparisons"""
        matches = self._check_pattern(source, self.FLOAT_PATTERNS, lines, start_line)
        if matches:
            return [RootCause(
                type=FlakinessType.FLOATING_POINT,
                description="Test uses exact floating point comparison which may fail due to rounding",
                line_numbers=[m[0] for m in matches],
                code_snippets=[m[1] for m in matches],
                confidence=0.85
            )]
        return []

    def _check_global_state(self, source: str, lines: List[str],
                            start_line: int) -> List[RootCause]:
        """Check for global state modification"""
        matches = self._check_pattern(source, self.GLOBAL_STATE_PATTERNS, lines, start_line)
        if matches:
            return [RootCause(
                type=FlakinessType.GLOBAL_STATE,
                description="Test modifies global state which may affect other tests",
                line_numbers=[m[0] for m in matches],
                code_snippets=[m[1] for m in matches],
                confidence=0.75
            )]
        return []
