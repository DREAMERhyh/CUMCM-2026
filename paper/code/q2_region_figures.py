"""Generate the Q2 region-construction figures used in the paper."""

import os
from math import cos, radians, sin
from pathlib import Path
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cumcm-q2-paper")

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon

PAPER_DIR = Path(__file__).resolve().parents[1]
SOLUTION_SRC = PAPER_DIR.parent / "solution" / "src"
sys.path.insert(0, str(SOLUTION_SRC))

from common.domain import build_region_from_observations  # noqa: E402
from common.models import BearingObservation  # noqa: E402
from q1.geometry import bearing_planes, contains  # noqa: E402
from q2.candidates import (  # noqa: E402
    _clip_many,
    _inner_circle_planes,
    _inner_circle_polygon,
    build_candidate_regions,
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


def _draw_k1_layers(axis, exact_vertices, outer_vertices, sensor,
                    bearing_deg, error_deg):
    axis.add_patch(Circle((0.0, 0.0), 1800.0, fill=False,
                          edgecolor="#52796f", lw=0.9, ls="--",
                          label=r"$\partial B(O_0,1800)$", zorder=1))
    axis.add_patch(Circle(sensor, 1500.0, fill=False,
                          edgecolor="#457b9d", lw=0.9, ls="-.",
                          label=r"$\partial B(S_1,1500)$", zorder=1))
    axis.add_patch(Polygon(outer_vertices, closed=True, fill=False,
                           edgecolor="#d97706", lw=1.7, ls=(0, (5, 3)),
                           label=r"$\widehat K_1$", zorder=4))
    axis.add_patch(Polygon(exact_vertices, closed=True,
                           facecolor="#90caf9", edgecolor="#0b4f6c",
                           lw=1.2, alpha=0.55, label=r"$K_1$", zorder=3))
    _draw_wedge(axis, sensor, bearing_deg, error_deg, 1900.0)
    axis.plot(*sensor, marker="o", ms=4, color="black", zorder=6)
    axis.text(sensor[0]+25.0, sensor[1]-55.0, r"$S_1$",
              ha="left", va="top", zorder=6, clip_on=True)
    axis.set_aspect("equal", adjustable="box")
    axis.grid(alpha=0.13)
    axis.set_xlabel(r"$x/\mathrm{m}$")
    axis.set_ylabel(r"$y/\mathrm{m}$")


def plot_source_outer_approximation():
    """Show curved K1 and the actual 24-sided conservative outer model."""
    sensor = (-600.0, -300.0)
    bearing_deg = 132.13
    # The half-angle is enlarged only so that both active circular arcs and
    # their polygonal outer approximation remain legible in the paper.
    display_error_deg = 8.0
    observation = BearingObservation(
        sensor, 1, "direction", bearing_deg
    )
    outer = build_region_from_observations(
        [observation], error_deg=display_error_deg,
        arena_radius=1800.0, max_receive_radius=1500.0,
        circle_sides=24,
    )

    # A 4096-gon has sub-millimetre radial deficit at this scale and is used
    # only to draw the continuous circular boundary of K1.
    exact = _inner_circle_polygon((0.0, 0.0), 1800.0, 4096)
    exact = _clip_many(
        exact, _inner_circle_planes(sensor, 1500.0, 4096)
    )
    exact = _clip_many(
        exact, bearing_planes(sensor, bearing_deg, display_error_deg)
    )
    if not all(contains(outer["planes"], point) for point in exact):
        raise AssertionError("K1 的高密度圆弧边界超出了外近似 Khat1。")

    fig, axes = plt.subplots(
        1, 2, figsize=(9.0, 4.1),
        gridspec_kw={"width_ratios": [1.18, 1.0]},
    )
    for axis in axes:
        _draw_k1_layers(
            axis, exact, outer["vertices"], sensor,
            bearing_deg, display_error_deg,
        )
    axes[0].set_xlim(-1830.0, -470.0)
    axes[0].set_ylim(-390.0, 1060.0)
    axes[0].set_title("(a)")
    axes[1].set_xlim(-1740.0, -1400.0)
    axes[1].set_ylim(560.0, 1010.0)
    axes[1].set_title("(b)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4,
               frameon=False, fontsize=9)
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.13,
                        top=0.82, wspace=0.28)
    save_figure(fig, "q2-k1-outer-approx")
    print(
        "outer-approximation check: "
        f"{len(exact)} dense K1 boundary points are inside Khat1"
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


def main():
    plt.rcParams.update({
        "font.family": "DejaVu Serif",
        "mathtext.fontset": "dejavuserif",
        "axes.linewidth": 0.8,
    })
    plot_source_outer_approximation()
    plot_reception_regions()


if __name__ == "__main__":
    main()
