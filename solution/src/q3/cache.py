"""Bounded, state-keyed computation cache for Q3 planning.

The cache is deliberately internal to one ``Q3Policy`` instance.  Keys are
derived from immutable snapshots of geometry, observations, robot state and
configuration; cached values therefore never stand in for newer observations.
"""

from collections import Counter, OrderedDict
from copy import deepcopy
from dataclasses import fields, is_dataclass
import math


def _float_key(value, digits=8):
    value = float(value)
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0.0 else "-inf"
    rounded = round(value, digits)
    return 0.0 if rounded == -0.0 else rounded


def freeze_value(value):
    """Convert nested planner data into a deterministic hashable value."""
    if is_dataclass(value):
        return (
            type(value).__name__,
            tuple((item.name, freeze_value(getattr(value, item.name)))
                  for item in fields(value)),
        )
    if isinstance(value, dict):
        return tuple(sorted(
            (str(key), freeze_value(item)) for key, item in value.items()
        ))
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(freeze_value(item) for item in value))
    if isinstance(value, float):
        return _float_key(value)
    if isinstance(value, (str, int, bool, type(None))):
        return value
    return repr(value)


def point_fingerprint(point):
    return tuple(_float_key(value) for value in point)


def region_fingerprint(region):
    """Fingerprint every geometric field that can affect Q3 costs."""
    if region is None:
        return None
    return freeze_value({
        "status": region.get("status"),
        "vertices": region.get("vertices", ()),
        "planes": region.get("planes", ()),
        "minimum_enclosing_circle": region.get(
            "minimum_enclosing_circle"
        ),
    })


def observations_fingerprint(observations):
    return tuple((
        point_fingerprint(observation.position),
        observation.channel,
        observation.result,
        (None if observation.bearing_deg is None
         else _float_key(observation.bearing_deg)),
    ) for observation in observations)


def posterior_fingerprint(track):
    """Fingerprint inputs used by Q2 and finite-scenario posterior scoring."""
    return (
        track.channel,
        observations_fingerprint(track.observations),
        region_fingerprint(track.region),
    )


def config_fingerprint(config):
    return freeze_value(config)


class Q3ComputationCache:
    """One bounded LRU shared by named Q3 computation layers."""

    def __init__(self, capacity=4096, *, enabled=True):
        if capacity < 1:
            raise ValueError("缓存容量至少为1。")
        self.capacity = int(capacity)
        self.enabled = bool(enabled)
        self._items = OrderedDict()
        self._hits = Counter()
        self._misses = Counter()
        self._stores = Counter()
        self._evictions = Counter()
        self._state_changes = 0

    def get_or_compute(self, namespace, key, compute, *, clone=False,
                       cache_if=None):
        """Return a cached value or compute and store it atomically."""
        if not self.enabled:
            return compute()
        full_key = str(namespace), freeze_value(key)
        if full_key in self._items:
            self._hits[namespace] += 1
            value = self._items.pop(full_key)
            self._items[full_key] = value
            return deepcopy(value) if clone else value
        self._misses[namespace] += 1
        value = compute()
        if cache_if is not None and not cache_if(value):
            return value
        stored = deepcopy(value) if clone else value
        self._items[full_key] = stored
        self._stores[namespace] += 1
        while len(self._items) > self.capacity:
            (evicted_namespace, _), _ = self._items.popitem(last=False)
            self._evictions[evicted_namespace] += 1
        return deepcopy(stored) if clone else stored

    def note_state_change(self):
        """Record a real response; versioned keys make older entries stale."""
        if self.enabled:
            self._state_changes += 1

    def clear(self):
        self._items.clear()

    def snapshot(self):
        namespaces = sorted(
            set(self._hits) | set(self._misses)
            | set(self._stores) | set(self._evictions)
        )
        per_namespace = {}
        for namespace in namespaces:
            hits = self._hits[namespace]
            misses = self._misses[namespace]
            per_namespace[namespace] = {
                "hits": hits,
                "misses": misses,
                "stores": self._stores[namespace],
                "evictions": self._evictions[namespace],
                "hit_rate": hits / (hits + misses) if hits + misses else 0.0,
            }
        hits = sum(self._hits.values())
        misses = sum(self._misses.values())
        return {
            "enabled": self.enabled,
            "capacity": self.capacity,
            "entries": len(self._items),
            "hits": hits,
            "misses": misses,
            "stores": sum(self._stores.values()),
            "evictions": sum(self._evictions.values()),
            "state_changes": self._state_changes,
            "hit_rate": hits / (hits + misses) if hits + misses else 0.0,
            "namespaces": per_namespace,
        }
