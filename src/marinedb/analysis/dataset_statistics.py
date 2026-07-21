#!/usr/bin/python
# coding: utf-8

import os
import json
import numpy as np
import pandas as pd
import h3
import h3pandas
from pathlib import Path

def prepare_occurrence_data(df: pd.DataFrame, latkey: str, lonkey: str, speciesidkey: str, specieskey: str = None, resolution: int = 8):

    data = df.h3.geo_to_h3(
        resolution=resolution,
        lat_col=latkey,
        lng_col=lonkey,
        set_index=False,
    )

    species_name_mapping = None

    if specieskey  is not None:

        name_pairs = data[[speciesidkey, specieskey]].drop_duplicates()
        name_counts = name_pairs.groupby(speciesidkey, observed=True)[specieskey].nunique()

        multiple_names = name_counts[name_counts > 1]

        if not multiple_names.empty:
            conflict_examples = name_pairs[name_pairs[speciesidkey].isin(multiple_names.index[:10])].sort_values([speciesidkey, specieskey])
            conflict_examples = conflict_examples.to_dict("records")
            raise ValueError(f"{len(multiple_names)} species identifier(s) are associated with more than one distinct name in {specieskey!r}.\nExamples: {conflict_examples}")

        species_name_mapping = (
            name_pairs
            .drop_duplicates(subset=[speciesidkey])
            .set_index(speciesidkey)[specieskey]
            .to_dict()
        )

    return data, species_name_mapping

def gini_coefficient(values: pd.Series) -> float:
    """
    Compute the normalized Gini coefficient of positive values.

    Returns
    -------
    float
        0 means that values are evenly distributed.
        Values approaching 1 indicate strong concentration.
    """
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array) & (array >= 0)]

    n = array.size
    total = array.sum()

    if n == 0 or total == 0:
        return np.nan

    if n == 1:
        return 0.0

    array = np.sort(array)
    ranks = np.arange(1, n + 1)

    raw_gini = (
        2.0 * np.sum(ranks * array) / (n * total)
        - (n + 1.0) / n
    )

    normalized_gini = raw_gini * n / (n - 1)

    return float(np.clip(normalized_gini, 0.0, 1.0))

def cell_concentration_statistics(counts_by_cell, target_share=0.9):

    n_occupied_cells = len(counts_by_cell)

    sorted_counts = counts_by_cell.sort_values(ascending=False)
    cumulative_share = sorted_counts.cumsum() / sorted_counts.sum()
    n_cells_for_target_share = int(np.searchsorted(cumulative_share.to_numpy(), target_share, side="left") + 1)

    share_cells_for_target_share = n_cells_for_target_share / n_occupied_cells

    proportions = counts_by_cell / counts_by_cell.sum()
    max_cell_record_share = proportions.max()

    results = {
                "n_cells_for_target_share": n_cells_for_target_share,
                "share_cells_for_target_share": share_cells_for_target_share,
                "max_cell_record_share": proportions.max(),
                "spatial_gini": gini_coefficient(counts_by_cell)
              }

    return results

def build_species_statistics(
    data: pd.DataFrame,
    specieskey: str,
    resolution: int = 8,
    spatial_target_share: float = 0.90,
) -> pd.DataFrame:

    h3_column = f"h3_{resolution:02d}"

    records_by_species_cell = (
        data
        .groupby([specieskey, h3_column], observed=True)
        .size()
        .rename("n_records")
        .reset_index()
    )

    cell_area_mapping = {
        cell: h3.cell_area(cell, unit="km^2")
        for cell in records_by_species_cell[h3_column].unique()
    }

    records_by_species_cell["cell_area_km2"] = (
        records_by_species_cell[h3_column].map(cell_area_mapping)
    )

    rows = []

    for species, group in records_by_species_cell.groupby(specieskey, observed=True, sort=False):

        counts_by_cell = group.set_index(h3_column)["n_records"]

        n_records = int(counts_by_cell.sum())
        n_occupied_cells = int(counts_by_cell.size)
        occupied_area_km2 = float(group["cell_area_km2"].sum())

        concentration = cell_concentration_statistics(
            counts_by_cell,
            target_share=spatial_target_share,
        )

        rows.append({
            specieskey: species,
            "n_records": n_records,
            "n_occupied_cells": n_occupied_cells,
            "occupied_h3_area_km2": float(np.round(occupied_area_km2,2)),
            "records_per_occupied_km2": int(n_records / occupied_area_km2),
            f"n_occupied_cells_for_{spatial_target_share:.0%}_records": concentration["n_cells_for_target_share"],
            f"pct_occupied_cells_for_{spatial_target_share:.0%}_records": float(np.round(concentration["share_cells_for_target_share"]*100,2)),
            "max_occupied_cell_record_pct": float(np.round(concentration["max_cell_record_share"]*100,2)),
            "spatial_gini": float(np.round(concentration["spatial_gini"],2)),
        })

    result = pd.DataFrame(rows)
    result = result.sort_values("n_records", ascending=False).reset_index(drop=True)

    return result


def get_top_species(species_statistics: pd.DataFrame, specieskey: str, top_k: int = 20) -> pd.DataFrame:
    total_records = species_statistics["n_records"].sum()
    top_species = species_statistics[[specieskey,"n_records"]].nlargest(top_k, "n_records").copy()
    top_species["percentage_of_total_records"] = ((top_species["n_records"] / total_records) * 100).round(2)
    return top_species.reset_index(drop=True)

def build_dataset_summary(
    data: pd.DataFrame,
    specieskey: str,
    top_k: int = 10,
    low_occurrence_threshold: int = 10,
    dominant_record_share: float = 0.75,
) -> dict:

    species_counts = data[specieskey].value_counts()

    n_species = int(species_counts.size)

    top_k_species = species_counts[:top_k].index.tolist()
    top_percentage = ((species_counts[:top_k] / species_counts.sum())*100).round(2).tolist()
    top_species = dict(zip(top_k_species,top_percentage))

    cumulative_share = (
        species_counts
        .sort_values(ascending=False)
        .cumsum()
        / species_counts.sum()
    )
    n_species_for_dominant_share = int(np.searchsorted(cumulative_share.to_numpy(), dominant_record_share, side="left") + 1)

    result = {
                "n_records": int(len(data)),
                "n_species": n_species,
                "top_k_species": top_species,
                f"n_species_le_{low_occurrence_threshold}_records": int(species_counts.le(low_occurrence_threshold).sum()),
                f"pct_species_le_{low_occurrence_threshold}_records": float(np.round(species_counts.le(low_occurrence_threshold).mean()*100,2)),
#                "low_occurrence_threshold": low_occurrence_threshold,
#                "dominant_record_share": dominant_record_share,
                f"n_species_for_{dominant_record_share:.0%}_records": n_species_for_dominant_share,
                f"pct_species_for_{dominant_record_share:.0%}_records": float(np.round((n_species_for_dominant_share / n_species) * 100, 2)),
                "mean_records_per_species": round(species_counts.mean()),
                "q25_records_per_species": round(species_counts.quantile(0.25)),
                "median_records_per_species": round(species_counts.median()),
                "q75_records_per_species": round(species_counts.quantile(0.75)),
                "max_records_for_one_species": round(species_counts.max()),
            }

    return result

def build_grid_occupancy_summary(
    species_statistics: pd.DataFrame,
    occupancy_thresholds: tuple[int, ...] = (1, 10, 20, 50, 100),
    occupied_cells_column: str = "n_occupied_cells",
) -> pd.DataFrame:
    """
    Summarize species occupancy across H3 cells.

    Parameters
    ----------
    species_statistics
        Species-level statistics table containing one row per species.
    occupancy_thresholds
        Minimum numbers of occupied H3 cells.
    occupied_cells_column
        Name of the column containing the number of occupied H3 cells
        per species.

    Returns
    -------
    pandas.DataFrame
        One row per occupancy threshold, with the number and proportion
        of species occurring in at least that many H3 cells.
    """

    thresholds = sorted(set(occupancy_thresholds))

    occupancy = species_statistics[occupied_cells_column]
    n_species = int(len(occupancy))

    rows = []

    for threshold in thresholds:
        n_species_at_least = int(occupancy.ge(threshold).sum())

        rows.append({
            "minimum_occupied_h3_cells": threshold,
            "n_species": n_species_at_least,
            "pct_species": np.round((n_species_at_least / n_species)*100,2)
        })

    return pd.DataFrame(rows)

def add_species_names(
    dataframe: pd.DataFrame,
    speciesidkey: str,
    specieskey: str,
    species_name_mapping: dict,
    position: int | None = None,
) -> pd.DataFrame:

    result = dataframe.copy()

    names = result[speciesidkey].map(species_name_mapping)

    if position is None:
        position = result.columns.get_loc(speciesidkey) + 1

    result.insert(loc=position, column=specieskey, value=names)

    return result

def compute_dataset_statistics(
    df: pd.DataFrame,
    latkey: str,
    lonkey: str,
    speciesidkey: str,
    output_directory: str,
    specieskey: str | None = None,
    resolution: int = 8,
    low_occurrence_threshold: int = 10,
    dominant_record_share: float = 0.75,
    spatial_target_share: float = 0.90,
    top_k: int = 20,
    occupancy_thresholds: tuple[int, ...] = (1, 10, 20, 50, 100),
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """
    Compute global and species-level occurrence statistics.
    """

    data, species_name_mapping = prepare_occurrence_data(df=df, latkey=latkey, lonkey=lonkey, speciesidkey=speciesidkey, specieskey=specieskey, resolution=resolution)

    species_statistics = build_species_statistics(
        data=data,
        specieskey=speciesidkey,
        resolution=resolution,
        spatial_target_share=spatial_target_share,
    )

    species_statistics = add_species_names(species_statistics, speciesidkey, specieskey, species_name_mapping)

    summary = build_dataset_summary(
        data=data,
        specieskey=speciesidkey,
        top_k=top_k,
        low_occurrence_threshold=low_occurrence_threshold,
        dominant_record_share=dominant_record_share,
    )

    grid_occupancy = build_grid_occupancy_summary(
        species_statistics=species_statistics,
        occupancy_thresholds=occupancy_thresholds,
        occupied_cells_column="n_occupied_cells",
    )

    top_species = get_top_species(species_statistics, specieskey=speciesidkey, top_k=top_k)
    top_species = add_species_names(top_species, speciesidkey, specieskey, species_name_mapping)

    Path(output_directory).mkdir(parents=True, exist_ok=True)

    outputfile = os.path.join(output_directory,"dataset_summary.json")
    with Path(outputfile).open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=4, ensure_ascii=False)

    outputfile = os.path.join(output_directory,"species_statistics.txt")
    species_statistics.to_csv(outputfile, sep="\t", index=False)

    outputfile = os.path.join(output_directory,"top_species.txt")
    top_species.to_csv(outputfile, sep="\t", index=False)

    outputfile = os.path.join(output_directory,"grid_occupancy_summary.txt")
    grid_occupancy.to_csv(outputfile, sep='\t', index=False)

    return pd.DataFrame.from_dict(summary, orient="index", columns=["statistics"]), species_statistics

