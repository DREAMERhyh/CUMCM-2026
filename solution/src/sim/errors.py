"""Typed failures raised by the official-simulator adapter."""


class SimulatorError(RuntimeError):
    """Base class for simulator communication failures."""


class SimulatorProtocolError(SimulatorError):
    """A request or response violates the confirmed JSON protocol."""


class SimulatorTransportError(SimulatorError):
    """No complete HTTP response was obtained after safe retries."""

    def __init__(self, message, *, request_id=None, attempts=None):
        super().__init__(message)
        self.request_id = request_id
        self.attempts = attempts


class SimulatorHttpError(SimulatorError):
    """The simulator returned a non-200 HTTP response."""

    def __init__(self, status, response):
        super().__init__(f"模拟器返回 HTTP {status}。")
        self.status = status
        self.response = response


class SimulatorRejectedError(SimulatorError):
    """HTTP succeeded, but the simulator rejected the action."""

    def __init__(self, response):
        super().__init__("模拟器返回 accepted=false，本次动作未执行。")
        self.response = response


class ConcurrentRequestError(SimulatorError):
    """A second action was attempted while another action was in flight."""


class IdempotencyConflictError(SimulatorError):
    """A request_id was reused for a different path or request body."""

