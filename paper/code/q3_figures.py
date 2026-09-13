"""Generate the scan-layout and decision-tree figures used in Q3."""

import os
from math import cos, pi, sin
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cumcm-q3-paper")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import (
    Circle,
    FancyArrowPatch,
    FancyBboxPatch,
    Polygon,
    Rectangle,
)


PAPER_DIR = Path(__file__).resolve().parents[1]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Noto Sans CJK JP", "Droid Sans Fallback",
                         "DejaVu Sans"],
    "axes.unicode_minus": False,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def save_figure(fig, stem):
    fig.savefig(PAPER_DIR / f"figures/{stem}.pdf", bbox_inches="tight")
    fig.savefig(PAPER_DIR / f"figures/{stem}.png", dpi=240,
                bbox_inches="tight")
    plt.close(fig)


def plot_scan_layout():
    arena_radius = 1800.0
    scan_radius = 960.0
    receive_radius = 1000.0
    points = [
        (scan_radius * cos(k * pi / 4), scan_radius * sin(k * pi / 4))
        for k in range(8)
    ]

    fig, ax = plt.subplots(figsize=(7.2, 7.0))
    ax.add_patch(Circle(
        (0.0, 0.0), arena_radius, facecolor="#eaf3f8",
        edgecolor="#245b78", lw=1.8, zorder=0,
    ))
    for point in points:
        ax.add_patch(Circle(
            point, receive_radius, facecolor="#74c69d", alpha=0.035,
            edgecolor="#40916c", lw=0.55, ls="--", zorder=1,
        ))

    route = [(0.0, 0.0)] + points
    for first, second in zip(route, route[1:]):
        ax.add_patch(FancyArrowPatch(
            first, second, arrowstyle="-|>", mutation_scale=9,
            color="#c44536", lw=1.25, shrinkA=4, shrinkB=5, zorder=3,
        ))

    xs, ys = zip(*points)
    ax.scatter(xs, ys, s=38, color="#c44536", edgecolors="white",
               linewidths=0.7, zorder=5)
    for index, point in enumerate(points):
        horizontal = 8 if point[0] >= 0 else -25
        vertical = 7 if point[1] >= 0 else -17
        ax.annotate(rf"$P_{{{index}}}$", point,
                    xytext=(horizontal, vertical), textcoords="offset points",
                    fontsize=10, zorder=6)

    ax.scatter([0.0], [0.0], color="black", s=28, zorder=6)
    ax.annotate(r"$O_0$", (0.0, 0.0), xytext=(6, 6),
                textcoords="offset points", fontsize=10)
    ax.add_patch(Circle(
        (0.0, 0.0), scan_radius, fill=False, edgecolor="0.45",
        lw=0.8, ls=":", zorder=2,
    ))

    theta = pi / 8
    worst = (arena_radius * cos(theta), arena_radius * sin(theta))
    ax.scatter([worst[0]], [worst[1]], marker="*", s=70,
               color="#6a3d9a", zorder=7)
    ax.plot([worst[0], points[0][0]], [worst[1], points[0][1]],
            color="#6a3d9a", lw=0.9, ls="-.", zorder=4)
    ax.plot([worst[0], points[1][0]], [worst[1], points[1][1]],
            color="#6a3d9a", lw=0.9, ls="-.", zorder=4)
    ax.annotate(r"$X^*$", worst, xytext=(7, 4),
                textcoords="offset points", fontsize=10, color="#6a3d9a")

    handles = [
        Line2D([0], [0], color="#245b78", lw=1.8,
               label=r"目标圆形区域 $\overline{B}(O_0,1800)$"),
        Line2D([0], [0], marker="o", color="none",
               markerfacecolor="#c44536", markeredgecolor="white",
               markersize=7, label="八个扫描驻留点"),
        Line2D([0], [0], color="#c44536", lw=1.3,
               label="机器狗扫描顺序"),
        Line2D([0], [0], color="#40916c", lw=0.8, ls="--",
               label=r"半径 $1000\,\mathrm{m}$ 的保证接收圆"),
        Line2D([0], [0], marker="*", color="none",
               markerfacecolor="#6a3d9a", markersize=9,
               label="最不利覆盖位置"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=8.5,
              framealpha=0.95)
    limit = 2920.0
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(r"$x/\mathrm{m}$")
    ax.set_ylabel(r"$y/\mathrm{m}$")
    ax.grid(alpha=0.12)
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.09, top=0.98)
    save_figure(fig, "q3-eight-point-scan")


def _box(ax, center, text, *, width=0.19, height=0.065,
         face="#eef4f8", edge="#245b78", fontsize=9.0, rounded=False):
    x, y = center
    lower_left = (x - width / 2, y - height / 2)
    if rounded:
        patch = FancyBboxPatch(
            lower_left, width, height,
            boxstyle="round,pad=0.006,rounding_size=0.008",
            facecolor=face, edgecolor=edge, linewidth=1.0, zorder=4,
        )
    else:
        patch = Rectangle(
            lower_left, width, height,
            facecolor=face, edgecolor=edge, linewidth=1.0, zorder=4,
        )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize,
            linespacing=1.25, zorder=5)
    return {"center": center, "patch": patch}


def _diamond(ax, center, text, *, width=0.12, height=0.055,
             face="#fff5d6", edge="#b07d16", fontsize=9.0):
    x, y = center
    vertices = [(x, y + height), (x + width, y),
                (x, y - height), (x - width, y)]
    patch = Polygon(vertices, closed=True, facecolor=face,
                    edgecolor=edge, lw=1.0, zorder=4)
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize,
            linespacing=1.18, zorder=5)
    return {"center": center, "patch": patch}


def _arrow(ax, source, target, text=None, *, rad=0.0, color="0.28",
           label_pos=None):
    start = source["center"]
    end = target["center"]
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=10, lw=0.9,
        color=color, connectionstyle=f"arc3,rad={rad}", zorder=2,
        patchA=source["patch"], patchB=target["patch"],
        shrinkA=0.8, shrinkB=0.8,
    ))
    if text:
        if label_pos is None:
            x = (start[0] + end[0]) / 2
            y = (start[1] + end[1]) / 2
        else:
            x, y = label_pos
        ax.text(x, y, text, ha="center", va="center",
                fontsize=8.0, color=color,
                bbox={"facecolor": "white", "edgecolor": "none",
                      "pad": 0.5}, zorder=6)


def plot_decision_tree():
    fig, ax = plt.subplots(figsize=(11.2, 8.0))
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    enter = _box(ax, (0.50, 0.955), "进入测试", width=0.12,
                 height=0.045, rounded=True,
                 face="#d8f3dc", edge="#2d6a4f")
    scan = _box(ax, (0.50, 0.875),
                "依次访问八个等角扫描点\n并检测 1-20 频道",
                width=0.20, height=0.075)
    result = _diamond(ax, (0.50, 0.775), "检测结果")
    no_signal = _box(ax, (0.16, 0.675), "无信号\n继续当前扫描",
                     width=0.19, height=0.075,
                     face="#f3f4f6", edge="#6b7280")
    bearing = _box(ax, (0.50, 0.675),
                   "获得示向度\n更新该频道定位区域",
                   width=0.20, height=0.075)
    close = _box(ax, (0.84, 0.675), "近距离\n立即在原地清除",
                 width=0.19, height=0.075,
                 face="#fee2e2", edge="#b91c1c")
    scan_done = _diamond(ax, (0.50, 0.565), "八点扫描\n是否完成",
                         height=0.060)
    summarize = _box(ax, (0.50, 0.465),
                     "汇总已发现源与无源频道\n选择距当前位置最近的未处理源",
                     width=0.25, height=0.075)
    located = _diamond(ax, (0.50, 0.365),
                       r"$r_j\leq19.9\,\mathrm{m}$", height=0.045)
    reliable = _box(ax, (0.18, 0.255),
                    "加入可靠清除队列\n记录最小包围圆中心",
                    width=0.21, height=0.075,
                    face="#d8f3dc", edge="#2d6a4f")
    trial_ready = _diamond(ax, (0.50, 0.245),
                           r"$r_j\leq40\,\mathrm{m}$", height=0.045)
    trial_queue = _box(ax, (0.50, 0.145),
                       "加入中心试清除队列\n并附加保底清除点",
                       width=0.22, height=0.075,
                       face="#fff5d6", edge="#b07d16")
    refine = _diamond(ax, (0.82, 0.255), "细化次数\n是否小于 2",
                      width=0.13, height=0.055)
    measure = _box(ax, (0.82, 0.145),
                   "调用问题二选取保证接收测点\n执行检测并用问题一更新区域",
                   width=0.25, height=0.075)
    probe_queue = _box(ax, (0.82, 0.055),
                       "达到上限：加入中心\n及有限保底清除点队列",
                       width=0.22, height=0.070,
                       face="#fff5d6", edge="#b07d16")
    finish = _box(ax, (0.18, 0.080),
                  "全部源入队后：Held-Karp 排序\n"
                  "TSPN 偏移清除；失败则取下一保底清除点\n"
                  "全部频道定性后退出",
                  width=0.27, height=0.105,
                  face="#e0e7ff", edge="#4338ca",
                  fontsize=8.6, rounded=True)

    _arrow(ax, enter, scan)
    _arrow(ax, scan, result)
    _arrow(ax, result, no_signal, "无信号")
    _arrow(ax, result, bearing, "示向度")
    _arrow(ax, result, close, "近距离")
    _arrow(ax, no_signal, scan_done, rad=-0.05)
    _arrow(ax, bearing, scan_done)
    _arrow(ax, close, scan_done, rad=0.05)
    _arrow(ax, scan_done, scan, "否", rad=-0.60,
           label_pos=(0.335, 0.645))
    _arrow(ax, scan_done, summarize, "是")
    _arrow(ax, summarize, located)
    _arrow(ax, located, reliable, "是")
    _arrow(ax, located, trial_ready, "否")
    _arrow(ax, trial_ready, trial_queue, "是")
    _arrow(ax, trial_ready, refine, "否")
    _arrow(ax, refine, measure, "是")
    _arrow(ax, refine, probe_queue, "否", rad=-0.48,
           label_pos=(0.965, 0.155))
    _arrow(ax, measure, located, "测量后重新判断", rad=-0.48,
           label_pos=(0.705, 0.325))
    _arrow(ax, reliable, finish)
    _arrow(ax, trial_queue, finish)
    _arrow(ax, probe_queue, finish)

    save_figure(fig, "q3-decision-tree")


if __name__ == "__main__":
    plot_scan_layout()
    plot_decision_tree()
    print("Generated q3-eight-point-scan and q3-decision-tree figures.")
