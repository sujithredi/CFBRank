"""Shared pytest fixtures."""

import pytest

from app.routers import matchup, odds


@pytest.fixture(autouse=True)
def _fresh_odds_state():
    """
    The weekly-odds endpoint keeps a module-level simulation cache and a per-client rate limiter,
    and the matchup endpoint has its own rate limiter.
    All would otherwise carry over from one test to the next: a cached result makes a later test
    that counts simulate_game calls see none, and enough requests across the whole suite from the
    same test client would trip a limiter.
    """
    odds.clear_simulation_cache()
    odds.reset_rate_limiter()
    matchup.reset_rate_limiter()
    yield
    odds.clear_simulation_cache()
    odds.reset_rate_limiter()
    matchup.reset_rate_limiter()
