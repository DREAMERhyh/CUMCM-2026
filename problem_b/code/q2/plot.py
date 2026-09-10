"""Matplotlib visualization for the B-Q2 decision."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot_plan(plan, *, output=None, show=True):
    region = plan["region"]
    candidates = plan["candidates"]
    selected = plan["selected_point"]
    vertices = region["vertices"]

    fig, (ax, score_ax) = plt.subplots(1, 2, figsize=(13, 5.5),
                                       constrained_layout=True)
    ax.add_patch(Polygon(vertices, closed=True, facecolor="#8ecae6",
                         edgecolor="#126782", alpha=0.35,
                         label="第一观测后的保守源区域"))
    xs = [item["point"][0] for item in candidates]
    ys = [item["point"][1] for item in candidates]
    values = [item["score"] for item in candidates]
    scatter = ax.scatter(xs, ys, c=values, cmap="viridis_r", s=28,
                         alpha=0.75, label="第二测点候选")
    ax.scatter([selected[0]], [selected[1]], marker="*", s=220,
               color="#d62828", edgecolor="white", linewidth=0.8,
               label="集合评分选择")
    fim = plan["fim_baseline_point"]
    ax.scatter([fim[0]], [fim[1]], marker="X", s=100, color="#ffb703",
               edgecolor="#333333", label="FIM基准")
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    ax.set_title("Q2 第二检测点候选与选择")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=9)
    fig.colorbar(scatter, ax=ax, label="综合分数", pad=0.02,
                 fraction=0.045)

    top = candidates[:min(15, len(candidates))]
    score_ax.barh(range(len(top)), [item["worst_case_radius_m"] for item in top],
                  color=["#2a9d8f" if item["guaranteed_reception"] else "#e9c46a"
                         for item in top])
    score_ax.invert_yaxis()
    score_ax.set_xlabel("最坏后验包围半径 / m")
    score_ax.set_ylabel("")
    score_ax.set_title("前15个候选的不确定性")
    score_ax.grid(axis="x", alpha=0.2)

    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=180)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig
