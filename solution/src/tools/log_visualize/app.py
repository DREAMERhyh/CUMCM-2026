"""Matplotlib desktop player for Q3 simulator action logs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    source_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(source_root))

from tools.log_visualize.model import load_replay, resolve_log_path

ARENA_RADIUS_M = 1800.0
SOLUTION_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_DIR = SOLUTION_ROOT / "output" / "sim"


def _format_virtual_clock(seconds):
    seconds = max(0.0, float(seconds))
    if seconds < 1e-9:
        return "00s"
    if seconds < 60:
        return f"{seconds:05.2f}s"
    hours, remainder = divmod(seconds, 3600)
    minutes, remainder = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{remainder:05.2f}"


def _response_text(frame):
    if frame.action is None:
        return "尚未执行动作"
    if frame.response is None:
        return "无有效响应"
    kind = frame.action["kind"]
    if kind == "measure":
        result = frame.response.get("measure_result", "未知")
        if result == "direction":
            return f"direction, {frame.response.get('svd_deg', '?')}°"
        return str(result)
    if kind == "clear":
        return str(frame.response.get("clear_result", "未知"))
    if kind == "exit":
        return str(frame.response.get("exit_reason", "未知"))
    return "accepted" if frame.response.get("accepted") else "rejected"


class LogPlayer:
    def __init__(self, replay):
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Button, RadioButtons

        self.plt = plt
        self.replay = replay
        self.index = 0
        self.speed = 1
        self.playing = False

        plt.rcParams["font.sans-serif"] = [
            "Microsoft YaHei", "SimHei", "DejaVu Sans"
        ]
        plt.rcParams["axes.unicode_minus"] = False
        self.figure = plt.figure(figsize=(13.5, 8.2), facecolor="#f7f8f5")
        manager = self.figure.canvas.manager
        if manager is not None:
            manager.set_window_title("Q3 模拟器日志回放")
        self.axis = self.figure.add_axes([0.055, 0.18, 0.62, 0.76])
        self.info_axis = self.figure.add_axes([0.705, 0.22, 0.275, 0.67])
        self.info_axis.axis("off")
        self.info_text = self.info_axis.text(
            0.0, 1.0, "", va="top", ha="left", fontsize=10,
            linespacing=1.5, color="#263238",
        )
        self.clock_text = self.figure.text(
            0.965, 0.965, "虚拟时间  00s", va="top", ha="right",
            fontsize=17, fontweight="bold", color="#1b5e20",
            bbox={
                "boxstyle": "round,pad=0.38",
                "facecolor": "#e8f5e9",
                "edgecolor": "#81a984",
                "alpha": 0.96,
            },
        )

        previous_axis = self.figure.add_axes([0.07, 0.065, 0.10, 0.055])
        next_axis = self.figure.add_axes([0.185, 0.065, 0.10, 0.055])
        reset_axis = self.figure.add_axes([0.30, 0.065, 0.10, 0.055])
        play_axis = self.figure.add_axes([0.43, 0.065, 0.15, 0.055])
        speed_axis = self.figure.add_axes([0.68, 0.035, 0.13, 0.11])

        self.previous_button = Button(previous_axis, "上一步")
        self.next_button = Button(next_axis, "下一步")
        self.reset_button = Button(reset_axis, "重置")
        self.play_button = Button(play_axis, "自动播放")
        self.speed_buttons = RadioButtons(
            speed_axis, ("1x", "2x", "4x"), active=0,
            activecolor="#2a9d8f",
        )
        speed_axis.set_title("播放速度", fontsize=9)

        self.previous_button.on_clicked(self.previous)
        self.next_button.on_clicked(self.next)
        self.reset_button.on_clicked(self.reset)
        self.play_button.on_clicked(self.toggle_play)
        self.speed_buttons.on_clicked(self.set_speed)
        self.figure.canvas.mpl_connect("key_press_event", self.on_key)
        self.figure.canvas.mpl_connect("close_event", self.on_close)
        self.timer = self.figure.canvas.new_timer(interval=1000)
        self.timer.add_callback(self.tick)
        self.draw()

    def _stop(self):
        if self.playing:
            self.timer.stop()
            self.playing = False
            self.play_button.label.set_text("自动播放")

    def previous(self, _event=None):
        self._stop()
        if self.index > 0:
            self.index -= 1
            self.draw()

    def next(self, _event=None):
        self._stop()
        if self.index < len(self.replay.frames) - 1:
            self.index += 1
            self.draw()

    def reset(self, _event=None):
        self._stop()
        self.index = 0
        self.draw()

    def toggle_play(self, _event=None):
        if self.playing:
            self._stop()
            self.figure.canvas.draw_idle()
            return
        if self.index >= len(self.replay.frames) - 1:
            self.index = 0
        self.playing = True
        self.play_button.label.set_text("暂停")
        self.timer.interval = round(1000 / self.speed)
        self.timer.start()
        self.draw()

    def set_speed(self, label):
        self.speed = int(label.rstrip("x"))
        self.timer.interval = round(1000 / self.speed)

    def tick(self):
        if not self.playing:
            return
        if self.index >= len(self.replay.frames) - 1:
            self._stop()
            self.figure.canvas.draw_idle()
            return
        self.index += 1
        self.draw()

    def on_key(self, event):
        if event.key in ("right", "n"):
            self.next()
        elif event.key in ("left", "p"):
            self.previous()
        elif event.key == "home":
            self.reset()
        elif event.key == " ":
            self.toggle_play()

    def on_close(self, _event):
        self._stop()

    def _draw_markers(self, points, *, marker, color, size):
        if not points:
            return
        xs = [point[0] for point in points.values()]
        ys = [point[1] for point in points.values()]
        self.axis.scatter(
            xs, ys, marker=marker, color=color, s=size, linewidths=2,
            zorder=7,
        )
        for channel, point in sorted(points.items()):
            self.axis.annotate(
                f"CH{channel}", point, xytext=(6, 5),
                textcoords="offset points", fontsize=8, color=color,
                zorder=8,
            )

    def _info(self, frame):
        action = frame.action or {}
        position = frame.robot_position
        channel = action.get("channel", "—")
        action_name = action.get("kind", "准备")
        sequence = frame.sequence if frame.sequence is not None else "—"
        time_lines = []
        summary = self.replay.time_summary
        for name, seconds in summary.items():
            time_lines.append(
                f"  {name:<4} {seconds:8.2f} s  "
                f"{summary.percentage(seconds):6.2f}%"
            )
        warning = "；".join(frame.warnings[-2:]) if frame.warnings else "无"
        return (
            f"文件：{self.replay.path.name}\n"
            f"动作：{frame.index}/{len(self.replay.records)}\n"
            f"序号：{sequence}  类型：{action_name}  频道：{channel}\n"
            f"反馈：{_response_text(frame)}\n"
            f"位置：({position[0]:.2f}, {position[1]:.2f}) m\n"
            f"本步虚拟时间：{frame.action_virtual_delta_s:.2f} s\n"
            f"累计虚拟时间：{frame.virtual_time_s:.2f} s\n"
            f"已清除：{len(frame.cleared_sources)}\n"
            f"未清除估计：{len(frame.active_sources)}\n\n"
            f"全程时间构成\n" + "\n".join(time_lines) +
            f"\n  合计   {summary.total_virtual_s:8.2f} s"
            f"\n  现实墙钟 {summary.real_wall_s:7.2f} s\n\n"
            f"警告：{warning}\n\n"
            "说明：日志不含真实源坐标。\n"
            "星号/叉号优先取后验区域中心；\n"
            "无可用区域时取 near 或成功清除位置。"
        )

    def draw(self):
        from matplotlib.lines import Line2D
        from matplotlib.patches import Circle, FancyArrowPatch, Patch, Polygon

        frame = self.replay.frames[self.index]
        axis = self.axis
        axis.clear()
        axis.set_facecolor("#fbfcfa")
        arena = Circle(
            (0, 0), ARENA_RADIUS_M, facecolor="#dff3df",
            edgecolor="#75a875", linewidth=1.5, alpha=0.70, zorder=0,
        )
        axis.add_patch(arena)
        for _channel, vertices in sorted(frame.regions.items()):
            axis.add_patch(Polygon(
                vertices, closed=True, facecolor="#f4a261",
                edgecolor="#d97706", linewidth=1.1, alpha=0.24, zorder=2,
            ))

        for previous, current in zip(
                frame.successful_clear_positions,
                frame.successful_clear_positions[1:]):
            if previous == current:
                continue
            axis.add_patch(FancyArrowPatch(
                previous, current, arrowstyle="-|>", color="#123a66",
                linewidth=0.9, mutation_scale=9, shrinkA=5, shrinkB=5,
                alpha=0.88, zorder=5,
            ))

        self._draw_markers(
            frame.active_sources, marker="*", color="#1565c0", size=145,
        )
        self._draw_markers(
            frame.cleared_sources, marker="x", color="#d32f2f", size=95,
        )
        robot = frame.robot_position
        axis.scatter(
            [robot[0]], [robot[1]], marker="^", color="#111111",
            edgecolors="white", linewidths=0.8, s=110, zorder=10,
        )

        axis.set_xlim(-1950, 1950)
        axis.set_ylim(-1950, 1950)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel("x / m")
        axis.set_ylabel("y / m")
        axis.set_title(
            f"Q3 动作日志回放  |  动作 {frame.index}/{len(self.replay.records)}"
        )
        axis.axhline(0, color="#b0bec5", linewidth=0.7, zorder=1)
        axis.axvline(0, color="#b0bec5", linewidth=0.7, zorder=1)
        axis.grid(color="#dfe7e3", linewidth=0.6, alpha=0.65)
        legend = [
            Patch(facecolor="#dff3df", edgecolor="#75a875", label="1800 m 圆形区域"),
            Patch(
                facecolor="#f4a261", edgecolor="#d97706", alpha=0.5,
                label="已测相交区域",
            ),
            Line2D(
                [], [], marker="^", color="none", markerfacecolor="#111111",
                markersize=8, label="机器狗位置",
            ),
            Line2D(
                [], [], marker="*", color="none", markerfacecolor="#1565c0",
                markeredgecolor="#1565c0", markersize=11,
                label="未清除源估计",
            ),
            Line2D(
                [], [], marker="x", color="#d32f2f", linestyle="none",
                markersize=8, markeredgewidth=2, label="已清除源估计",
            ),
            Line2D(
                [], [], color="#123a66", linewidth=0.9, marker=">",
                markersize=5, markevery=[1], label="成功清除间移动路径",
            ),
        ]
        axis.legend(
            handles=legend, loc="upper left", fontsize=8, framealpha=0.92,
        )
        self.info_text.set_text(self._info(frame))
        self.clock_text.set_text(
            f"虚拟时间  {_format_virtual_clock(frame.virtual_time_s)}"
        )
        self.figure.canvas.draw_idle()

    def show(self):
        self.plt.show()

    def save(self, path, *, frame_index=None):
        if frame_index is not None:
            if not 0 <= frame_index < len(self.replay.frames):
                raise ValueError(
                    f"帧号须在 0..{len(self.replay.frames)-1} 之间。"
                )
            self.index = frame_index
            self.draw()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.figure.savefig(
            target, dpi=170, facecolor=self.figure.get_facecolor()
        )
        return target


def build_parser():
    parser = argparse.ArgumentParser(
        description="逐动作播放 Q3 官方模拟器 JSONL 日志。"
    )
    parser.add_argument(
        "log", nargs="?",
        help="日志路径或 output/sim 下的文件名；省略时读取最新 Q3 日志。",
    )
    parser.add_argument(
        "--log-dir", default=str(DEFAULT_LOG_DIR),
        help="省略日志参数时搜索的目录。",
    )
    parser.add_argument(
        "--frame", type=int, default=0,
        help="初始帧号；0 表示尚未执行任何动作。",
    )
    parser.add_argument(
        "--save-frame", help="将初始帧保存为 PNG/SVG，用于无界面检查。",
    )
    parser.add_argument(
        "--no-show", action="store_true",
        help="不打开交互窗口，通常与 --save-frame 一起使用。",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_show:
        import matplotlib
        matplotlib.use("Agg")
    try:
        path = resolve_log_path(args.log, log_dir=args.log_dir)
        replay = load_replay(path)
        player = LogPlayer(replay)
        if not 0 <= args.frame < len(replay.frames):
            parser.error(f"--frame 须在 0..{len(replay.frames)-1} 之间。")
        player.index = args.frame
        player.draw()
        if args.save_frame:
            output = player.save(args.save_frame)
            print(f"已保存：{output}")
        summary = replay.time_summary
        print(
            f"日志：{path}\n动作：{len(replay.records)}；"
            f"成功清除：{replay.clear_successes}；"
            f"虚拟时间：{summary.total_virtual_s:.6f} s；"
            f"现实墙钟：{summary.real_wall_s:.3f} s"
        )
        if not args.no_show:
            player.show()
        else:
            player.plt.close(player.figure)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(f"日志可视化失败：{error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
