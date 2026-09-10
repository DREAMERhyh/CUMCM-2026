"""Official virtual-time accounting, kept independent from strategy code."""

import math

from .models import TimeBreakdown


def measure_cost(previous, target, current_channel, target_channel):
    return TimeBreakdown(
        movement_s=math.dist(previous, target)/5.0,
        switching_s=0.0 if current_channel == target_channel else 1.0,
        measurement_s=5.0,
    )


def clear_cost(previous, target, success):
    return TimeBreakdown(
        movement_s=math.dist(previous, target)/5.0,
        optical_s=3.0,
        laser_s=2.0 if success else 0.0,
    )

