"""Live policy runner with deadlines and durable per-action JSONL logs."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import uuid

from common.models import Action, RunSummary

from .errors import SimulatorError


class JsonlActionLogger:
    """Create a new log file and flush every action record immediately."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("x", encoding="utf-8", newline="\n")

    def write(self, *, sequence, action, request_payload=None, response=None,
              error=None, elapsed_real_s=None, note=None, http_status=None,
              attempts=None):
        record = {
            "sequence": sequence,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_real_s": elapsed_real_s,
            "action": action.as_dict(),
        }
        if request_payload is not None:
            record["request"] = request_payload
        if http_status is not None:
            record["http_status"] = http_status
        if attempts is not None:
            record["attempts"] = attempts
        if response is not None:
            record["response"] = response
        if error is not None:
            record["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            for name in ("status", "response", "request_id", "attempts"):
                value = getattr(error, name, None)
                if value is not None:
                    record["error"][name] = value
        if note is not None:
            record["note"] = note
        self._stream.write(json.dumps(
            record, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ) + "\n")
        self._stream.flush()

    def close(self):
        self._stream.close()


def _summary(state, log, response):
    return RunSummary(
        actions=log,
        cleared_channels=sorted(getattr(state, "cleared", set())),
        absent_channels=sorted(getattr(state, "absent", set())),
        virtual_time_s=float(response.get(
            "virtual_time_s", getattr(state, "virtual_time_s", 0.0)
        )),
        exit_reason=response.get("exit_reason"),
    )


def run_live_policy(policy, client, *, log_path, max_actions=10_000,
                    exit_safety_margin_s=15.0, clock=time.monotonic):
    """Run a policy serially until exit, stopping safely before the real deadline.

    This function never selects or starts a simulator test in the GUI.  The user
    must prepare the desired exercise/formal module and wait for interface-ready
    status before invoking the CLI.
    """
    if isinstance(max_actions, bool) or not isinstance(max_actions, int) or max_actions < 2:
        raise ValueError("max_actions 必须是至少为 2 的整数。")
    exit_safety_margin_s = float(exit_safety_margin_s)
    if not math.isfinite(exit_safety_margin_s) or exit_safety_margin_s < 0:
        raise ValueError("exit_safety_margin_s 不能为负数。")

    logger = JsonlActionLogger(log_path)
    state = policy.initial_state()
    log = []
    entered_at = None
    deadline = None
    last_response = {"virtual_time_s": 0.0}
    sequence = 0
    try:
        while sequence < max_actions:
            now = clock()
            if sequence == max_actions-1 and getattr(state, "entered", False):
                action = Action("exit", "exit-action-cap-"+uuid.uuid4().hex)
                note = "action_cap_safety_exit"
            elif deadline is not None and now >= deadline-exit_safety_margin_s:
                action = Action("exit", "exit-safety-"+uuid.uuid4().hex)
                note = "reality_deadline_safety_exit"
            else:
                action = policy.next_action(state)
                note = None
                if action is None:
                    raise RuntimeError("策略在终止前没有给出下一动作。")
            sequence += 1
            elapsed = None if entered_at is None else max(0.0, now-entered_at)
            try:
                response = client.execute(action)
            except SimulatorError as error:
                request_payload = None
                if hasattr(client, "robot_id"):
                    from .protocol import build_request_payload
                    request_payload = build_request_payload(action, client.robot_id)
                logger.write(
                    sequence=sequence, action=action,
                    request_payload=request_payload, error=error,
                    elapsed_real_s=elapsed, note=note,
                    http_status=getattr(error, "status", None),
                )
                raise
            exchange = getattr(client, "last_exchange", None)
            logger.write(
                sequence=sequence,
                action=action,
                request_payload=(exchange.payload if exchange else None),
                response=response,
                elapsed_real_s=elapsed,
                note=note,
                http_status=(exchange.http_status if exchange else None),
                attempts=(exchange.attempts if exchange else None),
            )
            item = {"action": action.as_dict(), "response": dict(response)}
            if note is not None:
                item["note"] = note
            log.append(item)
            last_response = response

            if note is not None:
                if hasattr(state, "virtual_time_s"):
                    state.virtual_time_s = float(response["virtual_time_s"])
                return _summary(state, log, response)

            policy.apply_response(state, action, response)
            if action.kind == "enter":
                entered_at = clock()
                deadline = entered_at+float(response["remaining_real_duration_s"])
            if action.kind == "exit":
                return _summary(state, log, response)
        raise RuntimeError("达到现场动作上限，策略未能进入可安全退出状态。")
    finally:
        logger.close()
