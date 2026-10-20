"""Shared pytest fixtures."""

import pytest

from app.routers import odds


@pytest.fixture(autouse=True)
def _fresh_odds_state():
    """
    The weekly-odds endpoint keeps a module-level simulation cache and a per-client rate limiter.
    Both would otherwise carry over from one test to the next: a cached result makes a later test
    that counts simulate_game calls see none, and enough requests across the whole suite from the
    same test client would trip the limiter.
    """
    odds.clear_simulation_cache()
    odds.reset_rate_limiter()
    yield
    odds.clear_simulation_cache()
    odds.reset_rate_limiter()
