"""B-Q1 Python canvas for supplied bearings. No localization or simulation.

Public API: plot_bearings(detector_points, bearings_deg, source=None).
All bearings are already valid observations. Source truth is optional artwork.
"""

from math import cos, sin, radians, hypot, isfinite
from pathlib import Path

ERROR_DEG = 1.0
DOMAIN_RADIUS = 1800.0
COLORS = ("#277DA8", "#D58A29", "#329578", "#8A67AA", "#AD607D", "#597C92")


def _finite(value, name):
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}必须是有限数值。") from None
    if not isfinite(number):
        raise ValueError(f"{name}必须是有限数值。")
    return number


def _point(point, name):
    try:
        values = tuple(point)
    except TypeError:
        raise ValueError(f"{name}须包含 x、y 两个坐标。") from None
    if len(values) != 2:
        raise ValueError(f"{name}须包含 x、y 两个坐标。")
    return tuple(_finite(v, name) for v in values)


def validate_inputs(detector_points, bearings_deg, source=None):
    """Validate plotting inputs only; do not infer target, distance or signal."""
    try:
        points = [_point(p, f"S{i+1}") for i, p in enumerate(detector_points)]
        bearings = [_finite(b, f"S{i+1} 示向度") for i, b in enumerate(bearings_deg)]
    except TypeError:
        raise ValueError("检测点和示向度必须为序列。") from None
    if not points or len(points) != len(bearings):
        raise ValueError("至少输入一个检测点，且坐标数与示向度数必须一致。")
    if any(not 0 <= b < 360 for b in bearings):
        raise ValueError("示向度须在 [0, 360) 度内；0 度为正东，90 度为正北。")
    reference = None if source is None else _point(source, "参考源 G")
    if reference is not None and hypot(*reference) > DOMAIN_RADIUS:
        raise ValueError("参考源 G 须位于半径 1800 m 的分布圆形区域内。")
    return points, bearings, reference


def plot_bearings(detector_points, bearings_deg, source=None, *, region=None,
                  error_deg=ERROR_DEG, show=True, output_path=None):
    """Draw bearings and an optional Q1 localization result; return (fig, ax).

    Parameters
    ----------
    detector_points : sequence of (x, y), in metres
    bearings_deg : sequence of measured bearings, in [0, 360), same order
    source : optional (x, y), a reference marker only
    region : optional result returned by ``geometry.localize``
    error_deg : half-width of each bearing wedge in degrees
    show : whether to open the native Matplotlib window
    output_path : optional .png or .svg path, saved before opening the window

    This function renders but does not solve geometry, sample measurement error,
    check reception distance, or use source truth. Pass a region computed only
    from detector coordinates and measured bearings. Dashed rays are bearing
    +/- ``error_deg``. Pass show=False for headless file rendering.
    """
    points, bearings, reference = validate_inputs(detector_points, bearings_deg, source)
    error_deg = _finite(error_deg, "示向度误差界")
    if not 0 < error_deg < 90:
        raise ValueError("示向度误差界须在 (0, 90) 度内。")
    if output_path is not None and Path(output_path).suffix.lower() not in (".png", ".svg"):
        raise ValueError("本版输出支持 .png 或 .svg。")
    try:
        import matplotlib as mpl
        if not show:
            # Object-oriented Agg canvas avoids changing an embedding app's backend.
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
        else:
            import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.patches import Circle, Polygon, FancyArrowPatch
    except ImportError:
        raise RuntimeError("缺少绘图库，请在 solution/ 下运行：python -m pip install -r requirements.txt") from None

    style = {"font.family": "DejaVu Sans", "font.size": 10,
             "axes.labelcolor": "#465569", "text.color": "#324153",
             "xtick.color": "#718092", "ytick.color": "#718092",
             "svg.fonttype": "path", "savefig.facecolor": "white"}
    with mpl.rc_context(style):
        if show:
            fig, ax = plt.subplots(figsize=(10, 10), facecolor="white")
            manager = fig.canvas.manager
            if manager is not None:
                manager.set_window_title("Problem B | Bearing visualization")
            if not getattr(fig.canvas, "required_interactive_framework", None):
                plt.close(fig)
                raise RuntimeError("当前 Python 没有可用桌面绘图后端。可在带 Tk/Qt 的桌面 Python 中运行，或使用 --no-show --output 图片.png 导出。")
        else:
            fig = Figure(figsize=(10, 10), facecolor="white")
            FigureCanvasAgg(fig)
            ax = fig.subplots()
        fig.subplots_adjust(left=.11, right=.96, bottom=.23, top=.88)
        plotted_points = list(points)
        if reference is not None:
            plotted_points.append(reference)
        if region is not None:
            plotted_points.extend(region.get("vertices", []))
            plotted_points.extend(region.get("display_polygon", []))
        extent = max(DOMAIN_RADIUS, *(max(abs(x), abs(y)) for x, y in plotted_points)) * 1.17
        ray_length = extent*5
        ax.set(xlim=(-extent, extent), ylim=(-extent, extent),
               xlabel="x / m  (East)", ylabel="y / m  (North)", aspect="equal")
        ax.set_facecolor("white")
        ax.set_axisbelow(True)
        ax.grid(True, color="#EAF0F4", linewidth=.65)
        for spine in ax.spines.values():
            spine.set_color("#DCE4EB")
        ax.tick_params(length=3, width=.6)
        ax.axhline(0, color="#9EADB9", linewidth=.9, zorder=1)
        ax.axvline(0, color="#9EADB9", linewidth=.9, zorder=1)
        domain = Circle((0, 0), DOMAIN_RADIUS, facecolor="none", edgecolor="#A5B4C1",
                        linewidth=1.2, linestyle=(0, (6, 4)), zorder=2)
        domain.set_gid("distribution-circle")
        ax.add_patch(domain)
        ax.annotate("O", (0, 0), xytext=(5, -13), textcoords="offset points",
                    color="#708090", fontsize=9)
        if region is not None:
            region_points = (region.get("vertices", []) if region.get("status") == "bounded"
                             else region.get("display_polygon", []))
            if len(region_points) >= 3:
                patch = Polygon(region_points, facecolor="#8063AF", alpha=.16,
                                edgecolor="#6D4C9B", linewidth=1.5, zorder=2)
                patch.set_gid("localization-region")
                ax.add_patch(patch)
            elif len(region_points) == 2:
                ax.plot(*zip(*region_points), color="#6D4C9A", linewidth=3, zorder=4)
            elif len(region_points) == 1:
                ax.plot(*region_points[0], "o", color="#6D4C9A", markersize=6, zorder=4)
        for i, ((x, y), bearing) in enumerate(zip(points, bearings)):
            color = COLORS[i % len(COLORS)]
            # Trigonometry below only constructs drawing endpoints.
            ends = [(x+ray_length*cos(radians(bearing+offset)),
                     y+ray_length*sin(radians(bearing+offset)))
                    for offset in (-error_deg, error_deg)]
            wedge = Polygon([(x, y), *ends], facecolor=color, alpha=.065,
                            edgecolor="none", zorder=2)
            wedge.set_gid(f"S{i+1}-error-sector")
            ax.add_patch(wedge)
            for offset, endpoint in zip((-error_deg, error_deg), ends):
                line, = ax.plot([x, endpoint[0]], [y, endpoint[1]], color=color,
                                linewidth=.9, linestyle=(0, (4, 4)), alpha=.7, zorder=3)
                line.set_gid(f"S{i+1}-boundary-{offset:+g}")
            direction = (cos(radians(bearing)), sin(radians(bearing)))
            line, = ax.plot([x, x+ray_length*direction[0]], [y, y+ray_length*direction[1]],
                            color=color, linewidth=1.25, zorder=3)
            line.set_gid(f"S{i+1}-bearing")
            arrow = FancyArrowPatch((x+extent*.09*direction[0], y+extent*.09*direction[1]),
                                    (x+extent*.16*direction[0], y+extent*.16*direction[1]),
                                    arrowstyle="-|>", mutation_scale=11, linewidth=1.1,
                                    color=color, zorder=4)
            ax.add_patch(arrow)
            marker, = ax.plot(x, y, "o", color=color, markersize=6,
                              markeredgecolor="white", markeredgewidth=1.1, zorder=6)
            marker.set_gid(f"S{i+1}-point")
            ax.annotate(f"S{i+1}", (x, y), xytext=(8, 8), textcoords="offset points",
                        color=color, fontsize=10, fontweight="medium", zorder=7,
                        bbox=dict(facecolor="white", edgecolor="none", alpha=.7, pad=.6))
        if region is not None and region.get("diameter_pair"):
            p, q = region["diameter_pair"]
            line, = ax.plot([p[0], q[0]], [p[1], q[1]], color="#5E478E",
                            linewidth=2.4, zorder=6)
            line.set_gid("region-diameter")
            ax.plot([p[0], q[0]], [p[1], q[1]], "o", color="#5E478E",
                    markersize=4, zorder=7)
        if region is not None and region.get("diameter_circle"):
            circle_data = region["diameter_circle"]
            outline = Circle(circle_data["center"], circle_data["radius"],
                             facecolor="none", edgecolor="#9A6A3A", linewidth=1.4,
                             linestyle=(0, (7, 4)), zorder=5)
            outline.set_gid("diameter-circle")
            ax.add_patch(outline)
        if reference is not None:
            marker, = ax.plot(*reference, "s", color="#C94F58", markersize=7,
                              markeredgecolor="white", markeredgewidth=1.1, zorder=8)
            marker.set_gid("reference-source")
            ax.annotate("G", reference, xytext=(8, -15), textcoords="offset points",
                        color="#C94F58", fontsize=11, zorder=9,
                        bbox=dict(facecolor="white", edgecolor="none", alpha=.7, pad=.6))
        if region is not None and region.get("status") == "bounded" and region.get("vertices"):
            region_vertices = region["vertices"]
            xs = [point[0] for point in region_vertices]
            ys = [point[1] for point in region_vertices]
            local_width = max(max(xs)-min(xs), max(ys)-min(ys),
                              2*region["diameter_circle"]["radius"], 1.0)*1.35
            local_center = ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2)
            detail = ax.inset_axes([.61, .61, .35, .35])
            detail.set(xlim=(local_center[0]-local_width/2, local_center[0]+local_width/2),
                       ylim=(local_center[1]-local_width/2, local_center[1]+local_width/2),
                       aspect="equal")
            detail.set_facecolor("white")
            detail.grid(True, color="#E8EDF2", linewidth=.65)
            detail.tick_params(length=2, labelsize=7, colors="#6E7C8B")
            for spine in detail.spines.values():
                spine.set_color("#CFD8E0")
            detail.add_patch(Polygon(region_vertices, facecolor="#8063AF", alpha=.2,
                                     edgecolor="#6D4C9B", linewidth=1.5))
            p, q = region["diameter_pair"]
            detail.plot([p[0], q[0]], [p[1], q[1]], color="#5E478E", linewidth=2.4)
            circle_data = region["diameter_circle"]
            detail.add_patch(Circle(circle_data["center"], circle_data["radius"],
                                    facecolor="none", edgecolor="#9A6A3A", linewidth=1.3,
                                    linestyle=(0, (7, 4))))
            detail.plot(xs, ys, "o", color="#6D4C9B", markersize=3.5)
            detail.set_title("Localization detail", fontsize=10, color="#344E65", pad=5)
        fig.suptitle("Q1 bearing localization" if region is not None else "Bearing observations",
                     x=.12, y=.963, ha="left",
                     fontsize=19, fontweight="medium", color="#273D50")
        status = ""
        if region is not None:
            if region.get("status") == "bounded":
                coverage = "yes" if region["diameter_circle"]["covers"] else "no"
                status = f"   |   diameter: {region['diameter']:.3f} m   |   diameter circle covers: {coverage}"
            else:
                status = f"   |   region: {region.get('status', 'unknown')}"
        fig.text(.12, .916, f"{len(points)} observation points   |   error bound: +/-{error_deg:g} deg{status}",
                 fontsize=10, color="#718092")
        legend = [Line2D([], [], color="#536F85", linewidth=1.3, label="Measured bearing"),
                  Line2D([], [], color="#536F85", linestyle=(0, (4, 4)), linewidth=1,
                         label=f"Error boundary (+/-{error_deg:g} deg)"),
                  Line2D([], [], marker="o", color="none", markerfacecolor="#536F85",
                         markeredgecolor="white", markersize=7, label="Detector")]
        if reference is not None:
            legend.append(Line2D([], [], marker="s", color="none", markerfacecolor="#C94F58",
                                 markersize=6, label="Source (reference)"))
        if region is not None:
            legend.extend([
                Line2D([], [], color="#8063AF", linewidth=6, alpha=.3,
                       label="Localization region"),
                Line2D([], [], color="#5E478E", linewidth=2.4, label="Region diameter"),
                Line2D([], [], color="#9A6A3A", linestyle=(0, (7, 4)), linewidth=1.4,
                       label="Circle with diameter D"),
            ])
        fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.53, .025),
                   ncol=3 if region is not None else 2, frameon=False, fontsize=9, handlelength=2.5,
                   columnspacing=2.8, labelspacing=.8)
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, dpi=240, facecolor="white")
        if show:
            plt.show()
        return fig, ax
