"""Small, JSON-friendly models shared by the offline planners."""

from dataclasses import asdict, dataclass, field
from typing import Literal

Point = tuple[float, float]
MeasureKind = Literal["direction", "near", "no_signal"]
ActionKind = Literal["enter", "measure", "clear", "exit"]


@dataclass(frozen=True)
class BearingObservation:
    position: Point
    channel: int
    result: MeasureKind
    bearing_deg: float | None = None

    def __post_init__(self):
        if not 1 <= self.channel <= 20:
            raise ValueError("频道必须在 1 至 20 之间。")
        if self.result == "direction" and self.bearing_deg is None:
            raise ValueError("direction 观测必须包含 bearing_deg。")
        if self.result != "direction" and self.bearing_deg is not None:
            raise ValueError("只有 direction 观测可以包含 bearing_deg。")

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    request_id: str
    position: Point | None = None
    channel: int | None = None

    def as_dict(self):
        data = asdict(self)
        if self.position is not None:
            data["position"] = {"x": self.position[0], "y": self.position[1]}
        return data


@dataclass
class TimeBreakdown:
    movement_s: float = 0.0
    switching_s: float = 0.0
    measurement_s: float = 0.0
    optical_s: float = 0.0
    laser_s: float = 0.0

    @property
    def total_s(self):
        return (self.movement_s + self.switching_s + self.measurement_s
                + self.optical_s + self.laser_s)

    def as_dict(self):
        return {**asdict(self), "total_s": self.total_s}


@dataclass
class RunSummary:
    actions: list[dict] = field(default_factory=list)
    cleared_channels: list[int] = field(default_factory=list)
    absent_channels: list[int] = field(default_factory=list)
    virtual_time_s: float = 0.0
    exit_reason: str | None = None

    def as_dict(self):
        return asdict(self)

