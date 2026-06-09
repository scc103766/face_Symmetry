from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .schemas import Landmark


@dataclass(frozen=True)
class Line2D:
    origin: Landmark
    ux: float
    uy: float

    @classmethod
    def through(cls, top: Landmark, bottom: Landmark) -> "Line2D":
        dx = bottom.x - top.x
        dy = bottom.y - top.y
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            raise ValueError("midline points are degenerate")
        return cls(origin=top, ux=dx / length, uy=dy / length)

    @classmethod
    def fit(cls, points: Iterable[Landmark], *, orient_top: Landmark, orient_bottom: Landmark) -> "Line2D":
        usable = list(points)
        if len(usable) < 2:
            return cls.through(orient_top, orient_bottom)

        mean_x = sum(point.x for point in usable) / len(usable)
        mean_y = sum(point.y for point in usable) / len(usable)
        sxx = sum((point.x - mean_x) ** 2 for point in usable)
        syy = sum((point.y - mean_y) ** 2 for point in usable)
        sxy = sum((point.x - mean_x) * (point.y - mean_y) for point in usable)

        if abs(sxy) <= 1e-12 and abs(sxx - syy) <= 1e-12:
            return cls.through(orient_top, orient_bottom)

        angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
        ux = math.cos(angle)
        uy = math.sin(angle)

        orient_dx = orient_bottom.x - orient_top.x
        orient_dy = orient_bottom.y - orient_top.y
        if ux * orient_dx + uy * orient_dy < 0:
            ux = -ux
            uy = -uy

        length = math.hypot(ux, uy)
        if length <= 1e-9:
            return cls.through(orient_top, orient_bottom)
        return cls(origin=Landmark(mean_x, mean_y), ux=ux / length, uy=uy / length)

    @property
    def nx(self) -> float:
        return -self.uy

    @property
    def ny(self) -> float:
        return self.ux

    def along(self, point: Landmark) -> float:
        dx = point.x - self.origin.x
        dy = point.y - self.origin.y
        return dx * self.ux + dy * self.uy

    def signed_distance(self, point: Landmark) -> float:
        dx = point.x - self.origin.x
        dy = point.y - self.origin.y
        return dx * self.nx + dy * self.ny

    def reflect(self, point: Landmark) -> Landmark:
        distance = self.signed_distance(point)
        return Landmark(
            x=point.x - 2.0 * distance * self.nx,
            y=point.y - 2.0 * distance * self.ny,
            confidence=point.confidence,
        )


def euclidean(a: Landmark, b: Landmark) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def ramp(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("high must be greater than low")
    return clamp((value - low) / (high - low))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)
