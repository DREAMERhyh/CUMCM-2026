"""Sequential policy runner with an explicit action cap."""

from common.models import RunSummary


def run_policy(policy, client, *, max_actions=10_000):
    state = policy.initial_state()
    log = []
    for _ in range(max_actions):
        action = policy.next_action(state)
        if action is None:
            raise RuntimeError("策略在终止前没有给出下一动作。")
        response = client.execute(action)
        log.append({"action": action.as_dict(), "response": dict(response)})
        policy.apply_response(state, action, response)
        if action.kind == "exit" and response.get("accepted") is True:
            return RunSummary(
                actions=log,
                cleared_channels=sorted(state.cleared),
                absent_channels=sorted(state.absent),
                virtual_time_s=state.virtual_time_s,
                exit_reason=response.get("exit_reason"),
            )
    raise RuntimeError("达到离线动作上限，策略未终止。")

