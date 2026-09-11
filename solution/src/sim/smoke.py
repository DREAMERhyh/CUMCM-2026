"""Minimal policy for checking the official interface before strategy testing."""

from dataclasses import dataclass, field

from common.models import Action


@dataclass
class SmokeState:
    step: int = 0
    entered: bool = False
    exited: bool = False
    virtual_time_s: float = 0.0
    cleared: set[int] = field(default_factory=set)
    absent: set[int] = field(default_factory=set)


class SmokePolicy:
    """Issue /enter, one harmless /measure at the initial state, then /exit."""

    def initial_state(self):
        return SmokeState()

    def next_action(self, state):
        if state.step == 0:
            return Action("enter", "smoke-enter-1")
        if state.step == 1:
            return Action("measure", "smoke-measure-1", (0.0, 0.0), 1)
        if state.step == 2:
            return Action("exit", "smoke-exit-1")
        return None

    def apply_response(self, state, action, response):
        if response.get("accepted") is not True:
            raise RuntimeError("烟雾测试动作被拒绝。")
        expected = ("enter", "measure", "exit")[state.step]
        if action.kind != expected:
            raise RuntimeError("烟雾测试动作顺序不一致。")
        state.virtual_time_s = float(response["virtual_time_s"])
        state.step += 1
        if action.kind == "enter":
            state.entered = True
        elif action.kind == "exit":
            state.exited = True
