"""
Intentionally flaky tests demonstrating common flakiness patterns
"""

import random
import time
import threading
from datetime import datetime
from example_project.app import (
    get_greeting,
    generate_user_id,
    process_unordered_data,
    calculate_average,
    async_operation,
    DataStore
)


def test_time_dependent_greeting():
    """FLAKY: Depends on current time of day - genuinely flaky at certain hours"""
    greeting = get_greeting()
    # This test is truly flaky - passes in morning/afternoon, fails in evening
    # But specifically around hour boundaries (11:59 vs 12:00) it becomes very flaky
    assert greeting in ["Good morning", "Good afternoon"]


def test_random_user_id():
    """FLAKY: Uses random values without seed - truly random pass/fail"""
    user_id = generate_user_id()
    # Check if user_id is in a range - will randomly pass/fail
    user_num = int(user_id.split('_')[1])
    # 50/50 chance of passing (numbers 1000-5499 pass, 5500-9999 fail)
    assert user_num < 5500


def test_unordered_set():
    """FLAKY: Depends on set ordering - hash randomization causes flakiness"""
    result = process_unordered_data([1, 2, 3])
    result_list = list(result)
    # Set order varies, but we check first element is one of the valid values
    # Sometimes it's 2, sometimes 4, sometimes 6 - we assert it's "small"
    # This passes ~33% of time when first element is 2
    assert result_list[0] in [2, 4]  # Will pass sometimes (when 2 or 4 is first)


def test_floating_point_comparison():
    """FLAKY: Exact float comparison with accumulated rounding errors"""
    # Use different operations that sometimes hit exact 0.3, sometimes don't
    values = [0.1, 0.1, 0.1]
    result = sum(values) / len(values)
    # Sometimes this is exactly 0.3, sometimes 0.30000000000000004
    # Let's make it more reliably flaky with additional operations
    result = result + 0.1 - 0.1  # More rounding opportunities
    assert result == 0.3


def test_race_condition():
    """FLAKY: Race condition with threads"""
    counter = {'value': 0}

    def increment():
        for _ in range(100):
            current = counter['value']
            time.sleep(0.0001)  # Simulate some work
            counter['value'] = current + 1

    threads = [threading.Thread(target=increment) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Should be 300, but race condition causes random results
    assert counter['value'] == 300


def test_timing_dependent():
    """FLAKY: Depends on operation timing"""
    start = time.time()
    async_operation()
    duration = time.time() - start

    # Random sleep makes this unpredictable
    assert duration < 0.005


def test_global_state_pollution():
    """FLAKY: Modifies global state affecting other tests"""
    DataStore.save("test_key", "test_value")
    # Not cleaning up - will affect other tests
    assert DataStore.get("test_key") == "test_value"


def test_depends_on_previous_test():
    """FLAKY: Depends on previous test's global state"""
    # May pass or fail depending on test execution order
    value = DataStore.get("test_key")
    assert value == "test_value"


def test_dict_ordering():
    """FLAKY: Relies on dict key ordering"""
    data = {'z': 1, 'a': 2, 'b': 3}
    keys = list(data.keys())
    # In Python 3.7+ dicts are ordered, but this could still be flaky
    # if data comes from external source
    first_key = keys[0]
    assert first_key == 'z'


def test_random_without_seed():
    """FLAKY: Random choice without seed - 40% pass rate"""
    choices = [1, 2, 3, 4, 5]
    result = random.choice(choices)
    # Passes 40% of time (when result is 1 or 2)
    assert result in [1, 2]


def test_timestamp_comparison():
    """FLAKY: Timestamp comparison - passes sometimes based on system load"""
    before = datetime.now()
    # Very short sleep makes this genuinely flaky
    time.sleep(0.0001)  # 0.1ms - sometimes too fast to measure
    after = datetime.now()

    # This will pass sometimes (when measured), fail sometimes (when too fast)
    duration = (after - before).total_seconds()
    assert duration >= 0.00009  # Just below sleep time, genuinely flaky


# Add some stable tests for comparison
def test_stable_addition():
    """STABLE: Simple deterministic test"""
    assert 2 + 2 == 4


def test_stable_string():
    """STABLE: Simple string test"""
    assert "hello".upper() == "HELLO"


def test_stable_list():
    """STABLE: Simple list test"""
    assert [1, 2, 3] == [1, 2, 3]
