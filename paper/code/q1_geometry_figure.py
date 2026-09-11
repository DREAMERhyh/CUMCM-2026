"""Generate the abstract geometry figure used in the Q1 proof."""

import os
from math import atan2, cos, degrees, radians, sin
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cumcm-q1")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon

PAPER_DIR = Path(__file__).resolve().parents[1]


def ray(endpoint, angle_deg, length=7.0):
    angle = radians(angle_deg)
    return (endpoint[0] + length * cos(angle),
            endpoint[1] + length * sin(angle))


def save_figure(fig, stem):
    fig.savefig(PAPER_DIR / f"figures/{stem}.pdf", bbox_inches="tight")
    fig.savefig(PAPER_DIR / f"figures/{stem}.png",
                dpi=240, bbox_inches="tight")
    plt.close(fig)


def plot_region_intersection():
    """Draw angular-error regions and their bounded convex intersection."""
    fig, ax = plt.subplots(figsize=(4.8, 3.4))
    detectors = [(-3.0, -2.0), (3.0, -2.0)]
    bearings = [degrees(atan2(2.0, 3.0)), degrees(atan2(2.0, -3.0))]
    delta = 8.0  # Enlarged only to make the abstract construction visible.
    polygon = [(-0.8958, -0.1259), (0.0, -0.5568),
               (0.8958, -0.1259), (0.0, 0.6720)]
    for index, (point, bearing) in enumerate(zip(detectors, bearings), 1):
        ax.plot(*point, "ko", ms=3.5)
        ax.text(point[0], point[1] - 0.20, rf"$S_{index}$", ha="center", va="top")
        for boundary in (bearing - delta, bearing + delta):
            end = ray(point, boundary)
            ax.plot([point[0], end[0]], [point[1], end[1]],
                    color="0.35", lw=0.9)
        center_end = ray(point, bearing)
        ax.plot([point[0], center_end[0]], [point[1], center_end[1]],
                color="0.55", lw=0.8, ls="--")
    ax.add_patch(Polygon(polygon, closed=True, facecolor="0.82",
                         edgecolor="black", lw=1.2))
    ax.text(0.0, -0.02, r"$\Omega$", ha="center", va="center")
    ax.set_xlim(-3.55, 3.55)
    ax.set_ylim(-2.35, 2.0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(0.5, -0.04, r"$\Omega = \bigcap_{i=1}^{n}\; C_i$",
            transform=ax.transAxes, ha="center", va="top")
    fig.subplots_adjust(left=0.03, right=0.97, top=0.98, bottom=0.14)
    save_figure(fig, "q1-region-intersection")


def plot_diameter_circle():
    """Draw a diameter circle that does not cover the third vertex."""
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    p, q, v = (-1.0, 0.0), (1.0, 0.0), (0.0, 1.30)
    ax.add_patch(Circle((0.0, 0.0), 1.0, fill=False,
                        edgecolor="0.35", lw=1.0, ls="--"))
    ax.add_patch(Polygon([p, q, v], closed=True, facecolor="0.88",
                         edgecolor="black", lw=1.2))
    ax.plot([p[0], q[0]], [p[1], q[1]], color="black", lw=1.5)
    ax.plot(0.0, 0.0, marker="+", color="black", ms=7)
    for point, label, offset, alignment in [
        (p, r"$V_p$", (-0.12, -0.18), "right"),
        (q, r"$V_q$", (0.12, -0.18), "left"),
        (v, r"$V_k$", (0.0, 0.10), "center"),
    ]:
        ax.plot(*point, "ko", ms=3.5)
        ax.text(point[0] + offset[0], point[1] + offset[1], label,
                ha=alignment, va="center")
    ax.text(0.08, -0.10, r"$O$", ha="left", va="top")
    ax.text(0.46, 0.06, r"$r=D/2$", ha="center", va="bottom")
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.2, 1.65)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(0.5, -0.04, r"$\|V_k-O\|>D/2$",
            transform=ax.transAxes, ha="center", va="top")
    fig.subplots_adjust(left=0.06, right=0.94, top=0.98, bottom=0.14)
    save_figure(fig, "q1-diameter-circle")


def main():
    plt.rcParams.update({
        "font.family": "DejaVu Serif",
        "mathtext.fontset": "dejavuserif",
        "axes.linewidth": 0.8,
    })
    plot_region_intersection()
    plot_diameter_circle()


if __name__ == "__main__":
    main()
