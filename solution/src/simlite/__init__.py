"""simlite：函数级直调的离线模拟器，语义与 B 题附件2 严格一致（无 HTTP 层）。

与 ``sim.fake`` 的定位区别：fake 是策略测试的规则替身；simlite 面向
"官方演练对账"与"批量回放统计"，虚拟时间按微秒整数累计，便于与
``common/time_model`` 逐动作对账（验收硬标准见 tests/simlite/）。

本模块只新增文件，不修改 common/、q1-q3 任何现有代码。
"""

from dataclasses import dataclass
import hashlib
import math

from common.models import Action
from common.time_model import clear_cost, measure_cost

MICROSECONDS = 1_000_000


class RequestIdConflictError(ValueError):
    """同一 request_id 被用于不同动作（与官方 409/幂等语义一致）。"""


@dataclass
class Source:
    channel: int
    position: tuple[float, float]
    receive_radius: float
    direction_deg: float | None = None
    cleared: bool = False

    def __post_init__(self):
        if not 1 <= self.channel <= 20:
            raise ValueError("频道必须在 1 至 20 之间。")
        if not 1000.0 <= self.receive_radius <= 1500.0:
            raise ValueError("有效接收半径必须在 [1000,1500] 米。")
        if self.direction_deg is not None:
            if not 0 <= self.direction_deg < 360:
                raise ValueError("定向方向必须在 [0,360)。")


def _fixed_error(position, channel, error_bound_deg=1.0):
    """该（地点, 频道）固定的系统误差；全局有界于 ±error_bound_deg。"""
    key = f"{channel}:{position[0]:.9f}:{position[1]:.9f}".encode()
    integer = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
    return error_bound_deg * (2 * integer / (2**64 - 1) - 1)


def _in_coverage(source, sensor):
    """定向源仅覆盖定向方向两侧各 90°（含边界）；全向源任意方向可见。"""
    if source.direction_deg is None:
        return True
    delta = (sensor[0] - source.position[0],
             sensor[1] - source.position[1])
    angle = math.radians(source.direction_deg)
    return math.cos(angle) * delta[0] + math.sin(angle) * delta[1] >= -1e-9


def generate_sources(rng, *, count=None, direction_ratio=0.0):
    """按附件2/题目生成一局源案例（seed 可复现）。

    源数默认 10-16；频道从 20 个中不放回抽取；位置按面积均匀分布于
    D(0,1800)（sqrt 均匀）；有效接收半径 U(1000,1500)；定向源比例由
    ``direction_ratio`` 控制（Q3 场景传 0，全向）。
    """
    if not 0.0 <= direction_ratio <= 1.0:
        raise ValueError("direction_ratio 必须在 [0,1]。")
    if count is None:
        count = rng.randint(10, 16)
    if not 10 <= count <= 16:
        raise ValueError("源数必须在 10 至 16 之间。")
    channels = rng.sample(range(1, 21), count)
    sources = []
    for channel in channels:
        radius = 1800.0 * math.sqrt(rng.random())
        angle = 2.0 * math.pi * rng.random()
        position = (radius * math.cos(angle), radius * math.sin(angle))
        receive_radius = rng.uniform(1000.0, 1500.0)
        direction_deg = (rng.uniform(0.0, 360.0)
                         if rng.random() < direction_ratio else None)
        sources.append(Source(channel, position, receive_radius,
                              direction_deg))
    return sources


class Simulator:
    """单局离线模拟器。``execute`` 返回与官方相同的响应字典。"""

    def __init__(self, sources, *, error_bound_deg=1.0):
        self.sources = {source.channel: source
                        for source in (sources or [])}
        self.error_bound_deg = error_bound_deg
        self.position = (0.0, 0.0)
        self.channel = 1
        self.virtual_micros = 0
        self.entered = False
        self.exited = False
        self._responses = {}
        self._requests = {}

    @property
    def virtual_time_s(self):
        return self.virtual_micros / MICROSECONDS

    def _advance(self, timing):
        self.virtual_micros += round(timing.total_s * MICROSECONDS)

    def _common(self, accepted=True):
        return {
            "accepted": accepted,
            "real_timestamp_ms": 1760000000000,
            "virtual_time_s": self.virtual_time_s if accepted else 0,
        }

    def execute(self, action: Action):
        from common.models import Action as _Action

        if not isinstance(action, _Action):
            raise ValueError("simlite 只接受 common.models.Action。")
        fingerprint = action.as_dict()
        previous = self._requests.get(action.request_id)
        if previous is not None and previous != fingerprint:
            raise RequestIdConflictError(
                "同一 request_id 不能对应不同动作。"
            )
        cached = self._responses.get(action.request_id)
        if cached is not None:
            return dict(cached)
        if action.kind == "enter":
            if self.entered or self.exited:
                return self._common(False)
            self.entered = True
            response = {
                **self._common(True),
                "max_virtual_duration_s": 360000,
                "max_real_duration_s": 1200,
                "remaining_real_duration_s": 1200,
            }
        elif not self.entered or self.exited:
            return self._common(False)
        elif action.kind == "exit":
            self.exited = True
            response = {**self._common(True), "exit_reason": "user_exit"}
        elif action.kind == "measure":
            timing = measure_cost(self.position, action.position,
                                  self.channel, action.channel)
            self._advance(timing)
            self.position = action.position
            self.channel = action.channel
            source = self.sources.get(action.channel)
            if not _visible(source, self.position):
                result = {"measure_result": "no_signal"}
            elif math.dist(self.position, source.position) <= 5.0:
                result = {"measure_result": "near"}
            else:
                true = math.degrees(math.atan2(
                    source.position[1] - self.position[1],
                    source.position[0] - self.position[0],
                )) % 360.0
                result = {
                    "measure_result": "direction",
                    "svd_deg": round(
                        (true + _fixed_error(self.position, source.channel,
                                             self.error_bound_deg)) % 360.0,
                        2,
                    ),
                }
            response = {**self._common(True), **result}
        elif action.kind == "clear":
            source = self.sources.get(action.channel)
            success = bool(source and not source.cleared
                           and math.dist(action.position,
                                         source.position) <= 20.0 + 1e-9)
            timing = clear_cost(self.position, action.position, success)
            self._advance(timing)
            self.position = action.position
            if success:
                source.cleared = True
            response = {
                **self._common(True),
                "clear_result": "success" if success
                else "no_target_in_range",
            }
        else:
            raise AssertionError("未知动作类型。")
        self._requests[action.request_id] = fingerprint
        self._responses[action.request_id] = dict(response)
        return response


def _visible(source, sensor):
    """源被清除、超出接收半径或不在覆盖角范围内时均不可见。"""
    if source is None or source.cleared:
        return False
    if math.dist(sensor, source.position) > source.receive_radius:
        return False
    return _in_coverage(source, sensor)


__all__ = [
    "MICROSECONDS", "RequestIdConflictError", "Simulator", "Source",
    "_fixed_error", "_in_coverage", "generate_sources",
]