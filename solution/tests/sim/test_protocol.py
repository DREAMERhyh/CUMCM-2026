import math
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import Action
from sim.errors import SimulatorProtocolError
from sim.protocol import (
    build_request_payload,
    decode_response_body,
    encode_request_payload,
    validate_response,
)


def common(accepted=True, virtual_time=0):
    return {
        "accepted": accepted,
        "real_timestamp_ms": 1760000000000,
        "virtual_time_s": virtual_time,
    }


class ProtocolTestbench(unittest.TestCase):
    def test_four_request_payload_shapes_are_exact(self):
        enter = build_request_payload(Action("enter", "e-1"), "team")
        exit_payload = build_request_payload(Action("exit", "x-1"), "team")
        measure = build_request_payload(
            Action("measure", "m-1", (3, 4), 20), "team"
        )
        clear = build_request_payload(
            Action("clear", "c-1", (-2_000_000, 2_000_000), 1), "team"
        )
        self.assertEqual(set(enter), {"arena_id", "robot_id", "request_id"})
        self.assertEqual(set(exit_payload), set(enter))
        self.assertEqual(
            set(measure),
            {"arena_id", "robot_id", "request_id", "position", "channel"},
        )
        self.assertEqual(measure["position"], {"x": 3.0, "y": 4.0})
        self.assertEqual(clear["channel"], 1)

    def test_invalid_action_fields_are_rejected_locally(self):
        invalid = [
            Action("enter", "e", (0, 0), None),
            Action("measure", "m", None, 1),
            Action("measure", "m", (0, 0), 0),
            Action("measure", "m", (0, 0), 1.5),
            Action("measure", "m", (math.nan, 0), 1),
            Action("measure", "m", (2_000_001, 0), 1),
        ]
        for action in invalid:
            with self.subTest(action=action):
                with self.assertRaises(SimulatorProtocolError):
                    build_request_payload(action, "team")

    def test_identifier_utf8_lengths_and_hidden_characters(self):
        with self.assertRaises(SimulatorProtocolError):
            build_request_payload(Action("enter", ""), "team")
        with self.assertRaises(SimulatorProtocolError):
            build_request_payload(Action("enter", "ok"), "x"*65)
        with self.assertRaises(SimulatorProtocolError):
            build_request_payload(Action("enter", "bad\nvalue"), "team")
        payload = build_request_payload(Action("enter", "编号-1"), "队伍")
        self.assertEqual(payload["robot_id"], "队伍")

    def test_encoding_is_compact_utf8_without_bom(self):
        payload = build_request_payload(Action("enter", "编号-1"), "队伍")
        body = encode_request_payload(payload)
        self.assertFalse(body.startswith(b"\xef\xbb\xbf"))
        self.assertIn("队伍".encode("utf-8"), body)
        self.assertNotIn(b" ", body)

    def test_strict_response_decoder_rejects_duplicate_bom_and_nan(self):
        for body in (
            b'{"accepted":true,"accepted":false}',
            b"\xef\xbb\xbf{}",
            b'{"accepted":NaN}',
            b"[]",
        ):
            with self.subTest(body=body):
                with self.assertRaises(SimulatorProtocolError):
                    decode_response_body(body)

    def test_enter_response_contract(self):
        action = Action("enter", "e")
        response = {
            **common(),
            "max_virtual_duration_s": 360000,
            "max_real_duration_s": 1200,
            "remaining_real_duration_s": 1199,
        }
        self.assertIs(validate_response(action, 200, response), response)
        response["remaining_real_duration_s"] = 1200.5
        with self.assertRaises(SimulatorProtocolError):
            validate_response(action, 200, response)

    def test_measure_conditional_fields(self):
        action = Action("measure", "m", (0, 0), 1)
        validate_response(action, 200, {**common(), "measure_result": "near"})
        validate_response(action, 200, {
            **common(), "measure_result": "direction", "svd_deg": 359.99
        })
        with self.assertRaises(SimulatorProtocolError):
            validate_response(action, 200, {
                **common(), "measure_result": "near", "svd_deg": 1.0
            })
        with self.assertRaises(SimulatorProtocolError):
            validate_response(action, 200, {
                **common(), "measure_result": "direction"
            })

    def test_clear_exit_and_rejection_contracts(self):
        validate_response(
            Action("clear", "c", (0, 0), 1), 200,
            {**common(), "clear_result": "no_target_in_range"},
        )
        validate_response(
            Action("exit", "x"), 200,
            {**common(), "exit_reason": "user_exit"},
        )
        validate_response(Action("enter", "e"), 200, common(False, 0))
        with self.assertRaises(SimulatorProtocolError):
            validate_response(Action("enter", "e"), 200, common(False, 1))


if __name__ == "__main__":
    unittest.main()
