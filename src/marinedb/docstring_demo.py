#!/usr/bin/python
# coding: utf-8

"""Demonstration module for mkdocstrings rendering.

This module is intentionally simple and exists only to showcase rich
Google-style docstrings, including parameters, return values, exceptions,
examples, and math notation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r"""Compute the great-circle distance between two geographic points.

    The implementation uses the Haversine formula:

    $$
    d = 2R \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta \varphi}{2}\right)
    + \cos(\varphi_1)\cos(\varphi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)}\right)
    $$

    Args:
        lat1: Latitude of point 1, in decimal degrees.
        lon1: Longitude of point 1, in decimal degrees.
        lat2: Latitude of point 2, in decimal degrees.
        lon2: Longitude of point 2, in decimal degrees.

    Returns:
        Great-circle distance in kilometers.

    Raises:
        ValueError: If one coordinate is outside valid latitude/longitude bounds.

    Examples:
        Compute distance between two nearby points::

            >>> round(haversine_distance_km(48.8566, 2.3522, 51.5074, -0.1278), 1)
            343.6
    """

    for lat in (lat1, lat2):
        if lat < -90.0 or lat > 90.0:
            raise ValueError("Latitude must be in [-90, 90].")
    for lon in (lon1, lon2):
        if lon < -180.0 or lon > 180.0:
            raise ValueError("Longitude must be in [-180, 180].")

    phi1 = radians(lat1)
    phi2 = radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)

    a = sin(dphi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2.0) ** 2
    c = 2.0 * asin(sqrt(a))
    return EARTH_RADIUS_KM * c


@dataclass(frozen=True)
class WindowSummary:
    """Small statistics container used as a class docstring example.

    Attributes:
        count: Number of observations in the window.
        minimum: Smallest value.
        maximum: Largest value.
        mean: Arithmetic mean.
    """

    count: int
    minimum: float
    maximum: float
    mean: float


def summarize_window(values: list[float]) -> WindowSummary:
    """Summarize a non-empty list of values.

    Args:
        values: Numeric values to summarize.

    Returns:
        A :class:`WindowSummary` instance with count/min/max/mean.

    Raises:
        ValueError: If ``values`` is empty.

    Example: Basic usage
        blabla

            >>> summary = summarize_window([1.0, 2.0, 3.0])
            >>> summary.count, summary.minimum, summary.maximum, summary.mean
            (3, 1.0, 3.0, 2.0)
    """

    if not values:
        raise ValueError("values must contain at least one number")

    count = len(values)
    minimum = min(values)
    maximum = max(values)
    mean = sum(values) / count
    return WindowSummary(count=count, minimum=minimum, maximum=maximum, mean=mean)


def normalize_probability(p: float, eps: float = 1e-12) -> float:
    r"""Clamp a probability into the open interval ``(0, 1)``.

    This is useful before applying transforms like logit:

    $$
    \text{logit}(p) = \log\left(\frac{p}{1 - p}\right)
    $$

    Args:
        p: Input probability.
        eps: Numerical safety margin from the interval boundaries.

    Returns:
        A value in ``[eps, 1 - eps]``.

    Notes:
        - If ``p < eps``, the function returns ``eps``.
        - If ``p > 1 - eps``, the function returns ``1 - eps``.
    """

    if p < eps:
        return eps
    if p > 1.0 - eps:
        return 1.0 - eps
    return p
