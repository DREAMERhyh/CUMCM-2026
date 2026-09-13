"""Generate the Q2 region-construction figures used in the paper."""

import os
from math import cos, pi, radians, sin
from pathlib import Path
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cumcm-q2-paper")

import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Polygon

PAPER_DIR = Path(__file__).resolve().parents[1]
SOLUTION_SRC = PAPER_DIR.parent / "solution" / "src"
sys.path.insert(0, str(SOLUTION_SRC))

from common.domain import (  # noqa: E402
    build_region_from_observations,
    representative_points,
)
from common.models import BearingObservation  # noqa: E402
from q1.geometry import bearing_planes, contains  # noqa: E402
from q2.candidates import (  # noqa: E402
    _clip_many,
    _inner_circle_planes,
    _inner_circle_polygon,
    build_candidate_regions,
    generate_candidates,
)


def save_figure(fig, stem):
    """Save an editable vector figure and a high-resolution preview."""
    fig.savefig(PAPER_DIR / f"figures/{stem}.pdf", bbox_inches="tight")
    fig.savefig(PAPER_DIR / f"figures/{stem}.png",
                dpi=240, bbox_inches="tight")
    plt.close(fig)


def _draw_wedge(axis, sensor, bearing_deg, error_deg, length):
    for angle_deg in (bearing_deg-error_deg, bearing_deg+error_deg):
        angle = radians(angle_deg)
        endpoint = (sensor[0]+length*cos(angle),
                    sensor[1]+length*sin(angle))
        axis.plot([sensor[0], endpoint[0]], [sensor[1], endpoint[1]],
                  color="0.35", lw=0.9, ls=":", zorder=5)


def plot_source_outer_approximation():
    """Draw an angle-enlarged local view of the Q2 outer approximation."""
    radius = 1500.0
    sides = 24
    actual_half_angle = pi / sides
    radial_error = radius / cos(actual_half_angle) - radius
    assert abs(radial_error - radius * (1 / cos(pi / sides) - 1)) < 1e-9

    # The drawing angle is deliberately enlarged so the outer gap remains
    # legible at paper scale; the formula and numerical check still use N=24.
    display_half_angle = radians(20.0)
    contact_upper = (radius * cos(display_half_angle),
                     radius * sin(display_half_angle))
    contact_lower = (contact_upper[0], -contact_upper[1])
    display_vertex = (radius / cos(display_half_angle), 0.0)
    circle_midpoint = (radius, 0.0)
    arc_between = [
        (radius * cos(display_half_angle - 2 * display_half_angle * k / 120),
         radius * sin(display_half_angle - 2 * display_half_angle * k / 120))
        for k in range(121)
    ]
    outer_gap = [contact_lower, display_vertex, contact_upper, *arc_between]

    fig, axis = plt.subplots(figsize=(7.0, 4.2))
    axis.add_patch(Polygon(
        outer_gap, closed=True, facecolor="#edcf9e", edgecolor="none",
        alpha=0.72, zorder=1,
    ))
    surrounding_angles = [
        -radians(32.0) + 2 * radians(32.0) * k / 240
        for k in range(241)
    ]
    axis.plot(
        [radius * cos(angle) for angle in surrounding_angles],
        [radius * sin(angle) for angle in surrounding_angles],
        color="#245b78", lw=2.0, zorder=3,
    )
    axis.plot(
        [contact_lower[0], display_vertex[0], contact_upper[0]],
        [contact_lower[1], display_vertex[1], contact_upper[1]],
        color="#c97921", lw=2.0, zorder=4,
    )
    axis.scatter([0.0], [0.0], color="black", s=18, zorder=5)
    axis.annotate(r"$A$", (0.0, 0.0), xytext=(7, 5),
                  textcoords="offset points", fontsize=10)
    for contact, label, vertical_offset in (
        (contact_upper, r"$T_+$", 7),
        (contact_lower, r"$T_-$", -16),
    ):
        axis.plot([0.0, contact[0]], [0.0, contact[1]],
                  color="0.45", lw=0.8, ls=":", zorder=2)
        axis.scatter([contact[0]], [contact[1]], color="#245b78",
                     s=19, zorder=6)
        axis.annotate(label, contact, xytext=(-17, vertical_offset),
                      textcoords="offset points", fontsize=9)
    axis.scatter([display_vertex[0]], [display_vertex[1]], marker="o",
                 facecolors="white", edgecolors="#ac4444", s=28, zorder=7)
    axis.annotate(r"$V$", display_vertex, xytext=(7, 5),
                  textcoords="offset points", fontsize=10)
    axis.plot([circle_midpoint[0], display_vertex[0]],
              [circle_midpoint[1], display_vertex[1]],
              color="#ac4444", lw=2.0, zorder=6)
    axis.annotate(
        r"$\Delta_{\mathrm{out}}=R\!\left(\sec\frac{\pi}{N}-1\right)$",
        ((circle_midpoint[0] + display_vertex[0]) / 2.0, 0.0),
        xytext=(radius * 0.43, -radius * 0.31), textcoords="data",
        fontsize=9, arrowprops={"arrowstyle": "-", "lw": 0.7},
    )
    angle_radius = radius * 0.23
    axis.add_patch(Arc(
        (0.0, 0.0), 2 * angle_radius, 2 * angle_radius,
        theta1=-20.0, theta2=20.0, color="0.25", lw=1.0, zorder=5,
    ))
    axis.annotate(r"$2\pi/N$", (angle_radius * 0.98, 0.0),
                  xytext=(3, 5), textcoords="offset points", fontsize=9)
    axis.annotate(
        r"$\partial\overline{B}(A,R)$",
        (radius * cos(radians(28.0)), radius * sin(radians(28.0))),
        xytext=(-84, 13), textcoords="offset points", fontsize=9,
        color="#245b78",
    )
    upper_midpoint = ((contact_upper[0] + display_vertex[0]) / 2.0,
                      contact_upper[1] / 2.0)
    axis.annotate(
        r"$\partial\widehat{B}_{\mathrm{out}}^{(N)}(A,R)$",
        upper_midpoint, xytext=(15, 18), textcoords="offset points",
        fontsize=9, color="#9a5a13",
    )

    axis.set_xlim(-radius * 0.04, radius * 1.18)
    axis.set_ylim(-radius * 0.48, radius * 0.48)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xticks([])
    axis.set_yticks([])
    axis.spines[["top", "right", "bottom", "left"]].set_visible(False)
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.03, top=0.97)
    save_figure(fig, "q2-k1-outer-approx")
    print(
        "Fixed outer polygon checked: "
        f"N={sides}, maximum radial excess={radial_error:.6f} m."
    )


def plot_reception_regions():
    """Draw the Q2 guaranteed and possible reception approximations."""
    observation = BearingObservation(
        (-600.0, -300.0), 1, "direction", 35.89
    )
    source_region = build_region_from_observations(
        [observation], error_deg=1.005,
        arena_radius=1800.0, max_receive_radius=1500.0,
        circle_sides=24,
    )
    regions = build_candidate_regions(
        source_region, min_receive_radius=1000.0,
        max_receive_radius=1500.0, circle_sides=72,
    )
    guaranteed = regions["guaranteed_reception"]
    possible = regions["possible_reception"]

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    ax.add_patch(Polygon(
        possible["vertices"], closed=True,
        facecolor="#f4a261", edgecolor="#bc6c25", lw=1.2, alpha=0.22,
        label=r"$\widehat{\mathcal{F}}_p$",
    ))
    ax.add_patch(Polygon(
        guaranteed["vertices"], closed=True,
        facecolor="#74c69d", edgecolor="#2d6a4f", lw=1.3, alpha=0.48,
        label=r"$\widehat{\mathcal{F}}_g$",
    ))
    ax.add_patch(Polygon(
        source_region["vertices"], closed=True,
        facecolor="#90caf9", edgecolor="#0b4f6c", lw=1.3, alpha=0.75,
        label=r"$\widehat K_1$",
    ))
    ax.plot(*observation.position, marker="o", ms=4.2,
            color="black", zorder=5)
    ax.text(observation.position[0]-55.0, observation.position[1]-85.0,
            r"$S_1$", ha="right", va="top")
    all_vertices = possible["vertices"]
    xs = [point[0] for point in all_vertices]
    ys = [point[1] for point in all_vertices]
    margin = 180.0
    ax.set_xlim(min(xs)-margin, max(xs)+margin)
    ax.set_ylim(min(ys)-margin, max(ys)+margin)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(r"$x/\mathrm{m}$")
    ax.set_ylabel(r"$y/\mathrm{m}$")
    ax.grid(alpha=0.16)
    ax.legend(loc="upper left", frameon=True, fontsize=10)
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.12, top=0.97)
    save_figure(fig, "q2-reception-regions")


def plot_source_scenarios():
    """Illustrate the three raw point types and the eight-point cap."""
    vertices = [
        (-2.6, -0.9), (0.7, -1.35), (2.45, 0.25),
        (1.05, 2.25), (-1.85, 1.75),
    ]
    midpoints = [
        ((first[0]+second[0])/2, (first[1]+second[1])/2)
        for first, second in zip(vertices, vertices[1:]+vertices[:1])
    ]
    center = (
        sum(point[0] for point in vertices)/len(vertices),
        sum(point[1] for point in vertices)/len(vertices),
    )
    selected = representative_points(vertices, limit=8)

    fig, ax = plt.subplots(figsize=(6.6, 4.8))
    ax.add_patch(Polygon(
        vertices, closed=True, facecolor="#dbeafe", edgecolor="#315f7d",
        lw=1.4, alpha=0.78, zorder=1,
    ))
    ax.scatter(
        [point[0] for point in vertices],
        [point[1] for point in vertices],
        marker="s", s=42, color="#1d4ed8", label=r"vertices $V_i$",
        zorder=3,
    )
    ax.scatter(
        [point[0] for point in midpoints],
        [point[1] for point in midpoints],
        marker="^", s=48, color="#d97706", label=r"midpoints $M_i$",
        zorder=3,
    )
    ax.scatter(
        [center[0]], [center[1]], marker="*", s=115, color="#7e22ce",
        label=r"vertex-mean center $G$", zorder=4,
    )
    ax.scatter(
        [point[0] for point in selected],
        [point[1] for point in selected],
        marker="o", s=135, facecolors="none", edgecolors="#dc2626",
        linewidths=1.45, label=r"retained in $\mathcal{S}_A$", zorder=5,
    )
    for index, point in enumerate(vertices, start=1):
        ax.annotate(
            rf"$V_{index}$", point, xytext=(5, 6),
            textcoords="offset points", fontsize=9,
        )
    for index, point in enumerate(midpoints, start=1):
        ax.annotate(
            rf"$M_{index}$", point, xytext=(5, -13),
            textcoords="offset points", fontsize=9,
        )
    ax.annotate(r"$G$", center, xytext=(7, 5),
                textcoords="offset points", fontsize=9)
    ax.text(-0.85, 0.75, r"$\widehat K_1$", fontsize=13,
            ha="center", va="center", color="#315f7d")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-3.15, 3.0)
    ax.set_ylim(-1.8, 2.75)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=2,
              frameon=False, fontsize=9)
    fig.subplots_adjust(left=0.05, right=0.98, bottom=0.04, top=0.82)
    save_figure(fig, "q2-source-scenarios")


def _inside_convex_polygon(polygon, point, tolerance=1e-7):
    signs = []
    for first, second in zip(polygon, polygon[1:]+polygon[:1]):
        cross = ((second[0]-first[0])*(point[1]-first[1])
                 -(second[1]-first[1])*(point[0]-first[0]))
        if abs(cross) > tolerance:
            signs.append(cross > 0.0)
    return not signs or all(sign == signs[0] for sign in signs)


def plot_discrete_candidates():
    """Show the actual 46-point construction used by scheme one."""
    observation = BearingObservation(
        (-600.0, -300.0), 1, "direction", 35.89
    )
    source_region = build_region_from_observations(
        [observation], error_deg=1.005,
        arena_radius=1800.0, max_receive_radius=1500.0,
        circle_sides=24,
    )
    regions = build_candidate_regions(
        source_region, min_receive_radius=1000.0,
        max_receive_radius=1500.0, circle_sides=72,
    )
    guaranteed = regions["guaranteed_reception"]
    possible = regions["possible_reception"]
    center = tuple(source_region["minimum_enclosing_circle"]["center"])

    theta = radians(observation.bearing_deg)
    direction = (cos(theta), sin(theta))
    left_normal = (-direction[1], direction[0])
    directional = []
    for step in (100.0, 250.0, 500.0, 750.0):
        for lateral in (0.0, -0.5*step, 0.5*step, -step, step):
            directional.append((
                observation.position[0]+step*direction[0]
                + lateral*left_normal[0],
                observation.position[1]+step*direction[1]
                + lateral*left_normal[1],
            ))
    ring = [
        (center[0]+radius*cos(2*pi*k/8),
         center[1]+radius*sin(2*pi*k/8))
        for radius in (250.0, 500.0, 750.0)
        for k in range(8)
    ]
    guaranteed_center = (
        sum(point[0] for point in guaranteed["vertices"])
        / len(guaranteed["vertices"]),
        sum(point[1] for point in guaranteed["vertices"])
        / len(guaranteed["vertices"]),
    )
    special = [
        ((observation.position[0]+center[0])/2,
         (observation.position[1]+center[1])/2),
        guaranteed_center,
    ]
    generated = generate_candidates(
        source_region, observation.position, observation.bearing_deg,
        guaranteed_region=guaranteed,
    )
    expected = directional + special[:1] + ring + special[1:]
    generated_keys = {(round(x, 8), round(y, 8)) for x, y in generated}
    expected_keys = {(round(x, 8), round(y, 8)) for x, y in expected}
    if generated_keys != expected_keys:
        raise AssertionError("候选点示意与 generate_candidates 不一致。")
    preferred = [
        point for point in generated
        if _inside_convex_polygon(guaranteed["vertices"], point)
    ]

    fig, axes = plt.subplots(
        1, 2, figsize=(10.2, 4.8),
        gridspec_kw={"width_ratios": [1.0, 1.18]},
    )
    overview, detail = axes
    overview.add_patch(Polygon(
        possible["vertices"], closed=True,
        facecolor="#f4a261", edgecolor="#bc6c25", lw=1.1, alpha=0.22,
        label=r"$\widehat{\mathcal{F}}_p$",
    ))
    overview.add_patch(Polygon(
        guaranteed["vertices"], closed=True,
        facecolor="#74c69d", edgecolor="#2d6a4f", lw=1.2, alpha=0.5,
        label=r"$\widehat{\mathcal{F}}_g$",
    ))
    overview.add_patch(Polygon(
        source_region["vertices"], closed=True,
        facecolor="#90caf9", edgecolor="#0b4f6c", lw=1.2, alpha=0.72,
        label=r"$\widehat K_1$",
    ))
    overview.scatter(
        [point[0] for point in generated],
        [point[1] for point in generated],
        marker="o", s=12, color="#374151", zorder=4,
        label=r"$\mathcal{C}_A$",
    )
    overview.plot(*observation.position, marker="*", ms=8,
                  color="black", zorder=5)
    overview.annotate(r"$S_1$", observation.position,
                      xytext=(-14, -15), textcoords="offset points")
    overview.set_xlim(-2250.0, 2280.0)
    overview.set_ylim(-1950.0, 2250.0)
    overview.set_title("(a)")
    overview.legend(loc="upper left", frameon=True, fontsize=8)

    detail.add_patch(Polygon(
        guaranteed["vertices"], closed=True,
        facecolor="#74c69d", edgecolor="#2d6a4f", lw=1.2, alpha=0.42,
        zorder=1,
    ))
    detail.add_patch(Polygon(
        source_region["vertices"], closed=True,
        facecolor="#90caf9", edgecolor="#0b4f6c", lw=1.2, alpha=0.48,
        zorder=2,
    ))
    detail.scatter(
        [point[0] for point in directional],
        [point[1] for point in directional],
        marker="o", s=27, color="#2563eb",
        label="forward-lateral", zorder=4,
    )
    detail.scatter(
        [point[0] for point in ring],
        [point[1] for point in ring],
        marker="^", s=34, color="#d97706",
        label="center rings", zorder=4,
    )
    detail.scatter(
        [point[0] for point in special],
        [point[1] for point in special],
        marker="D", s=42, color="#7e22ce",
        label="special points", zorder=5,
    )
    detail.scatter(
        [point[0] for point in preferred],
        [point[1] for point in preferred],
        marker="o", s=95, facecolors="none", edgecolors="#dc2626",
        linewidths=1.2, label=r"$\mathcal{C}_A\cap\widehat{\mathcal{F}}_g$",
        zorder=6,
    )
    detail.plot(*observation.position, marker="*", ms=8,
                color="black", zorder=7)
    detail.annotate(r"$S_1$", observation.position,
                    xytext=(-15, -15), textcoords="offset points")
    detail.plot(*center, marker="x", ms=6, mew=1.2,
                color="#111827", zorder=7)
    detail.annotate(r"$Q_0$", center, xytext=(6, 5),
                    textcoords="offset points")
    endpoint = (
        observation.position[0]+440.0*direction[0],
        observation.position[1]+440.0*direction[1],
    )
    detail.annotate(
        "", xy=endpoint, xytext=observation.position,
        arrowprops={"arrowstyle": "->", "color": "0.25",
                    "lw": 1.0, "ls": ":"},
    )
    detail.annotate(r"$u_1$", endpoint, xytext=(4, 2),
                    textcoords="offset points")
    detail.set_xlim(-850.0, 850.0)
    detail.set_ylim(-690.0, 1010.0)
    detail.set_title("(b)")
    detail.legend(loc="upper left", frameon=True, fontsize=8, ncol=2)

    for axis in axes:
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel(r"$x/\mathrm{m}$")
        axis.set_ylabel(r"$y/\mathrm{m}$")
        axis.grid(alpha=0.14)
    fig.subplots_adjust(left=0.065, right=0.985, bottom=0.12,
                        top=0.94, wspace=0.25)
    save_figure(fig, "q2-discrete-candidates")
    print(
        "candidate-point check: "
        f"{len(generated)} generated, {len(preferred)} in Fg-hat"
    )


def main():
    plt.rcParams.update({
        "font.family": "DejaVu Serif",
        "mathtext.fontset": "dejavuserif",
        "axes.linewidth": 0.8,
    })
    plot_source_outer_approximation()
    plot_reception_regions()
    plot_source_scenarios()
    plot_discrete_candidates()


if __name__ == "__main__":
    main()
