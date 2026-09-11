"""Matplotlib visualization for the B-Q2 decision."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Polygon

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _draw_near_regions(axis, branch, color, *, with_labels=False,
                       label_prefix=""):
    boundaries = []
    near_regions = branch.get("near_optimal_regions", {})
    for key, linestyle, alpha in (("10pct", "--", 0.10),
                                  ("5pct", "-", 0.22)):
        near = near_regions.get(key, {})
        boundaries.extend(near.get("boundary_points", []))
        for component_index, component in enumerate(
                near.get("components", [])):
            vertices = component.get("vertices", [])
            if len(vertices) < 3:
                continue
            axis.add_patch(Polygon(
                vertices, closed=True, facecolor=color, edgecolor=color,
                linestyle=linestyle, linewidth=1.5, alpha=alpha,
                label=(f"{label_prefix}{'5' if key == '5pct' else '10'}%近优域"
                       if with_labels and component_index == 0 else None),
            ))
    return boundaries


def _draw_region_inset(parent, branch, color, marker, title, bounds):
    inset = parent.inset_axes(bounds)
    points = _draw_near_regions(inset, branch, color)
    center = branch["selected_point"]
    inset.scatter([center[0]], [center[1]], marker=marker, s=42,
                  color=color, edgecolor="white", linewidth=0.5, zorder=3)
    points = points + [center]
    if points:
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        span = max(max(xs)-min(xs), max(ys)-min(ys), 20.0)
        margin = 0.18*span
        inset.set_xlim(min(xs)-margin, max(xs)+margin)
        inset.set_ylim(min(ys)-margin, max(ys)+margin)
    inset.set_aspect("equal", adjustable="box")
    inset.set_title(title, fontsize=7)
    inset.tick_params(labelsize=6)
    inset.grid(alpha=0.15)


def plot_plan(plan, *, output=None, show=True):
    region = plan["region"]
    candidates = plan["candidates"]
    recommended = plan["selected_point"]
    baseline = plan["baseline"]
    selected = baseline["selected_point"]
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
    region_styles = [
        (baseline, "#d62828", "离散"),
        (continuous, "#277da1", "连续FIM"),
    ]
    for branch, color, label_prefix in region_styles:
        if branch.get("status", "ok") != "ok":
            continue
        _draw_near_regions(ax, branch, color, with_labels=True,
                           label_prefix=label_prefix)
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
    ax.scatter([recommended[0]], [recommended[1]], marker="o", s=180,
               facecolors="none", edgecolors="#111111", linewidth=2.0,
               label=f"最终推荐（{plan['recommendation_source']}）")
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    ax.set_title("Q2 离散基线与连续FIM选点")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=9)
    fig.colorbar(scatter, ax=ax, label="综合分数", pad=0.02,
                 fraction=0.045)
    if baseline.get("near_optimal_regions"):
        _draw_region_inset(ax, baseline, "#d62828", "*", "离散近优域局部",
                           [0.53, 0.04, 0.20, 0.24])
    if (continuous.get("status") == "ok"
            and continuous.get("near_optimal_regions")):
        _draw_region_inset(ax, continuous, "#277da1", "D",
                           "连续FIM近优域局部", [0.76, 0.04, 0.20, 0.24])

    pareto = plan.get("pareto_front", [])
    if pareto:
        pareto = sorted(pareto, key=lambda item: item["action_time_s"])
        compare_ax.plot([item["action_time_s"] for item in pareto],
                        [item["worst_case_radius_m"] for item in pareto],
                        color="#6c757d", linewidth=1.2, alpha=0.8)
        compare_ax.scatter([item["action_time_s"] for item in pareto],
                           [item["worst_case_radius_m"] for item in pareto],
                           color="#6c757d", s=35, label="Pareto候选")
    base_selected = baseline["selected"]
    compare_ax.scatter([base_selected["action_time_s"]],
                       [base_selected["worst_case_radius_m"]], marker="*",
                       s=170, color="#d62828", label="离散结果")
    compare_ax.annotate(
        f"J={base_selected['score']:.2f}",
        (base_selected["action_time_s"],
         base_selected["worst_case_radius_m"]),
        xytext=(5, -14), textcoords="offset points", fontsize=8,
        color="#9d0208",
    )
    if continuous.get("status") == "ok":
        fim_selected = continuous["selected"]
        compare_ax.scatter([fim_selected["action_time_s"]],
                           [fim_selected["worst_case_radius_m"]], marker="D",
                           s=75, color="#277da1", label="连续FIM结果")
        compare_ax.annotate(
            f"J={fim_selected['score']:.2f}",
            (fim_selected["action_time_s"],
             fim_selected["worst_case_radius_m"]),
            xytext=(5, 6), textcoords="offset points", fontsize=8,
            color="#16425b",
        )
    compare_ax.set_xlabel("虚拟动作时间 / s")
    compare_ax.set_ylabel("最坏后验包围半径 / m")
    compare_ax.set_title("时间—定位效果 Pareto 前沿\n（越靠左下越好）")
    compare_ax.grid(alpha=0.2)
    compare_ax.legend(fontsize=8)

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
