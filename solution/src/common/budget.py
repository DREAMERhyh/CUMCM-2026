"""Shared wall-clock budget guard for anytime planning.

One ``WallClockBudget`` is created per planning entry and passed to every
search loop (candidate scoring, pattern search, near-optimal sampling).  When
``expired()`` turns True the caller stops starting new work and returns the
current best incumbent; it never raises due to a time limit.
"""

import time


class WallClockBudget:
    """Deadline shared by all search loops of a single planning call.

    ``budget_s=None`` disables the limit.  All methods may be called freely
    from every loop; they never raise.
    """

    def __init__(self, budget_s):
        if budget_s is not None and budget_s <= 0:
            raise ValueError("墙钟预算必须为正数。")
        self.budget_s = budget_s
        self._started = time.perf_counter()

    def expired(self):
        return (self.budget_s is not None
                and time.perf_counter() - self._started >= self.budget_s)

    def remaining_s(self):
        if self.budget_s is None:
            return None
        return max(0.0, self.budget_s - (time.perf_counter() - self._started))

    @property
    def used_s(self):
        return time.perf_counter() - self._started