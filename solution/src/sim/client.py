"""Synchronous loopback-only HTTP client for the official simulator."""

from dataclasses import dataclass
import math
import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from common.models import Action

from .errors import (
    ConcurrentRequestError,
    IdempotencyConflictError,
    SimulatorHttpError,
    SimulatorProtocolError,
    SimulatorRejectedError,
    SimulatorTransportError,
)
from .protocol import (
    PATHS,
    build_request_payload,
    decode_response_body,
    encode_request_payload,
    validate_response,
)


@dataclass(frozen=True)
class SimulatorExchange:
    """A complete, validated HTTP exchange returned by ``request``."""

    action: Action
    path: str
    payload: dict
    http_status: int
    response: dict
    attempts: int


def _validate_base_url(value):
    if not isinstance(value, str):
        raise ValueError("base_url 必须是字符串。")
    parsed = urlsplit(value.rstrip("/"))
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("模拟器地址必须是本机回环地址上的 http 服务。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("模拟器地址不能包含认证信息、查询参数或片段。")
    if parsed.path not in ("", "/"):
        raise ValueError("模拟器地址不能包含路径。")
    try:
        if parsed.port is None:
            raise ValueError("模拟器地址必须显式包含端口。")
    except ValueError as error:
        raise ValueError("模拟器地址端口不合法。") from error
    return value.rstrip("/")


class HttpRobotClient:
    """Execute one action at a time with same-ID, same-body safe retries."""

    def __init__(self, robot_id, base_url="http://127.0.0.1:2026",
                 timeout_s=5.0, retry_count=2, retry_delay_s=0.2):
        build_request_payload(Action("enter", "client-validation"), robot_id)
        self.robot_id = robot_id
        self.base_url = _validate_base_url(base_url)
        if isinstance(retry_count, bool) or not isinstance(retry_count, int):
            raise ValueError("retry_count 必须是非负整数。")
        self.timeout_s = float(timeout_s)
        self.retry_count = retry_count
        self.retry_delay_s = float(retry_delay_s)
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0:
            raise ValueError("timeout_s 必须为正数。")
        if self.retry_count < 0:
            raise ValueError("retry_count 必须是非负整数。")
        if not math.isfinite(self.retry_delay_s) or self.retry_delay_s < 0:
            raise ValueError("retry_delay_s 不能为负数。")
        self._in_flight = threading.Lock()
        self._idempotency = {}
        self.last_exchange = None

    def _check_idempotency(self, action, path, body):
        previous = self._idempotency.get(action.request_id)
        fingerprint = (path, body)
        if previous is not None and previous != fingerprint:
            raise IdempotencyConflictError(
                f"request_id {action.request_id!r} 已绑定到另一动作；请求未发送。"
            )
        return fingerprint

    def request(self, action):
        """Return a validated exchange, including accepted=false and HTTP errors."""
        payload = build_request_payload(action, self.robot_id)
        path = PATHS[action.kind]
        body = encode_request_payload(payload)
        fingerprint = self._check_idempotency(action, path, body)
        if not self._in_flight.acquire(blocking=False):
            raise ConcurrentRequestError("不得并发发送不同动作；本次请求未发送。")
        try:
            last_error = None
            for attempt in range(1, self.retry_count+2):
                request = Request(
                    self.base_url+path,
                    data=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    method="POST",
                )
                try:
                    with urlopen(request, timeout=self.timeout_s) as http_response:
                        status = http_response.status
                        response_body = http_response.read()
                except HTTPError as error:
                    status = error.code
                    response_body = error.read()
                except (URLError, socket.timeout, TimeoutError,
                        ConnectionError, OSError) as error:
                    last_error = error
                    if attempt <= self.retry_count:
                        if self.retry_delay_s:
                            time.sleep(self.retry_delay_s)
                        continue
                    # The last request may have reached the simulator, so bind its ID.
                    self._idempotency[action.request_id] = fingerprint
                    raise SimulatorTransportError(
                        "保持相同路径、请求体和 request_id 重试后仍未获得完整 HTTP 响应。",
                        request_id=action.request_id,
                        attempts=attempt,
                    ) from last_error
                try:
                    response = decode_response_body(response_body)
                except SimulatorProtocolError:
                    if status == 200:
                        # A successful HTTP exchange with an unreadable body is
                        # execution-ambiguous; never allow this ID to be rebound.
                        self._idempotency[action.request_id] = fingerprint
                    raise
                if response.get("accepted") is True:
                    self._idempotency[action.request_id] = fingerprint
                validate_response(action, status, response)
                exchange = SimulatorExchange(
                    action=action,
                    path=path,
                    payload=payload,
                    http_status=status,
                    response=response,
                    attempts=attempt,
                )
                self.last_exchange = exchange
                return exchange
            raise AssertionError("不可达的重试分支。")
        finally:
            self._in_flight.release()

    def execute(self, action):
        """Execute an accepted action or raise a typed simulator error."""
        exchange = self.request(action)
        if exchange.http_status != 200:
            raise SimulatorHttpError(exchange.http_status, exchange.response)
        if exchange.response["accepted"] is not True:
            raise SimulatorRejectedError(exchange.response)
        return exchange.response
