"""Deterministic offline rule model; it is not the official simulator."""

from dataclasses import dataclass
import hashlib
import math

from common.models import Action
from common.time_model import clear_cost, measure_cost


@dataclass
class FakeSource:
    channel: int
    position: tuple[float, float]
    receive_radius: float = 1000.0
    direction_deg: float | None = None
    cleared: bool = False


class FakeSimulator:
    def __init__(self, sources, error_bound_deg=1.0):
        self.sources = {source.channel: source for source in sources}
        self.error_bound_deg = error_bound_deg
        self.position = (0.0, 0.0)
        self.channel = 1
        self.virtual_time = 0.0
        self.entered = False
        self.exited = False
        self.responses = {}

    def _visible(self, source, sensor):
        delta = (sensor[0]-source.position[0], sensor[1]-source.position[1])
        if math.hypot(*delta) > source.receive_radius:
            return False
        if source.direction_deg is None:
            return True
        angle = math.radians(source.direction_deg)
        return math.cos(angle)*delta[0] + math.sin(angle)*delta[1] >= -1e-9

    def _error(self, source, sensor):
        key = f"{source.channel}:{sensor[0]:.9f}:{sensor[1]:.9f}".encode()
        integer = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
        return self.error_bound_deg*(2*integer/(2**64-1)-1)

    def execute(self, action: Action):
        cached = self.responses.get(action.request_id)
        if cached is not None:
            return dict(cached)
        if action.kind == "enter":
            if self.entered or self.exited:
                response = {"accepted": False, "virtual_time_s": 0}
            else:
                self.entered = True
                response = {"accepted": True, "virtual_time_s": 0.0,
                            "remaining_real_duration_s": 1200}
        elif not self.entered or self.exited:
            response = {"accepted": False, "virtual_time_s": 0}
        elif action.kind == "exit":
            self.exited = True
            response = {"accepted": True, "virtual_time_s": self.virtual_time,
                        "exit_reason": "user_exit"}
        elif action.kind == "measure":
            timing = measure_cost(self.position, action.position, self.channel,
                                  action.channel)
            self.virtual_time += timing.total_s
            self.position, self.channel = action.position, action.channel
            source = self.sources.get(action.channel)
            if source is None or source.cleared or not self._visible(source, action.position):
                result = {"measure_result": "no_signal"}
            else:
                distance = math.dist(action.position, source.position)
                if distance <= 5.0:
                    result = {"measure_result": "near"}
                else:
                    true = math.degrees(math.atan2(source.position[1]-action.position[1],
                                                   source.position[0]-action.position[0])) % 360
                    result = {"measure_result": "direction",
                              "svd_deg": round((true+self._error(source, action.position)) % 360, 2)}
            response = {"accepted": True, "virtual_time_s": self.virtual_time, **result}
        elif action.kind == "clear":
            source = self.sources.get(action.channel)
            success = bool(source and not source.cleared and
                           math.dist(action.position, source.position) <= 20.0+1e-9)
            timing = clear_cost(self.position, action.position, success)
            self.virtual_time += timing.total_s
            self.position = action.position
            if success:
                source.cleared = True
            response = {"accepted": True, "virtual_time_s": self.virtual_time,
                        "clear_result": "success" if success else "no_target_in_range"}
        else:
            raise ValueError(f"未知动作：{action.kind}")
        self.responses[action.request_id] = dict(response)
        return response

