"""Held-Karp 精确 TSP（开放回路）与 B2 批量解耦策略变体。

B2 假设：先完成全部源的定位（certificate 级），再用精确 TSP 规划清除
顺序（n<=16），与现有"交错"流程同池对比。本策略独立于交错的
Q3Policy 状态机（仅继承共性方法），不改变交错路径的任何逻辑。
"""

from dataclasses import dataclass, field
import math

from q3.coverage import strip_clear_points
from q3.policy import Q3Policy, Q3State

from .refine_selector import select_refine_leg


def held_karp_tsp(points):
    """开放回路精确 TSP（起点任意、不返回）；O(n^2*2^n)。

    返回 (总路径长, 顺序索引列表)。n<=16 时 DP 表 2^16x16 可接受。
    """
    count = len(points)
    if count == 0:
        return 0.0, []
    if count == 1:
        return 0.0, [0]
    distances = [[math.dist(points[i], points[j]) for j in range(count)]
                 for i in range(count)]
    size = 1 << count
    infinity = float("inf")
    dp = [[infinity] * count for _ in range(size)]
    parent = [[-1] * count for _ in range(size)]
    for index in range(count):
        dp[1 << index][index] = 0.0
    for mask in range(size):
        for last in range(count):
            if not (mask >> last) & 1:
                continue
            current = dp[mask][last]
            if current >= infinity:
                continue
            for nxt in range(count):
                if (mask >> nxt) & 1:
                    continue
                new_mask = mask | (1 << nxt)
                cost = current + distances[last][nxt]
                if cost < dp[new_mask][nxt] - 1e-12:
                    dp[new_mask][nxt] = cost
                    parent[new_mask][nxt] = last
    full = size - 1
    last = min(range(count), key=lambda index: dp[full][index])
    total = dp[full][last]
    order = []
    mask = full
    while last != -1:
        order.append(last)
        previous = parent[mask][last]
        mask ^= 1 << last
        last = previous
    order.reverse()
    return total, order


@dataclass
class Q3BatchState(Q3State):
    batch_stage: str = "locate"          # locate -> clear -> done
    clear_queues: list = field(default_factory=list)  # 每源一个 [(点, 频道)]
    clear_index: int = 0
    certificate_ok: dict = field(default_factory=dict)  # channel -> bool


class Q3BatchPolicy(Q3Policy):
    """B2 变体：全部定位后 TSP 规划清除顺序（交错流程的对照臂）。

    定位阶段：逐源细化到 certificate（radius<=19.9）或细化上限；随后把
    全部清除点按 Held-Karp TSP 排序，逐源清除。无证书源的清除队列末尾
    自动补 strip 保底点（沿用既有 strip_clear_points 网格）。
    """

    def __init__(self, *, tour_refine=False, tspn_clear=False,
                 **kwargs):
        super().__init__(**kwargs)
        self.tour_refine = tour_refine
        self.tspn_clear = tspn_clear

    def initial_state(self):
        return Q3BatchState()

    # ---------- 定位阶段 ----------
    def _locate_next(self, state):
        located = set(state.certificate_ok)
        remaining = [channel for channel in sorted(state.sources)
                     if channel not in state.cleared
                     and channel not in located]
        if remaining:
            channel = remaining[0]
            track = state.sources[channel]
            radius = track.region["minimum_enclosing_circle"]["radius"]
            if radius <= 19.9:
                center = tuple(track.region["minimum_enclosing_circle"]
                               ["center"])
                state.clear_queues.append([(center, channel)])
                state.certificate_ok[channel] = True
                return None
            if track.refinements < self.max_refinements:
                if self.tour_refine:
                    point, _ = select_refine_leg(
                        track.region, track.observations,
                        current_position=state.position,
                        current_channel=state.current_channel,
                        error_deg=self.error_deg)
                else:
                    point = self._refinement_point(state, track)
                return self._action(state, "measure", point, channel,
                                    "batch_refine")
            center = tuple(track.region["minimum_enclosing_circle"]["center"])
            first = track.observations[0]
            state.clear_queues.append(
                [(center, channel)]
                + [(point, channel)
                   for point in strip_clear_points(first.position,
                                                   first.bearing_deg)])
            state.certificate_ok[channel] = False
            return None
        self._tsp_sort(state)
        state.batch_stage = "clear"
        return None

    def _tsp_sort(self, state):
        centers = [queue[0][0] for queue in state.clear_queues]
        _, order = held_karp_tsp(centers)
        state.clear_queues = [state.clear_queues[index] for index in order]

    # ---------- 清除阶段 ----------
    def _clear_next(self, state):
        while state.clear_index < len(state.clear_queues):
            queue = state.clear_queues[state.clear_index]
            if not queue:
                state.clear_index += 1
                continue
            point, channel = queue[0]
            if channel in state.cleared:
                state.clear_index += 1
                continue
            track = state.sources.get(channel)
            radius = None
            if (track is not None and track.region is not None
                    and track.region.get("status") == "bounded"):
                radius = track.region["minimum_enclosing_circle"]["radius"]
            if radius is not None and radius <= 19.9:
                # A：TSPN 清除端点（可选）——停在清除邻域边界朝下一目标
                # 方向，|p-源| <= (20-r)+r = 20 数学保证，节省后续移动。
                center = tuple(track.region["minimum_enclosing_circle"]
                               ["center"])
                if self.tspn_clear:
                    next_center = self._next_queue_center(state,
                                                          state.clear_index)
                    if next_center is not None:
                        dx = next_center[0] - center[0]
                        dy = next_center[1] - center[1]
                        norm = math.hypot(dx, dy)
                        if norm > 1e-9:
                            reach = max(0.0, 20.0 - radius)
                            point = (center[0] + reach * dx / norm,
                                     center[1] + reach * dy / norm)
                            return self._action(state, "clear", point,
                                                channel, "batch_clear")
                return self._action(state, "clear", center, channel,
                                    "batch_clear")
            return self._action(state, "clear", point, channel,
                                "batch_clear")
        if state.cleared | state.absent != set(range(1, 21)):
            raise RuntimeError("批量清除未覆盖全部频道定性。")
        state.phase = "exit"
        return None

    @staticmethod
    def _next_queue_center(state, index):
        """返回 index 之后下一个未清除源的清除队列首点（目标中心）。"""
        for j in range(index + 1, len(state.clear_queues)):
            queue = state.clear_queues[j]
            if queue and queue[0][1] not in state.cleared:
                return queue[0][0]
        return None

    def _resolve_action(self, state):
        if state.batch_stage == "locate":
            return self._locate_next(state)
        return self._clear_next(state)

    def apply_response(self, state, action, response):
        if action != state.pending:
            raise RuntimeError("收到的响应与当前待处理动作不一致。")
        mode = state.pending_mode
        if mode not in ("batch_refine", "batch_clear"):
            # 扫描测量、enter、near、exit 等完整委托标准状态机。
            return super().apply_response(state, action, response)
        state.pending = None
        state.pending_mode = None
        if response.get("accepted") is not True:
            raise RuntimeError("模拟器拒绝了动作。")
        state.virtual_time_s = float(response.get("virtual_time_s",
                                                  state.virtual_time_s))
        state.position = action.position
        if action.kind == "measure" and mode == "batch_refine":
            state.current_channel = action.channel
            self._record_measurement(state, action, response, mode="refine")
            state.sources[action.channel].refinements += 1
            return
        if action.kind == "clear" and mode == "batch_clear":
            if response.get("clear_result") == "success":
                state.cleared.add(action.channel)
                state.forced_clear = None
                state.clear_index += 1
            else:
                queue = state.clear_queues[state.clear_index]
                if queue:
                    queue.pop(0)  # 队首失败：丢弃该点（无证书源有保底尾缀）
            return
        raise RuntimeError(f"批量模式与动作不匹配：{action.kind}/{mode}")