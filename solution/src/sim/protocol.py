"""Confirmed HTTP+JSON protocol from B-problem appendices 1 and 2."""

import json
import math
import unicodedata

from common.models import Action

from .errors import SimulatorProtocolError

ARENA_ID = "default"
PATHS = {
    "enter": "/enter",
    "measure": "/measure",
    "clear": "/clear",
    "exit": "/exit",
}
COMMON_RESPONSE_FIELDS = {"accepted", "real_timestamp_ms", "virtual_time_s"}
MAX_BODY_BYTES = 65_536
MAX_COORDINATE_ABS_M = 2_000_000.0


def _finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SimulatorProtocolError(f"{name}必须是 JSON number。")
    value = float(value)
    if not math.isfinite(value):
        raise SimulatorProtocolError(f"{name}必须是有限数值。")
    return value


def _identifier(value, name, max_bytes):
    if not isinstance(value, str):
        raise SimulatorProtocolError(f"{name}必须是字符串。")
    size = len(value.encode("utf-8"))
    if not 1 <= size <= max_bytes:
        raise SimulatorProtocolError(
            f"{name}的 UTF-8 长度必须为 1 至 {max_bytes} 字节。"
        )
    if any(unicodedata.category(char) in ("Cc", "Cf") for char in value):
        raise SimulatorProtocolError(f"{name}不能包含控制字符或不可见格式字符。")
    return value


def _channel(value):
    number = _finite_number(value, "channel")
    if not number.is_integer() or not 1 <= number <= 20:
        raise SimulatorProtocolError("channel 必须是 1 至 20 的整数。")
    return int(number)


def validate_action(action):
    """Validate one internal action before it can reach the HTTP layer."""
    if not isinstance(action, Action):
        raise SimulatorProtocolError("动作必须是 common.models.Action。")
    if action.kind not in PATHS:
        raise SimulatorProtocolError(f"未知动作类型：{action.kind!r}。")
    _identifier(action.request_id, "request_id", 128)
    if action.kind in ("enter", "exit"):
        if action.position is not None or action.channel is not None:
            raise SimulatorProtocolError("enter/exit 动作不能包含 position 或 channel。")
        return action
    if action.position is None or action.channel is None:
        raise SimulatorProtocolError("measure/clear 动作必须包含 position 和 channel。")
    try:
        position = tuple(action.position)
    except TypeError:
        raise SimulatorProtocolError("position 必须包含 x、y 两个坐标。") from None
    if len(position) != 2:
        raise SimulatorProtocolError("position 必须包含 x、y 两个坐标。")
    for name, value in zip(("position.x", "position.y"), position):
        number = _finite_number(value, name)
        if abs(number) > MAX_COORDINATE_ABS_M:
            raise SimulatorProtocolError(f"{name}绝对值不能超过 2000000 米。")
    _channel(action.channel)
    return action


def build_request_payload(action, robot_id):
    """Map an internal Action to exactly the fields accepted by the simulator."""
    validate_action(action)
    payload = {
        "arena_id": ARENA_ID,
        "robot_id": _identifier(robot_id, "robot_id", 64),
        "request_id": action.request_id,
    }
    if action.kind in ("measure", "clear"):
        payload["position"] = {
            "x": float(action.position[0]),
            "y": float(action.position[1]),
        }
        payload["channel"] = _channel(action.channel)
    return payload


def encode_request_payload(payload):
    """Encode a no-BOM UTF-8 body and reject NaN or oversized payloads."""
    try:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SimulatorProtocolError("请求无法编码为合法 UTF-8 JSON。") from error
    if len(body) > MAX_BODY_BYTES:
        raise SimulatorProtocolError("请求体超过 65536 字节。")
    return body


def decode_response_body(body):
    """Decode one strict UTF-8 JSON object, rejecting BOM, constants and duplicate keys."""
    if not isinstance(body, bytes):
        raise SimulatorProtocolError("HTTP 响应体必须是字节串。")
    if body.startswith(b"\xef\xbb\xbf"):
        raise SimulatorProtocolError("响应 JSON 不能包含 UTF-8 BOM。")

    def object_from_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SimulatorProtocolError(f"响应 JSON 包含重复键：{key}。")
            result[key] = value
        return result

    def reject_constant(value):
        raise SimulatorProtocolError(f"响应 JSON 包含非法常量：{value}。")

    try:
        text = body.decode("utf-8")
        data = json.loads(
            text,
            object_pairs_hook=object_from_pairs,
            parse_constant=reject_constant,
        )
    except SimulatorProtocolError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SimulatorProtocolError("模拟器响应不是合法的 UTF-8 JSON。") from error
    if not isinstance(data, dict):
        raise SimulatorProtocolError("模拟器响应必须是 JSON 对象。")
    return data


def _exact_fields(response, expected):
    actual = set(response)
    if actual != expected:
        missing = sorted(expected-actual)
        unknown = sorted(actual-expected)
        details = []
        if missing:
            details.append("缺少字段 " + ", ".join(missing))
        if unknown:
            details.append("未知字段 " + ", ".join(unknown))
        raise SimulatorProtocolError("响应字段不符合协议：" + "；".join(details) + "。")


def validate_response(action, http_status, response):
    """Validate common and action-specific response fields; return the same dict."""
    validate_action(action)
    if isinstance(http_status, bool) or not isinstance(http_status, int):
        raise SimulatorProtocolError("HTTP 状态必须是整数。")
    if not isinstance(response, dict):
        raise SimulatorProtocolError("模拟器响应必须是 JSON 对象。")
    missing_common = COMMON_RESPONSE_FIELDS-set(response)
    if missing_common:
        raise SimulatorProtocolError(
            "响应缺少公共字段：" + ", ".join(sorted(missing_common)) + "。"
        )
    if type(response["accepted"]) is not bool:
        raise SimulatorProtocolError("accepted 必须是 boolean。")
    _finite_number(response["real_timestamp_ms"], "real_timestamp_ms")
    virtual_time = _finite_number(response["virtual_time_s"], "virtual_time_s")
    if virtual_time < 0:
        raise SimulatorProtocolError("virtual_time_s 不能为负数。")
    if response["accepted"] is False:
        _exact_fields(response, COMMON_RESPONSE_FIELDS)
        if virtual_time != 0:
            raise SimulatorProtocolError("accepted=false 时 virtual_time_s 必须为 0。")
        return response
    if http_status != 200:
        raise SimulatorProtocolError("非 200 HTTP 响应不能包含 accepted=true。")

    if action.kind == "enter":
        expected = COMMON_RESPONSE_FIELDS | {
            "max_virtual_duration_s",
            "max_real_duration_s",
            "remaining_real_duration_s",
        }
        _exact_fields(response, expected)
        max_virtual = _finite_number(
            response["max_virtual_duration_s"], "max_virtual_duration_s"
        )
        max_real = _finite_number(response["max_real_duration_s"], "max_real_duration_s")
        remaining = _finite_number(
            response["remaining_real_duration_s"], "remaining_real_duration_s"
        )
        if max_virtual <= 0 or max_real <= 0:
            raise SimulatorProtocolError("模拟器时间上限必须为正数。")
        if not remaining.is_integer() or not 0 <= remaining <= max_real:
            raise SimulatorProtocolError(
                "remaining_real_duration_s 必须是 0 至 max_real_duration_s 的整数。"
            )
    elif action.kind == "measure":
        result = response.get("measure_result")
        if result not in ("no_signal", "near", "direction"):
            raise SimulatorProtocolError("measure_result 取值不符合协议。")
        expected = COMMON_RESPONSE_FIELDS | {"measure_result"}
        if result == "direction":
            expected.add("svd_deg")
        _exact_fields(response, expected)
        if result == "direction":
            bearing = _finite_number(response["svd_deg"], "svd_deg")
            if not 0 <= bearing < 360:
                raise SimulatorProtocolError("svd_deg 必须位于 [0, 360)。")
    elif action.kind == "clear":
        _exact_fields(response, COMMON_RESPONSE_FIELDS | {"clear_result"})
        if response["clear_result"] not in ("success", "no_target_in_range"):
            raise SimulatorProtocolError("clear_result 取值不符合协议。")
    elif action.kind == "exit":
        _exact_fields(response, COMMON_RESPONSE_FIELDS | {"exit_reason"})
        if response["exit_reason"] != "user_exit":
            raise SimulatorProtocolError("exit_reason 取值不符合协议。")
    return response
