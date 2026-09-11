"""Generate the abstract geometry figure used in the Q1 proof."""

import os
from math import atan2, cos, degrees, pi, radians, sin
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cumcm-q1")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Circle, Polygon

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
    ax.add_patch(Polygon([p, q, v], closed=True, facecolor="0.88",
                         edgecolor="black", lw=1.2, zorder=1))
    ax.plot([p[0], q[0]], [p[1], q[1]], color="black", lw=1.5,
            zorder=2)
    ax.add_patch(Circle((0.0, 0.0), 1.0, fill=False,
                        edgecolor="0.35", lw=1.0, ls="--", zorder=3))
    ax.plot(0.0, 0.0, marker="+", color="black", ms=7, zorder=4)
    for point, label, offset, alignment in [
        (p, r"$V_p$", (-0.12, -0.18), "right"),
        (q, r"$V_q$", (0.12, -0.18), "left"),
        (v, r"$V_k$", (0.0, 0.10), "center"),
    ]:
        ax.plot(*point, "ko", ms=3.5, zorder=4)
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


def arc_points(center, radius, start, stop, count=121):
    """Return points on a circular arc, with angles measured in radians."""
    return [
        (center[0] + radius * cos(start + (stop-start)*k/(count-1)),
         center[1] + radius * sin(start + (stop-start)*k/(count-1)))
        for k in range(count)
    ]


def sector_polygon(center, direction, half_angle, radius, count=161):
    """Return a counter-clockwise polygon for a finite circular sector."""
    return [center] + arc_points(
        center, radius, direction-half_angle, direction+half_angle, count)


def cross(a, b, c):
    """Twice the signed area of triangle abc."""
    return ((b[0]-a[0])*(c[1]-a[1])
            - (b[1]-a[1])*(c[0]-a[0]))


def convex_intersection(subject, clipper):
    """Clip a convex polygon by another counter-clockwise convex polygon."""
    output = list(subject)
    for clip_start, clip_end in zip(clipper, clipper[1:] + clipper[:1]):
        if not output:
            break
        input_polygon, output = output, []
        start = input_polygon[-1]
        start_side = cross(clip_start, clip_end, start)
        for end in input_polygon:
            end_side = cross(clip_start, clip_end, end)
            start_inside, end_inside = start_side >= -1e-10, end_side >= -1e-10
            if start_inside != end_inside:
                fraction = start_side / (start_side-end_side)
                output.append((start[0] + fraction*(end[0]-start[0]),
                               start[1] + fraction*(end[1]-start[1])))
            if end_inside:
                output.append(end)
            start, start_side = end, end_side
    return output


def add_sector_construction(ax, center, direction, half_angle, radius,
                            color, detector_label):
    """Draw a finite sector, its bearing line, and dashed ray extensions."""
    for boundary in (direction-half_angle, direction+half_angle):
        arc_end = (center[0] + radius*cos(boundary),
                   center[1] + radius*sin(boundary))
        far_end = (center[0] + (radius+1.35)*cos(boundary),
                   center[1] + (radius+1.35)*sin(boundary))
        ax.plot([center[0], arc_end[0]], [center[1], arc_end[1]],
                color=color, lw=1.0)
        ax.plot([arc_end[0], far_end[0]], [arc_end[1], far_end[1]],
                color=color, lw=0.9, ls=(0, (4, 3)))
    central_end = (center[0] + (radius+1.35)*cos(direction),
                   center[1] + (radius+1.35)*sin(direction))
    ax.plot([center[0], central_end[0]], [center[1], central_end[1]],
            color=color, lw=0.75, ls=":")
    sector_arc = arc_points(center, radius, direction-half_angle,
                            direction+half_angle)
    ax.plot([point[0] for point in sector_arc],
            [point[1] for point in sector_arc], color=color, lw=1.15)
    ax.add_patch(Arc(center, 0.92, 0.92,
                     theta1=degrees(direction-half_angle),
                     theta2=degrees(direction+half_angle),
                     color=color, lw=0.8))
    ax.plot(*center, "ko", ms=3.2)
    ax.text(center[0]-0.04, center[1]-0.17, detector_label,
            ha="center", va="top")


def plot_receive_radius_arc():
    """Draw two finite 2-degree sectors whose overlap has a circular edge."""
    fig, ax = plt.subplots(figsize=(4.5, 3.4))
    # The two-degree aperture is exaggerated solely for geometric legibility.
    half_angle = radians(12.0)
    radius = 3.6
    s1, direction1 = (-3.0, -2.0), atan2(2.0, 3.0)
    s2, direction2 = (2.0, -1.5), atan2(1.5, -2.0)
    sector1 = sector_polygon(s1, direction1, half_angle, radius)
    sector2 = sector_polygon(s2, direction2, half_angle, radius)
    long_sector1 = sector_polygon(s1, direction1, half_angle, 8.5)
    long_sector2 = sector_polygon(s2, direction2, half_angle, 8.5)
    omega = convex_intersection(long_sector1, long_sector2)
    feasible = convex_intersection(sector1, sector2)

    ax.add_patch(Polygon(omega, closed=True, facecolor="#e7eaee",
                         edgecolor="0.48", lw=0.9, ls=":"))
    ax.add_patch(Polygon(feasible, closed=True, facecolor="#91bad6",
                         edgecolor="black", lw=1.25))
    add_sector_construction(ax, s1, direction1, half_angle, radius,
                            "#3f6f91", r"$S_1$")
    add_sector_construction(ax, s2, direction2, half_angle, radius,
                            "#9a6339", r"$S_2$")
    ax.annotate(r"$\Omega$", xy=(0.28, 0.37), xytext=(1.25, 0.92),
                arrowprops=dict(arrowstyle="-", color="0.4", lw=0.7),
                color="0.30", ha="center")
    ax.text(-0.38, -0.28, r"$K$", ha="center", va="center")
    ax.text(-2.8, -2.8, r"$R=1500\,\mathrm{m}$",
            color="#3f6f91", fontsize=9, ha="left", va="bottom")
    ax.set_xlim(-3.5, 3.0)
    ax.set_ylim(-3.0, 1.85)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.91, bottom=0.02)
    save_figure(fig, "q1-receive-radius-arc")


def plot_arena_radius_arc():
    """Draw a bearing-intersection polygon cut by the 1800 m arena disk."""
    fig, ax = plt.subplots(figsize=(4.5, 3.4))
    half_angle = radians(12.0)
    detectors = [(-3.0, -2.0), (2.0, -1.5)]
    directions = [atan2(-p[1], -p[0]) for p in detectors]
    omega = convex_intersection(*[
        sector_polygon(p, direction, half_angle, 8.5)
        for p, direction in zip(detectors, directions)])
    center, radius = (-4.0, -1.0), 4.32
    arena = arc_points(center, radius, 0.0, 2*pi, count=2401)
    feasible = convex_intersection(omega, arena)

    for index, (point, direction, color) in enumerate(zip(
            detectors, directions, ["#3f6f91", "#9a6339"]), 1):
        for offset in (-half_angle, half_angle):
            end = ray(point, degrees(direction+offset), 5.0)
            ax.plot([point[0], end[0]], [point[1], end[1]],
                    color=color, lw=1.0)
        end = ray(point, degrees(direction), 4.9)
        ax.plot([point[0], end[0]], [point[1], end[1]],
                color=color, lw=0.75, ls=":")
        ax.plot(*point, "ko", ms=3.2)
        ax.text(point[0], point[1]-0.17, rf"$S_{index}$",
                ha="center", va="top")

    ax.add_patch(Polygon(omega, closed=True, facecolor="#e7eaee",
                         edgecolor="0.42", lw=1.0, ls=":"))
    local_arc = arc_points(center, radius, radians(-17), radians(38))
    ax.plot(*zip(*local_arc), color="#517a55", lw=1.15, ls="--")
    ax.add_patch(Polygon(feasible, closed=True, facecolor="#91bad6",
                         edgecolor="black", lw=1.25))
    ax.annotate(r"$\Omega$", xy=(0.40, 0.20), xytext=(1.4, 0.95),
                arrowprops=dict(arrowstyle="-", color="0.4", lw=0.7),
                color="0.30", ha="center")
    ax.text(-0.40, -0.24, r"$K$", ha="center", va="center")
    ax.annotate(r"$R_0=1800\,\mathrm{m}$", xy=(0.30, -0.6),
                xytext=(1.0, -2.65), fontsize=9,
                arrowprops=dict(arrowstyle="-", color="#406744", lw=0.7),
                color="#406744", ha="center")
    ax.set_xlim(-3.5, 3.0)
    ax.set_ylim(-3.0, 1.85)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=0.03, right=0.97, top=0.98, bottom=0.03)
    save_figure(fig, "q1-arena-radius-arc")


def main():
    plt.rcParams.update({
        "font.family": "DejaVu Serif",
        "mathtext.fontset": "dejavuserif",
        "axes.linewidth": 0.8,
    })
    plot_region_intersection()
    plot_diameter_circle()
    plot_receive_radius_arc()
    plot_arena_radius_arc()


if __name__ == "__main__":
    main()
