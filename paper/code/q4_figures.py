"""Generate the triangular scan and decision-tree figures used in Q4."""

import os
from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cumcm-q4-paper")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Wedge


PAPER_DIR = Path(__file__).resolve().parents[1]
SOLUTION_SRC = PAPER_DIR.parent / "solution" / "src"
sys.path.insert(0, str(SOLUTION_SRC))

from q4.directional import triangular_scan_mesh  # noqa: E402


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


def _triangle_centroid(triangle):
    return tuple(sum(point[index] for point in triangle) / 3.0
                 for index in range(2))


def plot_triangular_scan():
    points, triangles = triangular_scan_mesh(
        spacing=985.0, lattice_phase=(0.112, 0.112),
    )
    route = [(0.0, 0.0), *points]
    route_length = sum(
        hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(route, route[1:])
    )

    display_target = (650.0, 300.0)
    highlighted = min(
        triangles,
        key=lambda triangle: hypot(
            _triangle_centroid(triangle)[0] - display_target[0],
            _triangle_centroid(triangle)[1] - display_target[1],
        ),
    )
    source = _triangle_centroid(highlighted)
    direction_deg = 28.0
    direction = (cos(radians(direction_deg)), sin(radians(direction_deg)))
    visible = [
        point for point in highlighted
        if (direction[0] * (point[0] - source[0])
            + direction[1] * (point[1] - source[1]) >= -1e-9)
    ]
    assert visible

    fig, ax = plt.subplots(figsize=(7.5, 7.0))
    ax.add_patch(Circle(
        (0.0, 0.0), 1800.0, facecolor="#eaf3f8",
        edgecolor="#245b78", lw=1.8, zorder=0,
    ))
    for triangle in triangles:
        ax.add_patch(Polygon(
            triangle, closed=True, facecolor="none", edgecolor="#8ba9bb",
            lw=0.55, alpha=0.45, zorder=1,
        ))

    ax.add_patch(Wedge(
        source, 1000.0, direction_deg - 90.0, direction_deg + 90.0,
        facecolor="#74c69d", edgecolor="#2d6a4f", lw=1.0,
        alpha=0.20, zorder=2,
    ))
    ax.add_patch(Polygon(
        highlighted, closed=True, facecolor="#f4a261",
        edgecolor="#bc6c25", lw=1.8, alpha=0.42, zorder=3,
    ))

    xs, ys = zip(*route)
    ax.plot(xs, ys, color="#c44536", lw=1.0, alpha=0.82, zorder=4)
    for index in range(0, len(route) - 1, 2):
        first, second = route[index], route[index + 1]
        ratio = 0.52
        midpoint = (first[0] + ratio * (second[0] - first[0]),
                    first[1] + ratio * (second[1] - first[1]))
        angle = degrees(atan2(second[1] - first[1],
                              second[0] - first[0]))
        ax.scatter([midpoint[0]], [midpoint[1]], marker=(3, 0, angle - 90),
                   s=22, color="#c44536", zorder=5)

    px, py = zip(*points)
    ax.scatter(px, py, s=28, color="#c44536", edgecolors="white",
               linewidths=0.55, zorder=6)
    vx, vy = zip(*visible)
    ax.scatter(vx, vy, s=70, color="#2d6a4f", marker="o",
               edgecolors="white", linewidths=0.8, zorder=7)
    ax.scatter([source[0]], [source[1]], marker="*", s=105,
               color="#6a3d9a", edgecolors="white", linewidths=0.5,
               zorder=8)
    ax.annotate(r"$X^*$", source, xytext=(-18, 8),
                textcoords="offset points", fontsize=10, color="#6a3d9a")
    arrow_end = (source[0] + 520.0 * direction[0],
                 source[1] + 520.0 * direction[1])
    ax.add_patch(FancyArrowPatch(
        source, arrow_end, arrowstyle="-|>", mutation_scale=11,
        color="#2d6a4f", lw=1.5, zorder=8,
    ))
    ax.annotate(r"$u(\psi)$", arrow_end, xytext=(10, 10),
                textcoords="offset points", fontsize=9, color="#2d6a4f")
    ax.scatter([0.0], [0.0], color="black", s=26, zorder=8)
    ax.annotate(r"$O_0$", (0.0, 0.0), xytext=(-28, -18),
                textcoords="offset points", fontsize=10)

    handles = [
        Line2D([0], [0], color="#245b78", lw=1.8,
               label=r"目标圆形区域 $\overline{B}(O_0,1800)$"),
        Line2D([0], [0], marker="o", color="none",
               markerfacecolor="#c44536", markeredgecolor="white",
               markersize=6.5, label="25 个三角网驻留点"),
        Line2D([0], [0], color="#c44536", lw=1.2,
               label="机器狗访问顺序"),
        Line2D([0], [0], color="#2d6a4f", lw=5, alpha=0.30,
               label=r"示例源的 $180^\circ$ 发射正面"),
        Line2D([0], [0], color="#bc6c25", lw=2.0,
               label="包含示例源的网格三角形"),
        Line2D([0], [0], marker="o", color="none",
               markerfacecolor="#2d6a4f", markeredgecolor="white",
               markersize=7.5, label="满足方向与距离条件的驻留点"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=8.0,
              framealpha=0.96)
    ax.set_xlim(-2850.0, 2850.0)
    ax.set_ylim(-2850.0, 2850.0)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(r"$x/\mathrm{m}$")
    ax.set_ylabel(r"$y/\mathrm{m}$")
    ax.grid(alpha=0.10)
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.09, top=0.98)
    save_figure(fig, "q4-triangular-scan")
    print(
        f"Q4 triangular scan: {len(points)} points, "
        f"{len(triangles)} triangles, route={route_length:.6f} m."
    )


def _box(ax, center, text, *, face="#eef4f8", edge="#245b78",
         fontsize=8.4, rounded=False):
    style = "round,pad=0.30" if rounded else "square,pad=0.23"
    ax.text(
        center[0], center[1], text, ha="center", va="center",
        fontsize=fontsize, linespacing=1.20,
        bbox={"boxstyle": style, "facecolor": face,
              "edgecolor": edge, "linewidth": 1.0}, zorder=5,
    )


def _diamond(ax, center, text, *, width=0.105, height=0.040,
             face="#fff5d6", edge="#b07d16", fontsize=8.3):
    x, y = center
    vertices = [(x, y + height), (x + width, y),
                (x, y - height), (x - width, y)]
    ax.add_patch(Polygon(vertices, closed=True, facecolor=face,
                         edgecolor=edge, lw=1.0, zorder=4))
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize,
            linespacing=1.16, zorder=5)


def _arrow(ax, start, end, text=None, *, rad=0.0, color="0.28"):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=9, lw=0.9,
        color=color, connectionstyle=f"arc3,rad={rad}", zorder=2,
    ))
    if text:
        x = (start[0] + end[0]) / 2.0
        y = (start[1] + end[1]) / 2.0
        ax.text(x, y + 0.010, text, ha="center", va="center",
                fontsize=7.7, color=color,
                bbox={"facecolor": "white", "edgecolor": "none",
                      "pad": 0.4}, zorder=6)


def plot_decision_tree():
    fig, ax = plt.subplots(figsize=(11.4, 8.3))
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    reused = {"face": "#f3f4f6", "edge": "#6b7280"}
    new = {"face": "#e6f2f8", "edge": "#245b78"}
    clear = {"face": "#d8f3dc", "edge": "#2d6a4f"}
    warn = {"face": "#fff5d6", "edge": "#b07d16"}

    _box(ax, (0.50, 0.965), "进入测试", rounded=True, **clear)
    _box(ax, (0.50, 0.895), "访问 25 个三角网驻留点\n逐点检测 1--20 频道", **new)
    _diamond(ax, (0.50, 0.810), "检测结果")
    _box(ax, (0.18, 0.725), "无信号\n更新有限可能状态", **new)
    _box(ax, (0.50, 0.725), "获得示向度\n更新定位区域与联合状态", **new)
    _box(ax, (0.82, 0.725), "近距离\n立即原地清除", **clear)
    _diamond(ax, (0.50, 0.635), "全域扫描\n是否完成")
    _box(ax, (0.50, 0.555), "汇总已发现源和无源频道\n选择距当前位置最近的未处理源",
         **reused)
    _diamond(ax, (0.50, 0.475), r"$r_j\leq19.9\,\mathrm{m}$")
    _box(ax, (0.20, 0.400), "沿用 Q3 可靠清除点\n清除后转向下一源", **reused)
    _diamond(ax, (0.50, 0.395),
             "$r_j\\leq40\\,\\mathrm{m}$\n且尚未试清除")
    _box(ax, (0.20, 0.310), "在区域中心尝试清除\n成功则转向下一源", **reused)
    _box(ax, (0.50, 0.300), "构造四侧或局部三角探测组\n更新有限可能状态与预计时间",
         **new)
    _diamond(ax, (0.50, 0.205), "继续检测比\n立即清除更省时")
    _box(ax, (0.22, 0.115), "执行完整清除覆盖\n失败点排除 20 m 邻域", **warn)
    _box(ax, (0.78, 0.130), "执行一个探测点\n收到结果后重新计算", **new)
    _diamond(ax, (0.78, 0.050), "探测结果", width=0.085,
             height=0.030, fontsize=8.0)
    _box(ax, (0.50, 0.025), "全部频道已清除或判定无源：退出",
         rounded=True, **clear)

    _arrow(ax, (0.50, 0.940), (0.50, 0.925))
    _arrow(ax, (0.50, 0.862), (0.50, 0.850))
    _arrow(ax, (0.405, 0.810), (0.245, 0.748), "无信号")
    _arrow(ax, (0.50, 0.770), (0.50, 0.755), "示向度")
    _arrow(ax, (0.595, 0.810), (0.755, 0.748), "近距离")
    _arrow(ax, (0.18, 0.695), (0.42, 0.648), rad=-0.06)
    _arrow(ax, (0.50, 0.695), (0.50, 0.678))
    _arrow(ax, (0.82, 0.695), (0.58, 0.648), rad=0.06)
    _arrow(ax, (0.405, 0.635), (0.37, 0.870), rad=-0.35)
    ax.text(0.315, 0.630, "未完成", ha="center", va="center",
            fontsize=7.7, color="0.28",
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.4})
    _arrow(ax, (0.50, 0.595), (0.50, 0.580), "是")
    _arrow(ax, (0.50, 0.525), (0.50, 0.515))
    _arrow(ax, (0.405, 0.475), (0.25, 0.420), "是")
    _arrow(ax, (0.50, 0.435), (0.50, 0.430), "否")
    _arrow(ax, (0.405, 0.395), (0.255, 0.330), "是")
    _arrow(ax, (0.50, 0.355), (0.50, 0.335), "否")
    _arrow(ax, (0.50, 0.265), (0.50, 0.245))
    _arrow(ax, (0.405, 0.205), (0.28, 0.138), "否")
    _arrow(ax, (0.595, 0.205), (0.72, 0.155), "是")
    _arrow(ax, (0.78, 0.102), (0.78, 0.082))
    _arrow(ax, (0.70, 0.050), (0.57, 0.190), "示向度/无信号",
           rad=-0.23)
    _arrow(ax, (0.84, 0.050), (0.90, 0.115), "近距离", rad=-0.12)
    _arrow(ax, (0.90, 0.115), (0.58, 0.030), "清除成功", rad=0.12)
    _arrow(ax, (0.22, 0.087), (0.42, 0.032), "成功或继续反馈")
    _arrow(ax, (0.20, 0.285), (0.40, 0.205), "失败后继续判断",
           rad=-0.08)

    ax.text(0.03, 0.97, "灰色：Q3 已完成并直接沿用",
            fontsize=8.0, color="#4b5563", ha="left", va="top")
    ax.text(0.03, 0.935, "蓝色：问题四新增步骤",
            fontsize=8.0, color="#245b78", ha="left", va="top")
    save_figure(fig, "q4-decision-tree")


if __name__ == "__main__":
    plot_triangular_scan()
    plot_decision_tree()
    print("Generated q4-triangular-scan and q4-decision-tree figures.")
