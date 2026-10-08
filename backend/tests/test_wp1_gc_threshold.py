"""WP1 1b: the API process collects garbage in a few large runs, not thousands of small ones (app/main.py)."""

import gc

from app import main


def test_the_api_collects_garbage_every_fifty_thousand_allocations():
    assert main.GC_FIRST_GENERATION == 50_000
    assert gc.get_threshold()[0] == main.GC_FIRST_GENERATION
