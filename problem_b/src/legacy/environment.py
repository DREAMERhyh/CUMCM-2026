"""Synthetic omnidirectional environment following B appendices 1 and 2.

The error field is a reproducible synthetic construction, not the official
simulator's error distribution. The solver never receives source truth.
"""

import hashlib
import math
import random
from pathlib import Path
import sys

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from q1.geometry import contains, localize

DOMAIN_RADIUS = 1800.0


def number(value, name, low=-2_000_000, high=2_000_000):
    if isinstance(value, bool):
        raise ValueError(f"{name}必须是有限数值。")
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}必须是有限数值。") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name}须在 {low:g} 至 {high:g} 之间。")
    return 0.0 if value == 0 else value


def integer(value, name, low, high):
    value = number(value, name, low, high)
    if not value.is_integer():
        raise ValueError(f"{name}必须为整数。")
    return int(value)


def validate_scene(data):
    if not isinstance(data, dict):
        raise ValueError("场景必须是 JSON 对象。")
    seed = integer(data.get("seed", 2026), "随机种子", 0, 2**32-1)
    sources, detectors = data.get("sources"), data.get("detectors")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
        raise ValueError("请输入 1 至 20 个全向干扰源。")
    if not isinstance(detectors, list) or not 1 <= len(detectors) <= 64:
        raise ValueError("请输入 1 至 64 个检测点。")
    clean_sources, clean_detectors, channels = [], [], set()
    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            raise ValueError("每个干扰源必须是对象。")
        channel = integer(s.get("channel"), "频道", 1, 20)
        if channel in channels:
            raise ValueError("每个干扰源必须使用不同频道。")
        channels.add(channel)
        x, y = number(s.get("x"), "源 x"), number(s.get("y"), "源 y")
        if math.hypot(x, y) > DOMAIN_RADIUS + 1e-8:
            raise ValueError(f"G{i+1} 超出半径 1800 米的分布区域。")
        clean_sources.append(dict(channel=channel, x=x, y=y,
                                  radius=number(s.get("radius", 1250), "接收半径", 1000, 1500)))
    # Same coordinate must have one fixed error override within this scene.
    overrides = {}
    for i, d in enumerate(detectors):
        if not isinstance(d, dict):
            raise ValueError("每个检测点必须是对象。")
        x, y = number(d.get("x"), "检测点 x"), number(d.get("y"), "检测点 y")
        error = d.get("error_deg")
        error = None if error in (None, "") else number(error, "角度误差", -1, 1)
        key = (x, y)
        if key in overrides and overrides[key] != error:
            raise ValueError("同一检测位置的误差设置必须一致（同地点重复检测误差固定）。")
        overrides[key] = error
        clean_detectors.append(dict(x=x, y=y, error_deg=error))
    active = integer(data.get("active_channel", clean_sources[0]["channel"]), "当前频道", 1, 20)
    if active not in channels:
        raise ValueError("当前频道没有对应的输入干扰源。")
    return dict(seed=seed, sources=clean_sources, detectors=clean_detectors, active_channel=active)


def measure(source, detector, seed):
    point = [detector["x"], detector["y"]]
    distance = math.hypot(source["x"]-point[0], source["y"]-point[1])
    result = dict(position=point, distance=distance, bearing_deg=None,
                  true_bearing_deg=None, error_deg=None)
    if distance > source["radius"]:
        return dict(result, status="no_signal")
    if distance <= 5:
        return dict(result, status="near")
    true = math.degrees(math.atan2(source["y"]-point[1], source["x"]-point[0])) % 360
    error = detector.get("error_deg")
    if error is None:
        key = f'{seed}:{source["channel"]}:{point[0]:.17g}:{point[1]:.17g}'
        code = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
        error = 2*code/(2**64-1)-1
    return dict(result, status="direction", true_bearing_deg=true,
                error_deg=error, bearing_deg=(true+error) % 360)


def calculate(data):
    scene = validate_scene(data)
    source = next(s for s in scene["sources"] if s["channel"] == scene["active_channel"])
    observations = [dict(measure(source, d, scene["seed"]), label=f"S{i+1}")
                    for i, d in enumerate(scene["detectors"])]
    invalid = [o["label"] for o in observations if o["status"] != "direction"]
    if invalid:
        raise ValueError("、".join(invalid) + " 无有效示向度：本阶段要求检测点与当前源的距离大于 5 米且不超过接收半径，请调整坐标。")
    extent = max(2100.0, *(max(abs(d["x"]), abs(d["y"]))*1.15 for d in scene["detectors"]))
    bounds = [-extent, -extent, extent, extent]
    region = localize(observations, bounds)
    # Truth is used here only for the separate verification display.
    audit = dict(truth_in_region=contains(region["planes"], (source["x"], source["y"]))
                 if region["bearing_count"] else None,
                 max_error=max((abs(o["error_deg"]) for o in observations
                                if o["error_deg"] is not None), default=None))
    return dict(scene=scene, observations=observations, region=region, audit=audit, bounds=bounds)


def generate(data):
    if not isinstance(data, dict):
        raise ValueError("生成参数必须为对象。")
    seed = integer(data.get("seed", 2026), "随机种子", 0, 2**32-1)
    source_count = integer(data.get("source_count", 1), "源数量", 1, 20)
    detector_count = integer(data.get("detector_count", 4), "检测点数量", 1, 64)
    mode = data.get("mode", "nearby")
    if mode not in ("nearby", "uniform"):
        raise ValueError("未知的生成方式。")
    rng = random.Random(seed)

    def disk(radius, center=(0, 0)):
        r, angle = radius*math.sqrt(rng.random()), rng.random()*2*math.pi
        return center[0]+r*math.cos(angle), center[1]+r*math.sin(angle)

    sources = []
    for channel in range(1, source_count+1):
        x, y = disk(DOMAIN_RADIUS)
        sources.append(dict(channel=channel, x=round(x, 4), y=round(y, 4),
                            radius=round(rng.uniform(1000, 1500), 4)))
    detectors = []
    for _ in range(detector_count):
        for attempt in range(10000):
            if mode == "uniform":
                x, y = disk(DOMAIN_RADIUS)
            else:
                x, y = disk(min(950, sources[0]["radius"]-10),
                            (sources[0]["x"], sources[0]["y"]))
            distance = math.hypot(x-sources[0]["x"], y-sources[0]["y"])
            if math.hypot(x, y) <= DOMAIN_RADIUS-0.001 and 10 < distance < sources[0]["radius"]-1:
                break
        else:
            raise ValueError("未能生成检测点，请更换种子。")
        detectors.append(dict(x=round(x, 4), y=round(y, 4), error_deg=None))
    return dict(seed=seed, active_channel=1, sources=sources, detectors=detectors)


def demo():
    return dict(seed=2026, active_channel=1,
                sources=[dict(channel=1, x=220, y=280, radius=1250)],
                detectors=[dict(x=-600, y=-300, error_deg=0.6),
                           dict(x=850, y=-250, error_deg=-0.5),
                           dict(x=-200, y=1000, error_deg=0.3),
                           dict(x=850, y=850, error_deg=-0.2)])
