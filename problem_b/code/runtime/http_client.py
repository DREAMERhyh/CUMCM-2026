"""Official-protocol adapter.  Importing this module never starts a test."""

import json
import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from common.models import Action


def build_request_payload(action, robot_id):
    payload = {
        "arena_id": "default",
        "robot_id": robot_id,
        "request_id": action.request_id,
    }
    if action.kind in ("measure", "clear"):
        if action.position is None or action.channel is None:
            raise ValueError("measure/clear 动作必须包含位置和频道。")
        payload["position"] = {"x": action.position[0], "y": action.position[1]}
        payload["channel"] = action.channel
    return payload


class HttpRobotClient:
    """Synchronous adapter with same-ID, same-body transport retries.

    The user must start the simulator and choose the desired test manually.
    This class does not call /enter until the policy runner explicitly asks it.
    """
    def __init__(self, robot_id, base_url="http://127.0.0.1:2026",
                 timeout_s=5.0, retry_count=2, retry_delay_s=0.2):
        if not robot_id:
            raise ValueError("robot_id不能为空。")
        self.robot_id = robot_id
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.retry_count = retry_count
        self.retry_delay_s = retry_delay_s
        self._lock = threading.Lock()

    def execute(self, action):
        path = "/" + action.kind
        payload = build_request_payload(action, self.robot_id)
        body = json.dumps(payload, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
        request = Request(self.base_url+path, data=body,
                          headers={"Content-Type": "application/json; charset=utf-8"},
                          method="POST")
        with self._lock:
            last_error = None
            for attempt in range(self.retry_count+1):
                try:
                    with urlopen(request, timeout=self.timeout_s) as response:
                        return json.loads(response.read().decode("utf-8"))
                except HTTPError as error:
                    try:
                        data = json.loads(error.read().decode("utf-8"))
                    except Exception:
                        raise RuntimeError(f"HTTP {error.code}，响应不是合法JSON。") from error
                    data["http_status"] = error.code
                    return data
                except (URLError, socket.timeout, TimeoutError,
                        ConnectionError) as error:
                    last_error = error
                    if attempt < self.retry_count:
                        time.sleep(self.retry_delay_s)
            raise ConnectionError(
                f"动作{action.request_id}在保持相同请求内容重试后仍失败。"
            ) from last_error

