#!/usr/bin/python
# coding: utf-8

import os
import json
import numpy as np
import pandas as pd
import h3
import h3pandas
from pathlib import Path

def prepare_occurrence_data(df: pd.DataFrame, latkey: str, lonkey: str, resolution: int = 8): # speciesidkey: str, specieskey: str = None

    data = df.h3.geo_to_h3(
        resolution=resolution,
        lat_col=latkey,
        lng_col=lonkey,
        set_index=False,
    )

    return data

def gini_coefficient(counts: pd.Series) -> float:
    """
    Compute the normalized Gini coefficient of positive values.

    Returns
    -------
    float
        0 means that values are evenly distributed.
        Values approaching 1 indicate strong concentration.
    """
    array = np.asarray(counts, dtype=float)
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

def spatial_pielou_evenness(counts):

    counts = np.asarray(counts, dtype=float)
    counts = counts[np.isfinite(counts) & (counts > 0)]

    n_cells = counts.size

    if n_cells < 2:
        return np.nan

    proportions = counts / counts.sum()

    shannon_entropy = -np.sum(proportions * np.log(proportions))

    return shannon_entropy / np.log(n_cells)

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
                "spatial_gini": gini_coefficient(counts_by_cell),
                "spatial_pielou": spatial_pielou_evenness(counts_by_cell)
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
            "spatial_pielou": float(np.round(concentration["spatial_pielou"],2))
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
    sciname_mapping: dict,
    basisOfRecord_mapping: dict,
    databasekey: str,
    specieskey: str,
    genuskey: str,
    familykey: str,
    orderkey: str,
    classkey: str,
    phylumkey: str,
    kingdomkey: str,
    occ10key: str,
    occ50key: str,
    occ100key: str,
    yearkey: str,
    monthkey: str,
    absencekey: str,
    basisofrecordkey: str,
    top_k: int = 10,
    low_occurrence_threshold: int = 10,
    dominant_record_share: float = 0.75,
) -> dict:

    N = len(data)

    species_counts = data[specieskey].value_counts()

    n_species = int(species_counts.size)
    n_genus = data[genuskey].nunique()
    n_family = data[familykey].nunique()
    n_order = data[orderkey].nunique()
    n_class = data[classkey].nunique()
    phylum = data[phylumkey].unique()
    n_phylum = len(phylum)
    kingdom = data[kingdomkey].unique()
    n_kingdom = len(kingdom)

    top_k_species = species_counts[:top_k].index.tolist()
    top_k_species = [sciname_mapping[str(spe)]['scientificname'] for spe in top_k_species]
    top_percentage = ((species_counts[:top_k] / species_counts.sum())*100).round(2).tolist()
    top_species = dict(zip(top_k_species,top_percentage))

    cumulative_share = (
        species_counts
        .sort_values(ascending=False)
        .cumsum()
        / species_counts.sum()
    )
    n_species_for_dominant_share = int(np.searchsorted(cumulative_share.to_numpy(), dominant_record_share, side="left") + 1)

    kingdom_stats = {}
    for k in kingdom:
        is_kingdom = (data[kingdomkey] == k)
        kingdom_stats[sciname_mapping[str(k)]['scientificname']] = {}
        n_species_k = data.loc[is_kingdom, specieskey].nunique()
        n_genus_k = data.loc[is_kingdom, genuskey].nunique()
        n_family_k = data.loc[is_kingdom, familykey].nunique()
        n_order_k = data.loc[is_kingdom, orderkey].nunique()
        n_class_k = data.loc[is_kingdom, classkey].nunique()
        n_phylum_k = data.loc[is_kingdom, phylumkey].nunique()
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["n_species"] = n_species_k
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["pct_species"] = round((n_species_k / n_species) * 100, 2)
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["n_genus"] = n_genus_k
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["pct_genus"] = round((n_genus_k / n_genus) * 100, 2)
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["n_family"] = n_family_k
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["pct_family"] = round((n_family_k / n_family) * 100, 2)
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["n_order"] = n_order_k
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["pct_order"] = round((n_order_k / n_order) * 100, 2)
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["n_class"] = n_class_k
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["pct_class"] = round((n_class_k / n_class) * 100, 2)
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["n_phylum"] = n_phylum_k
        kingdom_stats[sciname_mapping[str(k)]['scientificname']]["pct_phylum"] = round((n_phylum_k / n_phylum) * 100, 2)

    phylum_stats = {}
    for p in phylum:
        if not pd.isnull(p):
            n_phylum_p = (data[phylumkey] == p).sum()
            pct_phylum_p = round((n_phylum_p/N)*100,2)
            kingdom = list(data.loc[data[phylumkey] == p, kingdomkey].unique())
            assert len(kingdom) == 1
            phylum_stats[sciname_mapping[str(p)]['scientificname']] = {}
            phylum_stats[sciname_mapping[str(p)]['scientificname']]["kingdom"] = sciname_mapping[str(kingdom[0])]['scientificname']
            phylum_stats[sciname_mapping[str(p)]['scientificname']]["stat"] = f"{n_phylum_p} ({pct_phylum_p}%)"
        else:
            phylum_stats["no_phylum"] = {}
            n_phylum_p = data[phylumkey].isna().sum()
            pct_phylum_p = round((n_phylum_p/N)*100,2)
            kingdom = list(data.loc[data[phylumkey].isna(), kingdomkey].unique())
            kingdom = ', '.join([sciname_mapping[str(k)]['scientificname'] for k in kingdom])
            phylum_stats["no_phylum"]["kingdom"] = kingdom
            phylum_stats["no_phylum"]["stat"] = f"{n_phylum_p} ({pct_phylum_p}%)"

    n_10 = int(data.loc[data[occ10key], specieskey].nunique())
    pct_10 = round((n_10/n_species)*100, 2)
    n_50 = int(data.loc[data[occ50key], specieskey].nunique())
    pct_50 = round((n_50/n_species)*100, 2)
    n_100 = int(data.loc[data[occ100key], specieskey].nunique())
    pct_100 = round((n_50/n_species)*100, 2)

    n_absence = data[absencekey].sum()
    pct_absence = round((n_absence/N)*100, 2)
    species_absence_counts = data.loc[data[absencekey], specieskey].value_counts()
    n_absence_species = int(species_absence_counts.size)
    pct_absence_species = round((n_absence_species/n_species)*100, 2)
    n_absence_species_10 = int((species_absence_counts >= 10).sum())
    pct_absence_species_10 = round((n_absence_species_10 / n_absence_species)*100, 2)

    database_stats = data[databasekey].value_counts()
    database_stats = database_stats.reset_index()
    database_stats['pct'] = ((database_stats['count'] / N)*100).round(2)

    year_min = data[yearkey].min()
    year_max = data[yearkey].max()
    year_75 = data[yearkey].quantile([0.25])[0.25]
    year_90 = data[yearkey].quantile([0.1])[0.1]

    data[monthkey] = data[monthkey].astype('string')
    month_df = data[monthkey].value_counts().reset_index()
    month_df['pct_with_month'] = ((month_df['count']/(month_df['count'].sum()))*100).round(2)
    month_stats = {k: {'count': int(l), 'pct_with_month': float(m)} for k,l,m in month_df.itertuples(index=False)}
    n_month_unknown = int(data[monthkey].isna().sum())
    month_stats['Unknown'] = {'count': n_month_unknown, 'pct_total': round((n_month_unknown/N)*100, 2)}

    basisofrecord_counts = data[basisofrecordkey].value_counts()
    basisofrecord_counts = basisofrecord_counts.reset_index()
    basisofrecord_counts[basisofrecordkey] = basisofrecord_counts[basisofrecordkey].replace(basisOfRecord_mapping)
    basisofrecord_stats = basisofrecord_counts.copy()
    basisofrecord_stats['pct'] = ((basisofrecord_stats['count'] / len(data))*100).round(2)

    result = {
                "n_records": N,
                "absence": {
                            "records": f"{n_absence} ({pct_absence}%)",
                            "species": f"{n_absence_species} ({pct_absence_species}%)",
                            "species_above_10_absences": f"{n_absence_species_10} ({pct_absence_species_10}%)"
                           },
                "n_kingdom": n_kingdom,
                "n_phylum": n_phylum,
                "n_class": n_class,
                "n_order": n_order,
                "n_family": n_family,
                "n_genus": n_genus,
                "n_species": n_species,
                "top_k_species": top_species,
                f"n_species_le_{low_occurrence_threshold}_records": int(species_counts.le(low_occurrence_threshold).sum()),
                f"pct_species_le_{low_occurrence_threshold}_records": float(np.round(species_counts.le(low_occurrence_threshold).mean()*100,2)),
                f"n_species_for_{dominant_record_share:.0%}_records": n_species_for_dominant_share,
                f"pct_species_for_{dominant_record_share:.0%}_records": float(np.round((n_species_for_dominant_share / n_species) * 100, 2)),
                "mean_records_per_species": round(species_counts.mean()),
                "q25_records_per_species": round(species_counts.quantile(0.25)),
                "median_records_per_species": round(species_counts.median()),
                "q75_records_per_species": round(species_counts.quantile(0.75)),
                "max_records_for_one_species": round(species_counts.max()),
                "10 occ": f"{n_10} ({pct_10}%)",
                "50 occ": f"{n_50} ({pct_50}%)",
                "100 occ": f"{n_100} ({pct_100}%)",
                "year": {"min": int(year_min), "max": int(year_max), "year_75%_above": int(year_75), "year_90%_above": int(year_90)},
            }

    return result, kingdom_stats, phylum_stats, database_stats, month_stats, basisofrecord_stats

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
    sciname_mapping: dict,
    position: int | None = None,
) -> pd.DataFrame:

    result = dataframe.copy()
    names = result[speciesidkey].astype('str').map(lambda x: sciname_mapping[x]['scientificname'])

    if position is None:
        position = result.columns.get_loc(speciesidkey) + 1

    result.insert(loc=position, column='species_name', value=names)

    return result

def compute_dataset_statistics(
    df: pd.DataFrame,
    output_directory: str,
    sciname_mapping_file: str,
    basisOfRecord_mapping_file,
    latkey: str = 'latitude',
    lonkey: str = 'longitude',
    specieskey: str = 'species',
    genuskey: str = 'genus',
    familykey: str = 'family',
    orderkey: str = 'order',
    classkey: str = 'class',
    phylumkey: str = 'phylum',
    kingdomkey: str = 'kingdom',
    occ10key: str = 'flag_species_above_10',
    occ50key: str = 'flag_species_above_50',
    occ100key: str = 'flag_species_above_100',
    yearkey: str = 'year',
    monthkey: str = 'month',
    absencekey: str = 'flag_absence',
    databasekey: str = 'database',
    basisofrecordkey: str = 'basisOfRecord',
    resolution: int = 8,
    low_occurrence_threshold: int = 10,
    dominant_record_share: float = 0.75,
    spatial_target_share: float = 0.90,
    top_k: int = 10,
    occupancy_thresholds: tuple[int, ...] = (1, 10, 20, 50, 100),
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """
    Compute global and species-level occurrence statistics.
    """

    with open(sciname_mapping_file,'r') as f:
        sciname_mapping = json.load(f)

    with open(basisOfRecord_mapping_file, 'r') as f:
        basisOfRecord_mapping = json.load(f)

    data = prepare_occurrence_data(df=df, latkey=latkey, lonkey=lonkey, resolution=resolution)

    species_statistics = build_species_statistics(
        data=data,
        specieskey=specieskey,
        resolution=resolution,
        spatial_target_share=spatial_target_share,
    )

    species_statistics = add_species_names(species_statistics, specieskey, sciname_mapping)

    summary, kingdom_stats, phylum_stats, database_stats, month_stats, basisofrecord_stats = build_dataset_summary(
        data=data,
        sciname_mapping=sciname_mapping,
        basisOfRecord_mapping=basisOfRecord_mapping,
        specieskey=specieskey,
        genuskey=genuskey,
        familykey=familykey,
        orderkey=orderkey,
        classkey=classkey,
        phylumkey=phylumkey,
        kingdomkey=kingdomkey,
        occ10key=occ10key,
        occ50key=occ50key,
        occ100key=occ100key,
        yearkey=yearkey,
        monthkey=monthkey,
        absencekey=absencekey,
        databasekey=databasekey,
        basisofrecordkey=basisofrecordkey,
        top_k=top_k,
        low_occurrence_threshold=low_occurrence_threshold,
        dominant_record_share=dominant_record_share,
    )

    grid_occupancy = build_grid_occupancy_summary(
        species_statistics=species_statistics,
        occupancy_thresholds=occupancy_thresholds,
        occupied_cells_column="n_occupied_cells",
    )

    top_species = get_top_species(species_statistics, specieskey=specieskey, top_k=top_k)
    top_species = add_species_names(top_species, specieskey, sciname_mapping)

    Path(output_directory).mkdir(parents=True, exist_ok=True)

    outputfile = os.path.join(output_directory,"dataset_summary.json")
    with Path(outputfile).open("w", encoding="utf-8") as stream:
        print(f'INFO:Save {outputfile}')
        json.dump(summary, stream, indent=4, ensure_ascii=False)

    outputfile = os.path.join(output_directory,"kingdom_summary.json")
    with Path(outputfile).open("w", encoding="utf-8") as stream:
        print(f'INFO:Save {outputfile}')
        json.dump(kingdom_stats, stream, indent=4, ensure_ascii=False)

    outputfile = os.path.join(output_directory,"phylum_summary.json")
    with Path(outputfile).open("w", encoding="utf-8") as stream:
        print(f'INFO:Save {outputfile}')
        json.dump(phylum_stats, stream, indent=4, ensure_ascii=False)

    outputfile = os.path.join(output_directory,"month_summary.json")
    with Path(outputfile).open("w", encoding="utf-8") as stream:
        print(f'INFO:Save {outputfile}')
        json.dump(month_stats, stream, indent=4, ensure_ascii=False)

    outputfile = os.path.join(output_directory,"origin_database_summary.txt")
    print(f'INFO:Save {outputfile}')
    database_stats.to_csv(outputfile, sep="\t", index=False)

    outputfile = os.path.join(output_directory,"species_summary.txt")
    print(f'INFO:Save {outputfile}')
    species_statistics.to_csv(outputfile, sep="\t", index=False)

    outputfile = os.path.join(output_directory,"top_species_summary.txt")
    print(f'INFO:Save {outputfile}')
    top_species.to_csv(outputfile, sep="\t", index=False)

    outputfile = os.path.join(output_directory,"grid_occupancy_summary.txt")
    print(f'INFO:Save {outputfile}')
    grid_occupancy.to_csv(outputfile, sep='\t', index=False)

    outputfile = os.path.join(output_directory,"basis_of_record_summary.txt")
    print(f'INFO:Save {outputfile}')
    basisofrecord_stats.to_csv(outputfile, sep='\t', index=False)

    return pd.DataFrame.from_dict(summary, orient="index", columns=["statistics"]), species_statistics

