"""app/ratelimit.py: a per-client sliding-window limit, driven by a fake clock so nothing sleeps."""

import threading

import pytest

from app.ratelimit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture()
def clock():
    return FakeClock()


def _limiter(clock, max_requests=3, window_seconds=60, **kwargs):
    return RateLimiter(max_requests=max_requests, window_seconds=window_seconds, clock=clock, **kwargs)


def test_requests_up_to_the_limit_are_allowed_and_the_next_one_is_not(clock):
    limiter = _limiter(clock)
    assert [limiter.check("a")[0] for _ in range(3)] == [True, True, True]
    assert limiter.check("a")[0] is False


def test_the_retry_after_is_the_time_until_the_oldest_request_leaves_the_window(clock):
    limiter = _limiter(clock)
    limiter.check("a")  # t = 1000
    clock.advance(10)
    limiter.check("a")  # t = 1010
    limiter.check("a")  # t = 1010

    clock.advance(5)  # t = 1015; the oldest request (1000) leaves the window at 1060
    allowed, retry_after = limiter.check("a")
    assert allowed is False
    assert retry_after == pytest.approx(45.0)


def test_the_window_slides_so_old_requests_stop_counting(clock):
    limiter = _limiter(clock)
    for _ in range(3):
        limiter.check("a")
    assert limiter.check("a")[0] is False

    clock.advance(60.1)
    assert limiter.check("a")[0] is True


def test_a_request_that_was_refused_does_not_extend_the_wait(clock):
    limiter = _limiter(clock)
    for _ in range(3):
        limiter.check("a")  # all at t = 1000

    for _ in range(20):  # a client hammering away while blocked
        clock.advance(1)
        assert limiter.check("a")[0] is False

    clock.advance(40.1)  # t = 1060.1: the original three have expired, and the refused ones never counted
    assert limiter.check("a")[0] is True


def test_each_client_has_its_own_budget(clock):
    limiter = _limiter(clock)
    for _ in range(3):
        limiter.check("a")
    assert limiter.check("a")[0] is False
    assert limiter.check("b")[0] is True


def test_a_limit_of_zero_means_no_limit(clock):
    limiter = _limiter(clock, max_requests=0)
    assert limiter.enabled is False
    assert all(limiter.check("a") == (True, 0.0) for _ in range(1000))


def test_reset_forgets_every_client(clock):
    limiter = _limiter(clock)
    for _ in range(3):
        limiter.check("a")
    limiter.reset()
    assert limiter.check("a")[0] is True


def test_the_number_of_remembered_clients_is_bounded(clock):
    limiter = _limiter(clock, max_requests=1, max_tracked_clients=100)
    for i in range(10_000):
        limiter.check(f"10.0.{i // 256}.{i % 256}")
    assert len(limiter._hits) <= 100


def test_when_the_bound_is_hit_clients_that_stopped_calling_are_dropped_first(clock):
    limiter = _limiter(clock, max_requests=5, max_tracked_clients=3)
    limiter.check("old-1")
    limiter.check("old-2")
    clock.advance(120)  # both are now outside the window
    limiter.check("busy")
    limiter.check("new")  # a fourth key: over the bound, so the two expired ones go
    assert set(limiter._hits) == {"busy", "new"}


def test_a_new_client_is_still_limited_when_the_table_of_clients_is_full(clock):
    limiter = _limiter(clock, max_requests=1, max_tracked_clients=2)
    limiter.check("a")
    limiter.check("b")  # the table is now full of clients that are still inside their window

    assert limiter.check("c")[0] is True  # a newcomer is admitted (the least recently seen client makes room)...
    assert limiter.check("c")[0] is False  # ...and is held to the limit, not waved through forever
    assert len(limiter._hits) <= 2


def test_a_burst_from_many_threads_never_lets_more_than_the_limit_through(clock):
    limiter = _limiter(clock, max_requests=10)
    allowed = []

    def hit():
        allowed.append(limiter.check("a")[0])

    threads = [threading.Thread(target=hit) for _ in range(200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert allowed.count(True) == 10
    assert allowed.count(False) == 190
