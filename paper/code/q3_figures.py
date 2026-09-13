"""Generate the scan-layout and decision-tree figures used in Q3."""

import os
from math import cos, pi, sin
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cumcm-q3-paper")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Rectangle


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
               label=r"目标圆域 $\overline{B}(O_0,1800)$"),
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
    style = "round,pad=0.32" if rounded else "square,pad=0.25"
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize,
            linespacing=1.25,
            bbox={"boxstyle": style, "facecolor": face,
                  "edgecolor": edge, "linewidth": 1.0}, zorder=5)


def _diamond(ax, center, text, *, width=0.12, height=0.055,
             face="#fff5d6", edge="#b07d16", fontsize=9.0):
    x, y = center
    vertices = [(x, y + height), (x + width, y),
                (x, y - height), (x - width, y)]
    ax.add_patch(Polygon(vertices, closed=True, facecolor=face,
                         edgecolor=edge, lw=1.0, zorder=4))
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize,
            linespacing=1.18, zorder=5)


def _arrow(ax, start, end, text=None, *, rad=0.0, color="0.28"):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=9, lw=0.9,
        color=color, connectionstyle=f"arc3,rad={rad}", zorder=2,
    ))
    if text:
        x = (start[0] + end[0]) / 2
        y = (start[1] + end[1]) / 2
        ax.text(x, y + 0.012, text, ha="center", va="center",
                fontsize=8.0, color=color,
                bbox={"facecolor": "white", "edgecolor": "none",
                      "pad": 0.5}, zorder=6)


def plot_decision_tree():
    fig, ax = plt.subplots(figsize=(11.2, 8.0))
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    _box(ax, (0.50, 0.955), "进入测试", width=0.12, rounded=True,
         face="#d8f3dc", edge="#2d6a4f")
    _box(ax, (0.50, 0.875), "依次访问八个等角扫描点\n并检测 1-20 频道")
    _diamond(ax, (0.50, 0.775), "检测结果")
    _box(ax, (0.16, 0.675), "无信号\n继续当前扫描", face="#f3f4f6",
         edge="#6b7280")
    _box(ax, (0.50, 0.675), "获得示向度\n更新该频道定位区域")
    _box(ax, (0.84, 0.675), "近距离\n立即在原地清除", face="#fee2e2",
         edge="#b91c1c")
    _diamond(ax, (0.50, 0.565), "八点扫描\n是否完成")
    _box(ax, (0.50, 0.465), "汇总已发现源与无源频道\n选择距当前位置最近的未处理源")
    _diamond(ax, (0.50, 0.365), r"$r_j\leq19.9\,\mathrm{m}$",
             height=0.045)
    _box(ax, (0.18, 0.255), "加入可靠清除队列\n记录最小包围圆中心",
         face="#d8f3dc", edge="#2d6a4f")
    _diamond(ax, (0.50, 0.245), r"$r_j\leq40\,\mathrm{m}$",
             height=0.045)
    _box(ax, (0.50, 0.145), "加入中心试清除队列\n并附加探针保底点",
         face="#fff5d6", edge="#b07d16")
    _diamond(ax, (0.82, 0.255), "细化次数\n是否小于 2")
    _box(ax, (0.82, 0.145), "调用问题二选取保证接收测点\n执行检测并用问题一更新区域")
    _box(ax, (0.82, 0.055), "达到上限：加入中心\n及有限探针清除队列",
         face="#fff5d6", edge="#b07d16")
    _box(ax, (0.18, 0.080), "全部源入队后：Held-Karp 排序\nTSPN 偏移清除；失败则取下一探针\n全部频道定性后退出",
         width=0.25, height=0.08, face="#e0e7ff", edge="#4338ca",
         fontsize=8.6, rounded=True)

    _arrow(ax, (0.50, 0.925), (0.50, 0.905))
    _arrow(ax, (0.50, 0.84), (0.50, 0.83))
    _arrow(ax, (0.40, 0.775), (0.23, 0.70), "无信号")
    _arrow(ax, (0.50, 0.72), (0.50, 0.705), "示向度")
    _arrow(ax, (0.60, 0.775), (0.77, 0.70), "近距离")
    _arrow(ax, (0.16, 0.64), (0.43, 0.585), rad=-0.05)
    _arrow(ax, (0.50, 0.64), (0.50, 0.62))
    _arrow(ax, (0.84, 0.64), (0.57, 0.585), rad=0.05)
    _arrow(ax, (0.41, 0.565), (0.34, 0.82), "否", rad=-0.42)
    _arrow(ax, (0.50, 0.51), (0.50, 0.495), "是")
    _arrow(ax, (0.50, 0.43), (0.50, 0.412))
    _arrow(ax, (0.40, 0.365), (0.23, 0.28), "是")
    _arrow(ax, (0.50, 0.318), (0.50, 0.292), "否")
    _arrow(ax, (0.40, 0.245), (0.33, 0.17), "是")
    _arrow(ax, (0.60, 0.245), (0.70, 0.255), "否")
    _arrow(ax, (0.82, 0.20), (0.82, 0.18), "是")
    _arrow(ax, (0.82, 0.11), (0.82, 0.09), "否")
    _arrow(ax, (0.73, 0.145), (0.62, 0.455),
           "测量后重新判断", rad=-0.34)
    _arrow(ax, (0.18, 0.22), (0.18, 0.13))
    _arrow(ax, (0.50, 0.11), (0.30, 0.085))
    _arrow(ax, (0.72, 0.055), (0.30, 0.075))

    save_figure(fig, "q3-decision-tree")


if __name__ == "__main__":
    plot_scan_layout()
    plot_decision_tree()
    print("Generated q3-eight-point-scan and q3-decision-tree figures.")
