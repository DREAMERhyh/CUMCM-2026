"""Compatibility import; the canonical offline simulator is ``sim.fake``."""

from sim.fake import FakeSimulator, FakeSource

__all__ = ["FakeSimulator", "FakeSource"]
