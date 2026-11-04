"""Controlled example: one pass, one persistent failure, and one mixed outcome."""

import os


def test_passes():
    assert 2 + 2 == 4


def test_alternates():
    # The detector sets this metadata for each fresh pytest process.
    run = int(os.environ.get('FLAKY_DETECTOR_RUN', '1'))
    assert run % 2 == 1, 'Controlled failure on even-numbered runs'


def test_fails():
    assert False, 'Intentional persistent failure, not a flaky test'
