"""Static code hints for investigation; these do not establish a root cause."""

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List


class FlakinessType(Enum):
    TIME_DEPENDENT = 'time_dependent'
    RANDOM_DEPENDENT = 'random_dependent'
    ORDER_DEPENDENT = 'order_dependent'
    CONCURRENCY = 'concurrency'
    EXTERNAL_DEPENDENCY = 'external_dependency'
    FLOATING_POINT = 'floating_point'
    UNORDERED_COLLECTION = 'unordered_collection'
    GLOBAL_STATE = 'global_state'
    UNKNOWN = 'unknown'


@dataclass
class RootCause:
    type: FlakinessType
    description: str
    line_numbers: List[int]
    code_snippets: List[str]
    confidence: float = 0.0  # Kept for API compatibility; not a calibrated probability.


class RootCauseAnalyzer:
    def __init__(self, test_file: Path):
        self.test_file = Path(test_file)
        self.tree = None
        self.source_code = ''
        self.aliases = {}
        try:
            self.source_code = self.test_file.read_text(encoding='utf-8')
            self.tree = ast.parse(self.source_code)
        except (OSError, UnicodeError, SyntaxError):
            return
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.aliases[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    self.aliases[alias.asname or alias.name] = f'{node.module}.{alias.name}'

    def _find_function(self, selector):
        wanted = tuple(selector.split('[', 1)[0].split('::'))
        matches = []

        def visit(node, scope=()):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    path = scope + (child.name,)
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if path == wanted or (len(wanted) == 1 and child.name == wanted[0]):
                            matches.append(child)
                    visit(child, path)
                else:
                    visit(child, scope)
        visit(self.tree)
        return matches[0] if len(matches) == 1 else None

    def _name(self, node):
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self._name(node.value)
            return f'{base}.{node.attr}' if base else node.attr
        return ''

    def analyze(self, test_function_name: str) -> List[RootCause]:
        if self.tree is None:
            return []
        function = self._find_function(test_function_name)
        if function is None:
            return []
        evidence = {}

        def add(kind, description, node):
            item = evidence.setdefault(kind, (description, set()))
            item[1].add(node.lineno)

        def walk(node):
            # A nested function's body is not executed merely by defining it.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                return
            if isinstance(node, ast.Call):
                name = self._name(node.func)
                if name.startswith(('time.', 'datetime.')) and name.rsplit('.', 1)[-1] in (
                    'time', 'monotonic', 'perf_counter', 'sleep', 'now', 'utcnow', 'today'):
                    add(FlakinessType.TIME_DEPENDENT, 'Time or scheduling is used; check clocks and timing assumptions.', node)
                if ((name.startswith(('random.', 'numpy.random.', 'secrets.'))
                     and name.rsplit('.', 1)[-1] not in ('seed', 'Random')) or name == 'uuid.uuid4'):
                    add(FlakinessType.RANDOM_DEPENDENT, 'Random values are used; check deterministic inputs and RNG state.', node)
                if name.startswith(('threading.', 'asyncio.', 'multiprocessing.', 'concurrent.futures.')):
                    add(FlakinessType.CONCURRENCY, 'Concurrent operations are used; check synchronization and cleanup.', node)
                if name in ('set', 'frozenset'):
                    add(FlakinessType.UNORDERED_COLLECTION, 'A set is used; check whether assertions depend on iteration order.', node)
                if (name == 'open' or name.startswith(('requests.', 'httpx.', 'aiohttp.', 'socket.', 'urllib.'))
                        or name.rsplit('.', 1)[-1] in ('read_text', 'write_text', 'read_bytes', 'write_bytes')):
                    add(FlakinessType.EXTERNAL_DEPENDENCY, 'External I/O is used; check isolation and resource availability.', node)
            if isinstance(node, (ast.Set, ast.SetComp)):
                add(FlakinessType.UNORDERED_COLLECTION, 'A set is used; check whether assertions depend on iteration order.', node)
            if isinstance(node, ast.Await):
                add(FlakinessType.CONCURRENCY, 'Async scheduling is used; check synchronization and cleanup.', node)
            if isinstance(node, ast.Assert):
                for comparison in ast.walk(node.test):
                    if (isinstance(comparison, ast.Compare)
                            and any(isinstance(operator, (ast.Eq, ast.NotEq)) for operator in comparison.ops)
                            and any(isinstance(value, ast.Constant) and isinstance(value.value, float)
                                    for value in ast.walk(comparison))):
                        add(FlakinessType.FLOATING_POINT, 'An exact comparison contains a float; check numeric tolerance.', comparison)
            if isinstance(node, ast.Global):
                add(FlakinessType.GLOBAL_STATE, 'Global state is accessed; check isolation between tests.', node)
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete)):
                targets = node.targets if hasattr(node, 'targets') else [node.target]
                if any(self._name(target.value) == 'os.environ'
                       for target in targets if isinstance(target, ast.Subscript)):
                    add(FlakinessType.GLOBAL_STATE, 'Environment variables are modified; check restoration after the test.', node)
            for child in ast.iter_child_nodes(node):
                walk(child)

        for statement in function.body:
            walk(statement)
        lines = self.source_code.splitlines()
        return [RootCause(kind, description, sorted(numbers), [lines[number - 1].strip() for number in sorted(numbers)])
                for kind, (description, numbers) in evidence.items()]
