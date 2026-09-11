"""Q4 uses the Q3 state machine with directional coverage and probes."""

from q3.policy import Q3Policy
from .directional import four_sided_points, grid121


class Q4Policy(Q3Policy):
    def __init__(self, *, max_refinements=2, error_deg=1.005,
                 fim_cpu_time_limit_s=6.0):
        super().__init__(max_refinements=max_refinements,
                         error_deg=error_deg,
                         coverage_points=grid121(),
                         fim_cpu_time_limit_s=fim_cpu_time_limit_s)

    def _refinement_point(self, state, track):
        circle = track.region["minimum_enclosing_circle"]
        probes = four_sided_points(tuple(circle["center"]), circle["radius"])
        if probes:
            if not track.probe_points:
                track.probe_points = probes
            index = min(track.refinements, len(track.probe_points)-1)
            return track.probe_points[index]
        return super()._refinement_point(state, track)

