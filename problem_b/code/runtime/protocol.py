"""Minimal client protocol consumed by the strategy runner."""

from typing import Protocol

from common.models import Action


class RobotClient(Protocol):
    def execute(self, action: Action) -> dict:
        """Execute one action and return the decoded simulator response."""

