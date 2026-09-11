"""Compatibility import; the canonical implementation is ``sim.client``."""

from sim.client import HttpRobotClient
from sim.protocol import build_request_payload

__all__ = ["HttpRobotClient", "build_request_payload"]
