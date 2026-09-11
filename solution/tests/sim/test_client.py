import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import sys
import threading
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import Action
from sim.client import HttpRobotClient
from sim.errors import (
    ConcurrentRequestError,
    IdempotencyConflictError,
    SimulatorHttpError,
    SimulatorProtocolError,
    SimulatorRejectedError,
)


def response_body(accepted=True, **extra):
    return {
        "accepted": accepted,
        "real_timestamp_ms": 1760000000000,
        "virtual_time_s": 0,
        **extra,
    }


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        size = int(self.headers["Content-Length"])
        body = self.rfile.read(size)
        self.server.records.append({
            "path": self.path,
            "content_type": self.headers.get("Content-Type"),
            "body": body,
        })
        item = self.server.responses.pop(0)
        if item is None:
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        status, payload = item
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        pass


class LocalServer:
    def __init__(self, responses):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.responses = list(responses)
        self.server.records = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_port}"


class HttpClientTestbench(unittest.TestCase):
    def test_successful_exchange_uses_exact_path_header_and_body(self):
        payload = response_body(
            max_virtual_duration_s=360000,
            max_real_duration_s=1200,
            remaining_real_duration_s=1200,
        )
        with LocalServer([(200, payload)]) as local:
            client = HttpRobotClient("team", local.base_url, retry_count=0)
            exchange = client.request(Action("enter", "e-1"))
        self.assertEqual(exchange.http_status, 200)
        self.assertEqual(local.server.records[0]["path"], "/enter")
        self.assertEqual(
            local.server.records[0]["content_type"],
            "application/json; charset=utf-8",
        )
        self.assertEqual(
            json.loads(local.server.records[0]["body"]),
            {"arena_id": "default", "robot_id": "team", "request_id": "e-1"},
        )

    def test_transport_retry_reuses_identical_request(self):
        payload = response_body(
            max_virtual_duration_s=360000,
            max_real_duration_s=1200,
            remaining_real_duration_s=1200,
        )
        with LocalServer([None, (200, payload)]) as local:
            client = HttpRobotClient(
                "team", local.base_url, retry_count=1, retry_delay_s=0
            )
            exchange = client.request(Action("enter", "retry-1"))
        self.assertEqual(exchange.attempts, 2)
        self.assertEqual(len(local.server.records), 2)
        self.assertEqual(local.server.records[0], local.server.records[1])

    def test_execute_raises_typed_rejection_and_http_errors(self):
        with LocalServer([(200, response_body(False))]) as local:
            client = HttpRobotClient("team", local.base_url, retry_count=0)
            with self.assertRaises(SimulatorRejectedError):
                client.execute(Action("enter", "rejected"))
        with LocalServer([(400, response_body(False))]) as local:
            client = HttpRobotClient("team", local.base_url, retry_count=0)
            with self.assertRaises(SimulatorHttpError) as caught:
                client.execute(Action("enter", "bad"))
        self.assertEqual(caught.exception.status, 400)

    def test_rejected_id_can_be_reused_after_correction(self):
        accepted = response_body(
            max_virtual_duration_s=360000,
            max_real_duration_s=1200,
            remaining_real_duration_s=1200,
        )
        with LocalServer([
            (200, response_body(False)),
            (200, accepted),
        ]) as local:
            client = HttpRobotClient("team", local.base_url, retry_count=0)
            with self.assertRaises(SimulatorRejectedError):
                client.execute(Action("exit", "reusable"))
            response = client.execute(Action("enter", "reusable"))
        self.assertTrue(response["accepted"])
        self.assertEqual([item["path"] for item in local.server.records],
                         ["/exit", "/enter"])

    def test_accepted_id_cannot_be_rebound_to_different_action(self):
        payload = response_body(
            max_virtual_duration_s=360000,
            max_real_duration_s=1200,
            remaining_real_duration_s=1200,
        )
        with LocalServer([(200, payload)]) as local:
            client = HttpRobotClient("team", local.base_url, retry_count=0)
            client.execute(Action("enter", "same"))
            with self.assertRaises(IdempotencyConflictError):
                client.execute(Action("exit", "same"))
        self.assertEqual(len(local.server.records), 1)

    def test_malformed_accepted_response_still_binds_request_id(self):
        malformed = response_body(
            max_virtual_duration_s=360000,
            max_real_duration_s=1200,
            remaining_real_duration_s=1200,
            unexpected="field",
        )
        with LocalServer([(200, malformed)]) as local:
            client = HttpRobotClient("team", local.base_url, retry_count=0)
            with self.assertRaises(SimulatorProtocolError):
                client.execute(Action("enter", "ambiguous"))
            with self.assertRaises(IdempotencyConflictError):
                client.execute(Action("exit", "ambiguous"))
        self.assertEqual(len(local.server.records), 1)

    def test_concurrent_request_is_rejected_before_network_io(self):
        payload = response_body(
            max_virtual_duration_s=360000,
            max_real_duration_s=1200,
            remaining_real_duration_s=1200,
        )
        with LocalServer([(200, payload)]) as local:
            client = HttpRobotClient("team", local.base_url, retry_count=0)
            client._in_flight.acquire()
            try:
                with self.assertRaises(ConcurrentRequestError):
                    client.execute(Action("enter", "e"))
            finally:
                client._in_flight.release()
        self.assertEqual(local.server.records, [])

    def test_non_loopback_url_is_rejected(self):
        for url in ("https://127.0.0.1:2026", "http://example.com:2026"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    HttpRobotClient("team", url)

    def test_nonfinite_or_noninteger_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            HttpRobotClient("team", timeout_s=float("nan"))
        with self.assertRaises(ValueError):
            HttpRobotClient("team", retry_delay_s=float("inf"))
        with self.assertRaises(ValueError):
            HttpRobotClient("team", retry_count=2.0)


if __name__ == "__main__":
    unittest.main()
