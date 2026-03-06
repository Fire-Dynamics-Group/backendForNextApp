"""External Fire Spread calculation engine (BRE 135)."""

import math
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
from io import StringIO

from services.efs_data import commercial_raw, residential_raw

COLUMNS = ["Height", 20, 30, 40, 50, 60, 70, 80, 90, 100]


def _convert_to_df(data: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(data), sep="\t", header=None)
    df.columns = COLUMNS
    return df


def _build_tables(raw_dict: dict) -> dict:
    return {k: _convert_to_df(v) for k, v in raw_dict.items()}


COMMERCIAL = _build_tables(commercial_raw)
RESIDENTIAL = _build_tables(residential_raw)


def return_bre_dimension(measured: float) -> int:
    if measured <= 1:
        return math.ceil(measured / 3) * 3
    elif measured <= 30:
        return math.ceil(measured / 3) * 3
    elif measured <= 60:
        return math.ceil(measured / 10) * 10
    elif measured <= 120:
        return math.ceil(measured / 20) * 20
    else:
        return 130


def interpolate(
    first_ref: Optional[float],
    second_ref: float,
    first_col: Optional[float],
    second_col: float,
    measured: float,
) -> float:
    if first_ref is None:
        first_ref = 1
        first_col = 0

    if measured == first_ref == second_ref:
        diff = 0
    else:
        diff = (measured - first_ref) / (second_ref - first_ref)

    return first_col + diff * (second_col - first_col)


def run_single_calc(
    height: float,
    width: float,
    boundary_dist: float,
    has_suppression: bool,
    is_commercial: bool = True,
) -> Tuple[float, float, float, float, float, float, int, int]:
    """Run BRE 135 calc for a single elevation. Returns same tuple as Python app."""
    bre_height = return_bre_dimension(height)
    bre_width = return_bre_dimension(width)

    data = COMMERCIAL if is_commercial else RESIDENTIAL
    df = data[bre_height]
    row = df[df["Height"] == float(bre_width)]

    effective_dist = boundary_dist * 2 if has_suppression else boundary_dist

    row_less = np.where([row.values[0][1:] <= effective_dist][0])

    if row_less[0].size == 0:
        less_col = None
        less_cell = None
    else:
        less_index = row_less[0][-1]
        less_col = COLUMNS[less_index + 1]
        less_cell = row[less_col].values[0]

    row_more = np.where([row.values[0][1:] >= effective_dist][0])

    if row_more[0].size == 0:
        more_col = None
        more_cell = None
    else:
        more_index = row_more[0][0]
        more_col = COLUMNS[more_index + 1]
        more_cell = row[more_col].values[0]

    if effective_dist < 1:
        percentage = 0
    elif more_cell is None:
        percentage = 0
    else:
        percentage = interpolate(
            first_ref=less_cell,
            second_ref=more_cell,
            first_col=less_col,
            second_col=more_col,
            measured=effective_dist,
        )

    area = bre_height * bre_width
    allowable_area = area * percentage / 100
    actual_area = height * width
    actual_allowable_area = round(actual_area - allowable_area, 1)
    actual_percentage = round(round(actual_allowable_area / actual_area, 2) * 100, 1)

    return (
        round(percentage, 1),
        actual_percentage,
        actual_area,
        round(allowable_area, 1),
        actual_allowable_area,
        area,
        bre_height,
        bre_width,
    )


def run_efs_calcs(
    height_list: List[float],
    width_list: List[float],
    boundary_dist_list: List[float],
    has_suppression_list: List[bool],
    is_commercial: bool = True,
) -> List[dict]:
    """Run calcs for all elevations and return results as list of dicts."""
    results = []

    for idx in range(len(height_list)):
        height = height_list[idx]
        width = width_list[idx]
        boundary_dist = boundary_dist_list[idx]
        has_suppression = has_suppression_list[idx]

        percentage, actual_percentage, actual_area, allowable_area, actual_allowable_area, area, bre_height, bre_width = run_single_calc(
            height, width, boundary_dist, has_suppression, is_commercial
        )

        result = {
            "elevation_number": idx + 1,
            "boundary_distance": str(boundary_dist),
            "er_height": str(height),
            "er_width": str(width),
            "bre_height": str(bre_height),
            "bre_width": str(bre_width),
            "bre_percentage": str(percentage) + "%",
            "allowable_area": str(allowable_area),
            "actual_area": str(actual_area),
            "actual_protected_area": str(actual_allowable_area),
            "actual_percentage": str(actual_percentage) + "%",
        }

        if boundary_dist < 1:
            result["boundary_distance"] = "<1"
            result["er_height"] = "-"
            result["er_width"] = "-"
            result["bre_height"] = "-"
            result["bre_width"] = "-"
            result["bre_percentage"] = "0%"
            result["allowable_area"] = "-"
            result["actual_area"] = "-"
            result["actual_protected_area"] = "-"
            result["actual_percentage"] = "-"
        elif boundary_dist == 1:
            result["er_height"] = "-"
            result["er_width"] = "-"
            result["bre_height"] = "-"
            result["bre_width"] = "-"
            result["bre_percentage"] = "0%"
            result["allowable_area"] = "-"
            result["actual_area"] = "-"
            result["actual_protected_area"] = "-"
            result["actual_percentage"] = "-"
        elif boundary_dist > 120:
            result["boundary_distance"] = ">120"

        if percentage == 100:
            result["bre_percentage"] = "100%"
            result["allowable_area"] = "-"
            result["actual_area"] = "-"
            result["actual_protected_area"] = "-"
            result["actual_percentage"] = "-"

        results.append(result)

    return results
