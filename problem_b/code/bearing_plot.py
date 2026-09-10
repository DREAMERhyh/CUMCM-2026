"""Python canvas for supplied bearings. No localization or simulation.

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
        raise ValueError("参考源 G 须位于半径 1800 m 的分布圆域内。")
    return points, bearings, reference


def plot_bearings(detector_points, bearings_deg, source=None, *,
                  show=True, output_path=None):
    """Draw known bearings and fixed +/-1 degree boundaries; return (fig, ax).

    Parameters
    ----------
    detector_points : sequence of (x, y), in metres
    bearings_deg : sequence of measured bearings, in [0, 360), same order
    source : optional (x, y), a reference marker only
    show : whether to open the native Matplotlib window
    output_path : optional .png or .svg path, saved before opening the window

    No intersection, diameter, measurement error sampling, reception-distance
    check or source estimation is performed. Dashed rays are bearing +/-1 deg.
    Pass show=False for file-only rendering in a headless environment.
    """
    points, bearings, reference = validate_inputs(detector_points, bearings_deg, source)
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
        raise RuntimeError("缺少绘图库，请运行：python -m pip install -r problem_b/requirements.txt") from None

    style = {"font.family": "DejaVu Sans", "font.size": 10,
             "axes.labelcolor": "#465569", "text.color": "#324153",
             "xtick.color": "#718092", "ytick.color": "#718092",
             "svg.fonttype": "path", "savefig.facecolor": "white"}
    with mpl.rc_context(style):
        if show:
            fig, ax = plt.subplots(figsize=(9, 9), facecolor="white")
            manager = fig.canvas.manager
            if manager is not None:
                manager.set_window_title("Problem B | Bearing visualization")
            if not getattr(fig.canvas, "required_interactive_framework", None):
                plt.close(fig)
                raise RuntimeError("当前 Python 没有可用桌面绘图后端。可在带 Tk/Qt 的桌面 Python 中运行，或使用 --no-show --output 图片.png 导出。")
        else:
            fig = Figure(figsize=(9, 9), facecolor="white")
            FigureCanvasAgg(fig)
            ax = fig.subplots()
        fig.subplots_adjust(left=.12, right=.95, bottom=.16, top=.88)
        extent = max(DOMAIN_RADIUS, *(max(abs(x), abs(y)) for x, y in points)) * 1.17
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
        for i, ((x, y), bearing) in enumerate(zip(points, bearings)):
            color = COLORS[i % len(COLORS)]
            # Trigonometry below only constructs drawing endpoints.
            ends = [(x+ray_length*cos(radians(bearing+offset)),
                     y+ray_length*sin(radians(bearing+offset)))
                    for offset in (-ERROR_DEG, ERROR_DEG)]
            wedge = Polygon([(x, y), *ends], facecolor=color, alpha=.065,
                            edgecolor="none", zorder=2)
            wedge.set_gid(f"S{i+1}-error-sector")
            ax.add_patch(wedge)
            for offset, endpoint in zip((-ERROR_DEG, ERROR_DEG), ends):
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
        if reference is not None:
            marker, = ax.plot(*reference, "s", color="#C94F58", markersize=7,
                              markeredgecolor="white", markeredgewidth=1.1, zorder=8)
            marker.set_gid("reference-source")
            ax.annotate("G", reference, xytext=(8, -15), textcoords="offset points",
                        color="#C94F58", fontsize=11, zorder=9,
                        bbox=dict(facecolor="white", edgecolor="none", alpha=.7, pad=.6))
        fig.suptitle("Bearing observations", x=.12, y=.963, ha="left",
                     fontsize=19, fontweight="medium", color="#273D50")
        fig.text(.12, .916, f"{len(points)} observation points   |   error bound: +/-1 deg   |   domain radius: 1800 m",
                 fontsize=10, color="#718092")
        legend = [Line2D([], [], color="#536F85", linewidth=1.3, label="Measured bearing"),
                  Line2D([], [], color="#536F85", linestyle=(0, (4, 4)), linewidth=1,
                         label="Error boundary (+/-1 deg)"),
                  Line2D([], [], marker="o", color="none", markerfacecolor="#536F85",
                         markeredgecolor="white", markersize=7, label="Detector")]
        if reference is not None:
            legend.append(Line2D([], [], marker="s", color="none", markerfacecolor="#C94F58",
                                 markersize=6, label="Source (reference)"))
        fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.53, .045),
                   ncol=2, frameon=False, fontsize=9, handlelength=2.5,
                   columnspacing=2.8, labelspacing=.8)
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, dpi=240, facecolor="white")
        if show:
            plt.show()
        return fig, ax
