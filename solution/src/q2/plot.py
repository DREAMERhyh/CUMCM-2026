"""Matplotlib visualization for the B-Q2 decision."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Polygon

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot_plan(plan, *, output=None, show=True):
    region = plan["region"]
    candidates = plan["candidates"]
    selected = plan["selected_point"]
    vertices = region["vertices"]
    candidate_regions = plan["candidate_regions"]

    continuous = plan.get("continuous_fim", {})
    fig, (ax, compare_ax, score_ax) = plt.subplots(
        1, 3, figsize=(18, 5.5), constrained_layout=True,
        gridspec_kw={"width_ratios": [1.45, 0.7, 1.0]},
    )
    possible = candidate_regions["possible_reception"]
    guaranteed = candidate_regions["guaranteed_reception"]
    if possible["status"] == "bounded":
        ax.add_patch(Polygon(possible["vertices"], closed=True,
                             facecolor="#f4a261", edgecolor="#bc6c25",
                             alpha=0.13, label="可能接收域（连续外近似）"))
    if guaranteed["status"] == "bounded":
        ax.add_patch(Polygon(guaranteed["vertices"], closed=True,
                             facecolor="#52b788", edgecolor="#2d6a4f",
                             alpha=0.25, label="保证接收域（连续内近似）"))
    ax.add_patch(Polygon(vertices, closed=True, facecolor="#8ecae6",
                         edgecolor="#126782", alpha=0.35,
                         label="第一观测后的源位置域"))
    xs = [item["point"][0] for item in candidates]
    ys = [item["point"][1] for item in candidates]
    values = [item["score"] for item in candidates]
    scatter = ax.scatter(xs, ys, c=values, cmap="viridis_r", s=28,
                         alpha=0.75, label="离散优化候选点")
    ax.scatter([selected[0]], [selected[1]], marker="*", s=220,
               color="#d62828", edgecolor="white", linewidth=0.8,
               label="离散搜索结果")
    if continuous.get("status") == "ok":
        fim_point = continuous["selected_point"]
        ax.scatter([fim_point[0]], [fim_point[1]], marker="D", s=105,
                   color="#277da1", edgecolor="white", linewidth=0.8,
                   label="连续FIM结果")
        ax.plot([selected[0], fim_point[0]], [selected[1], fim_point[1]],
                linestyle="--", linewidth=1.0, color="#6c757d", alpha=0.7)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    ax.set_title("Q2 离散基线与连续FIM选点")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=9)
    fig.colorbar(scatter, ax=ax, label="综合分数", pad=0.02,
                 fraction=0.045)

    labels = ["离散搜索"]
    values_to_compare = [plan["baseline"]["selected"]["score"]]
    colors = ["#d62828"]
    if continuous.get("status") == "ok":
        labels.append("连续FIM")
        values_to_compare.append(continuous["selected_score"])
        colors.append("#277da1")
    bars = compare_ax.bar(labels, values_to_compare, color=colors,
                          width=0.62)
    compare_ax.set_ylabel("同口径选点分数 / s")
    compare_ax.set_title("最终结果评分对比\n（越低越好）")
    compare_ax.grid(axis="y", alpha=0.2)
    compare_ax.tick_params(axis="x", labelrotation=15)
    for bar, value in zip(bars, values_to_compare):
        compare_ax.annotate(
            f"{value:.2f}",
            (bar.get_x() + bar.get_width() / 2.0, bar.get_height()),
            xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
            fontsize=9,
        )

    top = candidates[:min(15, len(candidates))]
    score_ax.barh(range(len(top)), [item["worst_case_radius_m"] for item in top],
                  color=["#2a9d8f" if item["guaranteed_reception"] else "#e9c46a"
                         for item in top])
    score_ax.invert_yaxis()
    score_ax.set_yticks(range(len(top)),
                        [item["candidate_id"] for item in top])
    score_ax.set_xlabel("有限场景最坏后验包围半径 / m")
    score_ax.set_ylabel("")
    score_ax.set_title("前15个离散候选的不确定性")
    score_ax.grid(axis="x", alpha=0.2)
    score_ax.legend(handles=[
        Patch(facecolor="#2a9d8f", label="保证接收候选"),
        Patch(facecolor="#e9c46a", label="非保证候选"),
    ], fontsize=8, loc="lower right")

    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=180)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig
