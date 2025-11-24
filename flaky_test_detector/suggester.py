"""
Repair suggester - Provides actionable fixes for flaky tests
"""

from typing import List
from dataclasses import dataclass

from .analyzer import FlakinessType, RootCause


@dataclass
class RepairSuggestion:
    """A suggested fix for a flaky test"""
    title: str
    description: str
    code_example: str
    priority: int  # 1-3, 1 = high priority


class RepairSuggester:
    """Generates repair suggestions based on root causes"""

    def suggest_repairs(self, causes: List[RootCause]) -> List[RepairSuggestion]:
        """Generate repair suggestions for identified root causes"""
        suggestions = []

        for cause in causes:
            if cause.type == FlakinessType.TIME_DEPENDENT:
                suggestions.extend(self._suggest_time_fixes())
            elif cause.type == FlakinessType.RANDOM_DEPENDENT:
                suggestions.extend(self._suggest_random_fixes())
            elif cause.type == FlakinessType.CONCURRENCY:
                suggestions.extend(self._suggest_concurrency_fixes())
            elif cause.type == FlakinessType.UNORDERED_COLLECTION:
                suggestions.extend(self._suggest_order_fixes())
            elif cause.type == FlakinessType.EXTERNAL_DEPENDENCY:
                suggestions.extend(self._suggest_external_fixes())
            elif cause.type == FlakinessType.FLOATING_POINT:
                suggestions.extend(self._suggest_float_fixes())
            elif cause.type == FlakinessType.GLOBAL_STATE:
                suggestions.extend(self._suggest_global_state_fixes())

        # Remove duplicates
        seen = set()
        unique_suggestions = []
        for suggestion in suggestions:
            if suggestion.title not in seen:
                seen.add(suggestion.title)
                unique_suggestions.append(suggestion)

        return sorted(unique_suggestions, key=lambda s: s.priority)

    def _suggest_time_fixes(self) -> List[RepairSuggestion]:
        """Suggestions for time-dependent tests"""
        return [
            RepairSuggestion(
                title="Mock datetime.now() with freezegun",
                description="Use freezegun to freeze time during test execution",
                code_example="""# Install: pip install freezegun
from freezegun import freeze_time

@freeze_time("2024-01-15 12:00:00")
def test_something():
    # Now datetime.now() always returns 2024-01-15 12:00:00
    result = my_function()
    assert result.date == datetime(2024, 1, 15)""",
                priority=1
            ),
            RepairSuggestion(
                title="Inject time as parameter",
                description="Pass time as a parameter instead of calling datetime.now() inside code",
                code_example="""# Instead of:
def process():
    now = datetime.now()
    return now.hour > 12

# Do this:
def process(current_time=None):
    if current_time is None:
        current_time = datetime.now()
    return current_time.hour > 12

# Test:
def test_process():
    test_time = datetime(2024, 1, 15, 14, 0)
    assert process(test_time) == True""",
                priority=1
            ),
        ]

    def _suggest_random_fixes(self) -> List[RepairSuggestion]:
        """Suggestions for random-dependent tests"""
        return [
            RepairSuggestion(
                title="Set random seed before test",
                description="Fix the random seed to make tests deterministic",
                code_example="""import random

def test_something():
    random.seed(42)  # Always same sequence
    result = my_random_function()
    assert result == expected_value""",
                priority=1
            ),
            RepairSuggestion(
                title="Use pytest fixtures for random data",
                description="Generate random test data in fixtures with fixed seed",
                code_example="""import pytest
import random

@pytest.fixture
def random_data():
    random.seed(42)
    return [random.randint(1, 100) for _ in range(10)]

def test_something(random_data):
    result = process(random_data)
    assert result == expected""",
                priority=1
            ),
            RepairSuggestion(
                title="Mock random module",
                description="Mock the random module to return predetermined values",
                code_example="""from unittest.mock import patch

def test_something():
    with patch('random.randint', return_value=42):
        result = my_function()
        assert result == expected""",
                priority=2
            ),
        ]

    def _suggest_concurrency_fixes(self) -> List[RepairSuggestion]:
        """Suggestions for concurrency issues"""
        return [
            RepairSuggestion(
                title="Add proper synchronization",
                description="Use locks, events, or other synchronization primitives",
                code_example="""import threading

lock = threading.Lock()

def test_concurrent():
    results = []

    def worker():
        with lock:
            results.append(do_work())

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 5""",
                priority=1
            ),
            RepairSuggestion(
                title="Use pytest-asyncio for async tests",
                description="Properly handle async tests with pytest-asyncio",
                code_example="""import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await my_async_function()
    assert result == expected""",
                priority=1
            ),
            RepairSuggestion(
                title="Add timeouts and retries",
                description="Add explicit timeouts for async operations",
                code_example="""import asyncio

async def test_with_timeout():
    try:
        result = await asyncio.wait_for(
            my_async_function(),
            timeout=5.0
        )
        assert result == expected
    except asyncio.TimeoutError:
        pytest.fail("Operation timed out")""",
                priority=2
            ),
        ]

    def _suggest_order_fixes(self) -> List[RepairSuggestion]:
        """Suggestions for order-dependent tests"""
        return [
            RepairSuggestion(
                title="Sort collections before comparison",
                description="Convert to sorted lists for deterministic ordering",
                code_example="""# Instead of:
assert result == {1, 2, 3}

# Do this:
assert sorted(result) == [1, 2, 3]

# Or for dicts:
assert sorted(result.items()) == sorted(expected.items())""",
                priority=1
            ),
            RepairSuggestion(
                title="Use ordered collections",
                description="Replace set/dict with list/OrderedDict when order matters",
                code_example="""from collections import OrderedDict

# Instead of:
data = {'a': 1, 'b': 2}

# Use:
data = OrderedDict([('a', 1), ('b', 2)])

# Or just use a list of tuples:
data = [('a', 1), ('b', 2)]""",
                priority=1
            ),
        ]

    def _suggest_external_fixes(self) -> List[RepairSuggestion]:
        """Suggestions for external dependency issues"""
        return [
            RepairSuggestion(
                title="Mock external dependencies",
                description="Use mocks instead of real external calls",
                code_example="""from unittest.mock import patch, Mock

def test_api_call():
    mock_response = Mock()
    mock_response.json.return_value = {'status': 'ok'}

    with patch('requests.get', return_value=mock_response):
        result = my_function_that_calls_api()
        assert result['status'] == 'ok'""",
                priority=1
            ),
            RepairSuggestion(
                title="Use pytest fixtures for test files",
                description="Create temporary files in fixtures",
                code_example="""import pytest
from pathlib import Path

@pytest.fixture
def test_file(tmp_path):
    file = tmp_path / "test.txt"
    file.write_text("test content")
    return file

def test_read_file(test_file):
    content = read_file(test_file)
    assert content == "test content" """,
                priority=1
            ),
            RepairSuggestion(
                title="Use responses library for HTTP",
                description="Mock HTTP requests with the responses library",
                code_example="""import responses
import requests

@responses.activate
def test_api():
    responses.add(
        responses.GET,
        'https://api.example.com/data',
        json={'status': 'ok'},
        status=200
    )

    result = fetch_data()
    assert result['status'] == 'ok'""",
                priority=2
            ),
        ]

    def _suggest_float_fixes(self) -> List[RepairSuggestion]:
        """Suggestions for floating point comparison issues"""
        return [
            RepairSuggestion(
                title="Use pytest.approx for float comparison",
                description="Compare floats with tolerance using pytest.approx",
                code_example="""import pytest

# Instead of:
assert result == 0.1 + 0.2  # May fail!

# Do this:
assert result == pytest.approx(0.3)

# Or with custom tolerance:
assert result == pytest.approx(0.3, abs=1e-6)""",
                priority=1
            ),
            RepairSuggestion(
                title="Use math.isclose()",
                description="Use math.isclose() for relative/absolute tolerance",
                code_example="""import math

# Instead of:
assert a == b

# Do this:
assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)""",
                priority=1
            ),
        ]

    def _suggest_global_state_fixes(self) -> List[RepairSuggestion]:
        """Suggestions for global state issues"""
        return [
            RepairSuggestion(
                title="Reset global state in fixtures",
                description="Use pytest fixtures to reset state before/after tests",
                code_example="""import pytest

@pytest.fixture(autouse=True)
def reset_global_state():
    # Setup
    original_value = MyClass.global_var
    yield
    # Teardown
    MyClass.global_var = original_value

def test_something():
    MyClass.global_var = 'new_value'
    # Test will not affect other tests""",
                priority=1
            ),
            RepairSuggestion(
                title="Mock environment variables",
                description="Use monkeypatch to temporarily set environment variables",
                code_example="""def test_with_env_var(monkeypatch):
    monkeypatch.setenv('MY_VAR', 'test_value')
    result = my_function()
    assert result == expected
    # Environment is automatically restored""",
                priority=1
            ),
            RepairSuggestion(
                title="Use dependency injection",
                description="Pass dependencies as parameters instead of using globals",
                code_example="""# Instead of:
CONFIG = {'debug': True}

def process():
    if CONFIG['debug']:
        print("Debug mode")

# Do this:
def process(config=None):
    config = config or {'debug': False}
    if config['debug']:
        print("Debug mode")

def test_process():
    result = process(config={'debug': True})
    assert result == expected""",
                priority=2
            ),
        ]
