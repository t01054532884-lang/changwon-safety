"""WMS raster measurements for regular Changwon analysis grids."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image


EARTH_RADIUS_M = 6_378_137.0


def red_high_risk_mask(image_bytes: bytes) -> np.ndarray:
    """Apply the red/orange WMS rule used by the project Colab analysis."""
    rgba = np.asarray(Image.open(BytesIO(image_bytes)).convert("RGBA"))
    red = rgba[:, :, 0].astype(np.int16)
    green = rgba[:, :, 1].astype(np.int16)
    blue = rgba[:, :, 2].astype(np.int16)
    alpha = rgba[:, :, 3].astype(np.int16)
    return (
        (alpha > 20)
        & (red >= 100)
        & ((red - green) >= 20)
        & ((red - blue) >= 20)
    )


def red_high_risk_percentage(image_bytes: bytes, grid: dict) -> np.ndarray:
    """Measure red WMS pixel share within every 100 m grid cell."""
    red_mask = red_high_risk_mask(image_bytes)
    height, width = red_mask.shape
    (minimum_latitude, minimum_longitude), (
        maximum_latitude,
        maximum_longitude,
    ) = grid["bounds"]

    minimum_y = EARTH_RADIUS_M * np.log(
        np.tan(np.pi / 4 + np.radians(minimum_latitude) / 2)
    )
    maximum_y = EARTH_RADIUS_M * np.log(
        np.tan(np.pi / 4 + np.radians(maximum_latitude) / 2)
    )
    pixel_x = np.arange(width, dtype=float) + 0.5
    pixel_y = np.arange(height, dtype=float) + 0.5
    longitudes = minimum_longitude + pixel_x / width * (
        maximum_longitude - minimum_longitude
    )
    mercator_y = maximum_y - pixel_y / height * (maximum_y - minimum_y)
    latitudes = np.degrees(
        2 * np.arctan(np.exp(mercator_y / EARTH_RADIUS_M)) - np.pi / 2
    )

    columns = np.floor(
        (longitudes - minimum_longitude) / grid["longitude_step"]
    ).astype(int)
    rows = np.floor(
        (maximum_latitude - latitudes) / grid["latitude_step"]
    ).astype(int)
    row_grid, column_grid = np.meshgrid(rows, columns, indexing="ij")
    valid = (
        (row_grid >= 0)
        & (row_grid < grid["mask"].shape[0])
        & (column_grid >= 0)
        & (column_grid < grid["mask"].shape[1])
    )
    valid &= grid["mask"][
        np.clip(row_grid, 0, grid["mask"].shape[0] - 1),
        np.clip(column_grid, 0, grid["mask"].shape[1] - 1),
    ]
    flat_index = row_grid * grid["mask"].shape[1] + column_grid
    cell_count = grid["mask"].size
    total_pixels = np.bincount(
        flat_index[valid], minlength=cell_count
    ).astype(float)
    red_pixels = np.bincount(
        flat_index[valid & red_mask], minlength=cell_count
    ).astype(float)
    percentages = np.divide(
        red_pixels,
        total_pixels,
        out=np.zeros(cell_count, dtype=float),
        where=total_pixels > 0,
    ) * 100.0
    selected = (
        grid["rows"] * grid["mask"].shape[1] + grid["columns"]
    )
    return np.round(percentages[selected], 2)

