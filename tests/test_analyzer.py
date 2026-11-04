from pathlib import Path

from flaky_test_detector.analyzer import FlakinessType, RootCauseAnalyzer


def analyze(tmp_path, source, selector='test_case'):
    path = tmp_path / 'test_sample.py'
    path.write_text(source)
    return RootCauseAnalyzer(path).analyze(selector)


def test_comments_docstrings_and_strings_do_not_create_hints(tmp_path):
    hints = analyze(tmp_path, '''def test_case():
    """random.randint() requests.get()"""
    # time.sleep(1)
    text = 'threading.Thread()'
    assert text
''')
    assert hints == []


def test_import_aliases_and_async_parameterized_class_selector(tmp_path):
    source = '''import time as clock
from random import randint as draw
class TestA:
    async def test_same(self):
        clock.sleep(0.1)
        assert draw(0, 1) == 1
class TestB:
    def test_same(self):
        pass
'''
    hints = analyze(tmp_path, source, 'TestA::test_same[case with spaces]')
    assert {hint.type for hint in hints} == {FlakinessType.TIME_DEPENDENT, FlakinessType.RANDOM_DEPENDENT}
    assert {line for hint in hints for line in hint.line_numbers} == {5, 6}
    assert analyze(tmp_path, source, 'TestB::test_same') == []
    assert analyze(tmp_path, source, 'test_same') == []  # Ambiguous, rather than guessed.


def test_nested_function_body_is_not_attributed_to_parent(tmp_path):
    assert analyze(tmp_path, '''def test_case():
    def never_called():
        import random
        return random.randint(0, 1)
    assert True
''') == []


def test_seeded_random_use_is_not_claimed_to_be_unseeded(tmp_path):
    hints = analyze(tmp_path, '''import random
def test_case():
    random.seed(42)
    assert random.randint(0, 1) == 0
''')
    assert len(hints) == 1
    assert 'without' not in hints[0].description
    assert hints[0].confidence == 0


def test_dict_order_is_not_treated_as_undefined(tmp_path):
    assert analyze(tmp_path, '''def test_case():
    data = {'first': 1, 'second': 2}
    assert list(data.keys())[0] == 'first'
''') == []


def test_float_assertion_and_environment_mutation_are_hints(tmp_path):
    hints = analyze(tmp_path, '''import os
def test_case():
    os.environ['EXAMPLE'] = 'value'
    assert 0.1 + 0.2 == 0.3
''')
    assert {hint.type for hint in hints} == {FlakinessType.GLOBAL_STATE, FlakinessType.FLOATING_POINT}
