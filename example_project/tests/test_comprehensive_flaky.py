"""
Comprehensive test suite with many different types of flaky tests
Each test demonstrates a specific flakiness pattern
"""

import random
import time
import os
import sys
import threading
import asyncio
from datetime import datetime, timedelta
from example_project.app import (
    get_greeting,
    generate_user_id,
    generate_uuid,
    process_unordered_data,
    get_dict_data,
    calculate_average,
    calculate_with_precision,
    async_operation,
    timed_operation,
    is_expired,
    shuffle_list,
    increment_counter,
    get_counter,
    reset_counter,
    DataStore,
    ThreadSafeCounter,
    async_fetch_data,
)


# ============================================================================
# TIME-DEPENDENT FLAKY TESTS
# ============================================================================

def test_time_greeting_morning_only():
    """FLAKY: Only passes in the morning (before noon)"""
    greeting = get_greeting()
    assert "morning" in greeting.lower()


def test_timestamp_expiration():
    """FLAKY: Depends on current time for expiration check"""
    # Create timestamp 59 minutes ago
    old_timestamp = datetime.now() - timedelta(minutes=59)
    # Sometimes passes (if test is fast), sometimes fails (if slow or at boundary)
    assert not is_expired(old_timestamp)


def test_datetime_comparison():
    """FLAKY: Comparing datetime.now() calls"""
    time1 = datetime.now()
    time.sleep(0.00001)  # Very short sleep
    time2 = datetime.now()
    # May fail if system is too fast to measure
    assert time2 > time1


def test_hour_boundary():
    """FLAKY: Behavior changes at hour boundaries"""
    hour = datetime.now().hour
    # Flaky when test runs exactly at hour change (e.g., 11:59:59 vs 12:00:00)
    time.sleep(0.001)
    hour2 = datetime.now().hour
    assert hour == hour2


# ============================================================================
# RANDOM-DEPENDENT FLAKY TESTS
# ============================================================================

def test_random_user_generation():
    """FLAKY: Random user ID in specific range"""
    user_id = generate_user_id()
    user_num = int(user_id.split('_')[1])
    # ~50% pass rate
    assert user_num < 5500


def test_uuid_collision():
    """FLAKY: UUID generation (extremely rare but possible collision)"""
    uuid1 = generate_uuid()
    uuid2 = generate_uuid()
    # Should always pass but demonstrates UUID randomness
    assert uuid1 != uuid2
    # Add flakiness: check if UUID starts with specific char (1/16 chance)
    assert uuid1[0] in '0123456789a'  # ~62.5% pass rate


def test_random_shuffle_order():
    """FLAKY: Depends on shuffle order"""
    items = [1, 2, 3, 4, 5]
    shuffled = shuffle_list(items.copy())
    # Expect first element to be 1 or 2 (~40% pass rate)
    assert shuffled[0] in [1, 2]


def test_random_choice_specific():
    """FLAKY: Random choice expects specific value"""
    choices = ['a', 'b', 'c', 'd', 'e']
    result = random.choice(choices)
    # 40% pass rate
    assert result in ['a', 'b']


def test_random_range():
    """FLAKY: Random integer in range"""
    value = random.randint(1, 100)
    # 30% pass rate
    assert value < 30


# ============================================================================
# UNORDERED COLLECTION FLAKY TESTS
# ============================================================================

def test_set_ordering():
    """FLAKY: Set order is not guaranteed"""
    result = process_unordered_data([1, 2, 3, 4, 5])
    result_list = list(result)
    # Check if first element is one of the smaller values
    assert result_list[0] in [2, 4]  # ~40% pass rate


def test_dict_keys_order():
    """FLAKY: Dict keys iteration order"""
    data = get_dict_data()
    keys = list(data.keys())
    # Assume first key is 'z' (may not be true depending on dict implementation)
    assert keys[0] == 'z'


def test_set_intersection():
    """FLAKY: Set operations with ordering assumptions"""
    set1 = {1, 2, 3, 4, 5}
    set2 = {3, 4, 5, 6, 7}
    intersection = set1 & set2
    result_list = list(intersection)
    # Assume specific ordering
    assert result_list[0] == 3


def test_dict_values_iteration():
    """FLAKY: Iterating dict values"""
    data = {'x': 10, 'y': 20, 'z': 30}
    values = list(data.values())
    # Assume first value
    assert values[0] in [10, 20]  # ~66% pass rate


# ============================================================================
# FLOATING-POINT FLAKY TESTS
# ============================================================================

def test_float_equality():
    """FLAKY: Exact float comparison"""
    result = calculate_average([0.1, 0.1, 0.1])
    # May be 0.30000000000000004 due to floating point precision
    assert result == 0.3


def test_float_division():
    """FLAKY: Division with floating point"""
    result = 1.0 / 3.0 * 3.0
    # May not be exactly 1.0
    assert result == 1.0


def test_complex_float_calculation():
    """FLAKY: Complex calculation with multiple operations"""
    result = calculate_with_precision(0.1, 0.2, 0.3)
    expected = (0.1 * 0.2) / 0.3 + (0.1 - 0.2) * 0.3
    # Exact comparison may fail
    assert result == expected


def test_float_accumulation():
    """FLAKY: Accumulating float errors"""
    total = 0.0
    for _ in range(10):
        total += 0.1
    # Should be 1.0 but may be 0.9999999999999999
    assert total == 1.0


# ============================================================================
# CONCURRENCY FLAKY TESTS
# ============================================================================

def test_thread_race_condition():
    """FLAKY: Race condition with threads"""
    counter = ThreadSafeCounter()

    def worker():
        for _ in range(50):
            counter.increment()  # No lock!

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Should be 150, but race condition causes random results
    assert counter.value == 150


def test_threading_counter_increment():
    """FLAKY: Multiple threads incrementing counter"""
    counter = {'value': 0}

    def increment():
        for _ in range(30):
            current = counter['value']
            time.sleep(0.00001)
            counter['value'] = current + 1

    threads = [threading.Thread(target=increment) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Should be 120, but race condition causes < 120
    assert counter['value'] == 120


def test_async_timing():
    """FLAKY: Async operation with timing"""
    async def run_test():
        start = time.time()
        await async_fetch_data()
        duration = time.time() - start
        # Random sleep makes this unpredictable
        return duration < 0.004

    result = asyncio.run(run_test())
    assert result


# ============================================================================
# GLOBAL STATE FLAKY TESTS
# ============================================================================

def test_global_counter_state():
    """FLAKY: Modifies global counter"""
    reset_counter()
    increment_counter()
    increment_counter()
    # This test modifies global state
    assert get_counter() == 2


def test_depends_on_counter():
    """FLAKY: Depends on global counter state from previous test"""
    # May pass or fail depending on test execution order
    current = get_counter()
    assert current > 0  # Assumes previous test ran


def test_datastore_pollution():
    """FLAKY: Modifies shared DataStore"""
    DataStore.save("test_key", "value1")
    DataStore.save("counter", 10)
    assert DataStore.get("test_key") == "value1"
    # Not cleaning up!


def test_depends_on_datastore():
    """FLAKY: Depends on DataStore state"""
    # May have data from previous test or not
    value = DataStore.get("test_key")
    assert value is not None


def test_environment_variable():
    """FLAKY: Modifies environment variable"""
    os.environ['TEST_VAR'] = 'test_value'
    assert os.environ.get('TEST_VAR') == 'test_value'
    # Not cleaning up


def test_depends_on_env():
    """FLAKY: Depends on environment variable"""
    value = os.environ.get('TEST_VAR')
    assert value == 'test_value'


# ============================================================================
# TIMING-DEPENDENT FLAKY TESTS
# ============================================================================

def test_operation_timing():
    """FLAKY: Expects operation to complete within time"""
    start = time.time()
    async_operation()  # Random sleep between 0.001-0.01
    duration = time.time() - start
    # May fail if random sleep is > 0.005
    assert duration < 0.005


def test_sleep_precision():
    """FLAKY: Sleep precision varies"""
    duration = timed_operation(1)  # 1ms sleep
    # Actual duration may vary
    assert 0.0009 <= duration <= 0.0011


def test_timeout_boundary():
    """FLAKY: At timeout boundary"""
    start = time.time()
    time.sleep(0.0001)  # Very short sleep
    elapsed = time.time() - start
    # May fail if too fast to measure
    assert elapsed >= 0.00009


# ============================================================================
# EXTERNAL DEPENDENCY FLAKY TESTS (simulated)
# ============================================================================

def test_file_write_read():
    """FLAKY: File I/O timing"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        filename = f.name
        f.write("test")

    # Sometimes file isn't immediately available
    time.sleep(0.00001)  # Very short delay

    with open(filename) as f:
        content = f.read()

    os.unlink(filename)
    # May fail if file I/O is slow
    assert content == "test"


# ============================================================================
# STABLE TESTS (for comparison)
# ============================================================================

def test_stable_addition():
    """STABLE: Simple arithmetic"""
    assert 2 + 2 == 4


def test_stable_string():
    """STABLE: String operation"""
    assert "hello".upper() == "HELLO"


def test_stable_list():
    """STABLE: List comparison"""
    assert [1, 2, 3] == [1, 2, 3]


def test_stable_dict():
    """STABLE: Dict comparison"""
    assert {"a": 1, "b": 2} == {"a": 1, "b": 2}


def test_stable_sorted():
    """STABLE: Sorted comparison"""
    assert sorted([3, 1, 2]) == [1, 2, 3]


def test_stable_float_approx():
    """STABLE: Proper float comparison"""
    import pytest
    result = calculate_average([0.1, 0.1, 0.1])
    assert result == pytest.approx(0.3)


def test_stable_with_seed():
    """STABLE: Random with seed"""
    random.seed(42)
    value = random.randint(1, 100)
    assert value == 81  # Deterministic with seed


def test_stable_set_sorted():
    """STABLE: Set comparison with sorting"""
    result = process_unordered_data([1, 2, 3])
    assert sorted(result) == [2, 4, 6]
