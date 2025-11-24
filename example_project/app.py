"""
Example application code that demonstrates various flakiness scenarios
"""

import random
import time
import os
import json
import threading
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
from uuid import uuid4


def get_greeting():
    """Returns greeting based on current time"""
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 18:
        return "Good afternoon"
    else:
        return "Good evening"


def generate_user_id():
    """Generate random user ID"""
    return f"user_{random.randint(1000, 9999)}"


def generate_uuid():
    """Generate UUID"""
    return str(uuid4())


def process_unordered_data(data: List[int]) -> set:
    """Process data and return as set"""
    return {x * 2 for x in data}


def get_dict_data() -> Dict:
    """Returns dict with data"""
    return {"z": 1, "a": 2, "m": 3, "b": 4}


def calculate_average(numbers: List[float]) -> float:
    """Calculate average of numbers"""
    return sum(numbers) / len(numbers)


def calculate_with_precision(a: float, b: float, c: float) -> float:
    """Complex calculation with multiple operations"""
    return (a * b) / c + (a - b) * c


def async_operation():
    """Simulates async operation with variable timing"""
    time.sleep(random.uniform(0.001, 0.01))
    return "completed"


def timed_operation(timeout_ms: int):
    """Operation with timeout"""
    start = time.time()
    time.sleep(timeout_ms / 1000.0)
    return time.time() - start


def is_expired(timestamp: datetime) -> bool:
    """Check if timestamp is expired (older than 1 hour)"""
    return datetime.now() - timestamp > timedelta(hours=1)


def shuffle_list(items: List) -> List:
    """Shuffle list using random"""
    random.shuffle(items)
    return items


# Global counter
_counter = 0

def increment_counter():
    """Increment global counter"""
    global _counter
    _counter += 1
    return _counter


def get_counter():
    """Get counter value"""
    return _counter


def reset_counter():
    """Reset counter"""
    global _counter
    _counter = 0


class DataStore:
    """Simple data store with global state"""
    cache = {}

    @classmethod
    def save(cls, key: str, value: any):
        cls.cache[key] = value

    @classmethod
    def get(cls, key: str):
        return cls.cache.get(key)

    @classmethod
    def clear(cls):
        cls.cache.clear()


class ThreadSafeCounter:
    """Counter with threading support"""
    def __init__(self):
        self.value = 0
        self.lock = threading.Lock()

    def increment(self):
        # Intentionally not using lock to create race condition
        current = self.value
        time.sleep(0.0001)  # Simulate work
        self.value = current + 1

    def increment_safe(self):
        with self.lock:
            current = self.value
            time.sleep(0.0001)
            self.value = current + 1


async def async_fetch_data():
    """Async function that takes variable time"""
    await asyncio.sleep(random.uniform(0.001, 0.005))
    return {"status": "ok", "data": [1, 2, 3]}
