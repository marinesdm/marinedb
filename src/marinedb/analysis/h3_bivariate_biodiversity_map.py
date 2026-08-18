#!/usr/bin/python
# coding: utf-8

import os
import argparse
import numpy as np
import pandas as pd
import h3pandas
import geodatasets
import geopandas as gpd
import antimeridian
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.patches import Patch
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

BIVARIATE_PALETTE = {
    # Low richness, low records
    "LL": "#FDD0A2",
    # High richness, low records
    "HL": "#BDD7E7",
    # Low richness, high records
    "LH": "#E6550D",
    # High richness, high records
    "HH": "#3182BD",
}

def _normalized_gini(counts: pd.Series) -> float:
    """
    Compute the normalized Gini coefficient of record counts across species.

    Returns
    -------
    float
        0 indicates a perfectly even distribution of records.
        1 indicates maximal concentration on a single species.

    Notes
    -----
    The usual finite-sample Gini coefficient has a maximum of (S - 1) / S,
    where S is the number of species. Multiplying it by S / (S - 1)
    normalizes the coefficient to the [0, 1] interval.
    """

    values = counts.to_numpy(dtype=float)
    values = values[np.isfinite(values) & (values >= 0)]

    n_species = values.size

    if n_species == 0 or values.sum() == 0:
        return np.nan

    if n_species == 1:
        # There is no inequality among species when only one species exists.
        # However, evenness is not especially informative in that case.
        return 0.0

    values = np.sort(values)
    ranks = np.arange(1, n_species + 1)

    raw_gini = (
        2.0 * np.sum(ranks * values)
        / (n_species * values.sum())
        - (n_species + 1.0) / n_species
    )

    normalized_gini = raw_gini * n_species / (n_species - 1)

    # Protect against tiny floating-point errors.
    return float(np.clip(normalized_gini, 0.0, 1.0))


def _summarize_species_counts(counts, upper_threshold, lower_threshold):

    n_species = len(counts)
    n_records = counts.sum()

    if n_species == 0 or n_records == 0:
        return pd.Series(dtype=float)

    proportions = counts / n_records

    # Basic record-count statistics

    mean_records = counts.mean()
    median_records = counts.median()
    q25_records = counts.quantile(0.25)
    max_records = counts.max()

    # Representation of poorly or sufficiently documented species

    singleton_share = counts.eq(1).mean()
    share_species_ge_threshold = counts.ge(upper_threshold).mean()
    share_species_le_threshold = counts.le(lower_threshold).mean()

    # Concentration among the most frequently recorded species

    max_species_share = proportions.max()
    top_3_species_share = counts.nlargest(min(3, n_species)).sum() / n_records

    # Gini concentration and evenness

    gini_records = _normalized_gini(counts)
    gini_evenness = 1.0 - gini_records

    # Shannon entropy and Pielou evenness

    shannon_entropy = -(proportions * np.log(proportions)).sum()

    if n_species > 1:
        pielou_evenness = shannon_entropy / np.log(n_species)
    else:
        # Pielou's evenness is undefined when
        # richness equals 1 because log(1) = 0.
        pielou_evenness = np.nan

    # Simpson concentration

    simpson_concentration = np.square(proportions).sum()

    # Hill numbers
    #
    # q = 0: observed species richness
    # q = 1: effective number of common species, exp(Shannon entropy)
    # q = 2: effective number of dominant species, inverse Simpson

    hill_q0 = float(n_species)
    hill_q1 = float(np.exp(shannon_entropy))
    hill_q2 = float(1.0 / simpson_concentration)

    if n_species > 1:
        hill_q1_evenness = hill_q1 / n_species
        hill_q2_evenness = hill_q2 / n_species
    else:
        hill_q1_evenness = np.nan
        hill_q2_evenness = np.nan

    statistics = pd.Series({
                            "species_richness": n_species,
                            "n_records": n_records,
                            "mean_records_per_species": mean_records,
                            "median_records_per_species": median_records,
                            "q25_records_per_species": q25_records,
                            "max_records_for_one_species": max_records,

                            "singleton_species_share": singleton_share,
                            "share_species_ge_threshold": share_species_ge_threshold,
                            "share_species_le_threshold": share_species_le_threshold,

                            "max_species_share": max_species_share,
                            "top_3_species_share": top_3_species_share,

                            "gini_records": gini_records,
                            "gini_evenness": gini_evenness,

                            "pielou_evenness": pielou_evenness,
                            "simpson_concentration": simpson_concentration,

                            "hill_q0_species_richness": hill_q0,
                            "hill_q1_effective_species": hill_q1,
                            "hill_q2_effective_species": hill_q2,
                            "hill_q1_evenness": hill_q1_evenness,
                            "hill_q2_evenness": hill_q2_evenness,
                        })

    return statistics

def build_h3_metrics(df, latkey, lonkey, specieskey, resolution=2, lower_occurrence_threshold=10, upper_occurrence_threshold=50):

    """
    Aggregate occurrence records into H3 cells and compute statistics
    describing richness, record volume, and the distribution of records
    across species.

    Parameters
    ----------
    df : pandas.DataFrame
        Input occurrence data.
    latkey : str
        Name of the latitude column.
    lonkey : str
        Name of the longitude column.
    specieskey : str
        Name of the species identifier column.
    resolution : int, default=2
        H3 grid resolution.
    upper_occurrence_threshold : int, default=10
        Minimum number of records required for a species to be considered
        sufficiently represented within a cell.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per occupied H3 cell, with cell-level metrics and geometry.
    """

    indexed = df[[latkey,lonkey,specieskey]].h3.geo_to_h3(
        resolution=resolution,
        lat_col=latkey,
        lng_col=lonkey,
        set_index=False,
    )

    h3_col = f"h3_{resolution:02d}"

    # Number of occurrence per species per cell
    per_species = (
        indexed
        .groupby([h3_col, specieskey], observed=True)
        .size()
        .rename("records_per_species_per_cell")
        .reset_index()
    )

    # Compute cell-level statistics
    cells = (
        per_species
        .groupby(h3_col, observed=True)["records_per_species_per_cell"]
        .apply(
            _summarize_species_counts,
            upper_threshold=upper_occurrence_threshold,
            lower_threshold=lower_occurrence_threshold
        )
        .unstack()
    )

    integer_columns = [
        "species_richness",
        "n_records",
        "max_records_for_one_species",
    ]

    for column in integer_columns:
        cells[column] = cells[column].astype("int64")

    gdf = cells.h3.h3_to_geo_boundary()

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    # Split polygons crossing the antimeridian to prevent
    # them from being rendered across the entire map
    gdf["geometry"] = gdf.geometry.apply(
        lambda geometry: antimeridian.fix_polygon(geometry)
    )

    gdf = gdf.h3.cell_area(unit="km^2")

    gdf["records_per_km2"] = (
        gdf["n_records"] / gdf["h3_cell_area"]
    )

    gdf["h3_id"] = gdf.index.astype(str)

    return gdf

def _robust_score_log01(values, lower_quantile=0.02, upper_quantile=0.98):

    transformed = np.log1p(values.astype(float))

    low = transformed.quantile(lower_quantile)
    high = transformed.quantile(upper_quantile)

    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return pd.Series(0.5, index=values.index)

    return (transformed.clip(lower=low, upper=high) - low) / (high - low)


def classify_bivariate(gdf, cell_metric="mean_records_per_species", classification_quantile=0.50, richness_threshold=None, second_metric_threshold=None):

    result = gdf.copy()

    if richness_threshold is None:
        richness_threshold = float(
            result["species_richness"].quantile(classification_quantile)
        )

    if second_metric_threshold is None:
        second_metric_threshold = float(
            result[cell_metric].quantile(classification_quantile)
        )

    high_richness = result["species_richness"] > richness_threshold
    high_effort = result[cell_metric] > second_metric_threshold

    # Discrete scores
    result["bivariate_class"] = np.select(
        condlist=[
              (~high_richness) & (~high_effort),
              high_richness & (~high_effort),
              (~high_richness) & high_effort,
              high_richness & high_effort,
        ],
        choicelist=["LL", "HL", "LH", "HH"],
        default="LL",
    )

    # Continuous scores

    result["richness_score_log01"] = _robust_score_log01(
        result["species_richness"]
    )
    result["effort_score_log01"] = _robust_score_log01(
        result[cell_metric]
    )

    ## Geometric mean: penalize cells with a low
    ## score in either of the two dimensions.
    result["joint_score"] = np.sqrt(
        result["richness_score_log01"]
        * result["effort_score_log01"]
    )

    thresholds = {
        "richness_threshold": richness_threshold,
        "second_metric_threshold": second_metric_threshold,
    }

    return result, thresholds

def format_threshold(value):

    if float(value).is_integer():
        return f"{int(value):,}"

    return f"{value:.2f}"

def plot_bivariate_world(gdf, richness_threshold, cell_metric_threshold, cell_metric="n_records", boundary_metric="share_species_le_threshold", boundary_metric_threshold=None, title="Species Richness and Mean Records per Species", lower_occurrence_threshold=10, palette=None, outputdir=None, resolution=3):

    # pielou_evenness : 0.8
    # share_species_le_threshold : 0.75

    if palette is None:
        palette = BIVARIATE_PALETTE

    required_classes = {"LL", "HL", "LH", "HH"}

    if not required_classes.issubset(palette):
        raise ValueError

    if cell_metric == "mean_records_per_species":
        cell_metric_label="Mean records per species"
    elif cell_metric == "median_records_per_species":
       cell_metric_label="Median records per species"
    elif cell_metric == "n_records":
        cell_metric_label="Number of records"

    if cell_metric == "n_records":

        if boundary_metric == "pielou_evenness":

            if boundary_metric_threshold is None:
                boundary_metric_threshold = 0.75

            boundary_legend = "Low record evenness"

            eligible = (
                gdf["species_richness"].ge(5)
                & gdf["n_records"].ge(20)
                & gdf["pielou_evenness"].notna()
            )
            low_evenness = (eligible & gdf["pielou_evenness"].lt(boundary_metric_threshold))

        elif boundary_metric == "share_species_le_threshold":

            if boundary_metric_threshold is None:
                boundary_metric_threshold = 0.8

            boundary_legend = (
                 "High-volume cells\n"
                f"≥{boundary_metric_threshold:.0%} species with "
                f"≤{lower_occurrence_threshold} records"
            )

            eligible = gdf["bivariate_class"].isin(['HH','LH'])
            low_species_representation = eligible & gdf["share_species_le_threshold"].ge(boundary_metric_threshold)

    world = gpd.read_file(geodatasets.get_path("naturalearth.land"))

    # Equal Earth
    target_crs = "EPSG:8857"

    world_projected = world.to_crs(target_crs)
    cells_projected = gdf.to_crs(target_crs)

    fig, ax = plt.subplots(figsize=(17, 9))

    # Reserve space on the left for the legends
    fig.subplots_adjust(left=0.16, right=0.99, bottom=0.06, top=0.98)

    land_color = "#E8E8E8"
    ocean_color = "#FFFFFF"

    fig.patch.set_facecolor(ocean_color)
    ax.set_facecolor(ocean_color)

    # Land areas without observations
    world_projected.plot(
        ax=ax,
        color=land_color,
        edgecolor="#B8B8B8",
        linewidth=0.5,
        zorder=1
    )

    cell_colors = cells_projected["bivariate_class"].map(palette)

    cells_projected.plot(
        ax=ax,
        color=cell_colors,
        edgecolor="white",
        linewidth=0.1,
        zorder=2,
    )

    if cell_metric == "n_records":

        if boundary_metric == "pielou_evenness":
            cells_projected.loc[low_evenness].boundary.plot(
                ax=ax,
                color="#3A3A3A",
                linewidth=0.9,
                zorder=3,
            )
        elif boundary_metric == "share_species_le_threshold":
            cells_projected.loc[low_species_representation].boundary.plot(
                ax=ax,
                color="#4A4A4A",
                linewidth=1.2,
                zorder=3,
            )

    ax.set_axis_off()

    bounds = world_projected.total_bounds
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])

    # Legend block position

    legend_left = 0.12 # 0.14
    legend_bottom = 0.137
    legend_width = 0.085 * 0.8
    legend_height = 0.16 * 0.8

    legend_ax = fig.add_axes([legend_left, legend_bottom, legend_width, legend_height])

    # Bottom row: low number of records
    # Top row: high number of records
    legend_codes = np.array([
        ["LL", "HL"],
        ["LH", "HH"],
    ])

    legend_image = np.array([
        [to_rgba(palette[code]) for code in row]
        for row in legend_codes
    ])

    legend_ax.imshow(
        legend_image,
        origin="lower",
        interpolation="nearest",
    )

    legend_ax.set_xticks(
        [0, 1],
        labels=["Low", "High"],
        fontsize=8,
    )

    legend_ax.xaxis.tick_top()
    legend_ax.tick_params(
        axis="x",
        top=True,
        labeltop=True,
        bottom=False,
        labelbottom=False,
        length=0,
    )

    legend_ax.set_yticks(
        [0, 1],
        labels=["Low", "High"],
        fontsize=8,
    )

    richness_threshold_label = format_threshold(richness_threshold)
    cell_metric_threshold_label = format_threshold(cell_metric_threshold)

    legend_ax.plot(
        [0.5, 0.5],
        [1.0, 1.03],
        transform=legend_ax.transAxes,
        color="#555555",
        linewidth=0.8,
        clip_on=False,
    )

    legend_ax.annotate(
        richness_threshold_label,
        xy=(0.5, 1.0),
        xycoords=legend_ax.transAxes,
        xytext=(0, 7),
        textcoords="offset points",
        fontsize=7,
        ha="center",
        va="bottom",
        annotation_clip=False,
    )

    legend_ax.plot(
        [0.0, -0.03],
        [0.5, 0.5],
        transform=legend_ax.transAxes,
        color="#555555",
        linewidth=0.8,
        clip_on=False,
    )

    legend_ax.annotate(
        cell_metric_threshold_label,
        xy=(0.0, 0.5),
        xycoords=legend_ax.transAxes,
        xytext=(-8, 0),
        textcoords="offset points",
        fontsize=7,
        ha="right",
        va="center",
        annotation_clip=False,
    )

    legend_ax.set_xlabel(
        "Species richness",
        fontsize=9,
        labelpad=8,
    )

    legend_ax.xaxis.set_label_position("top")

    legend_ax.set_ylabel(
        cell_metric_label,
        fontsize=9,
        labelpad=6,
    )

    legend_ax.tick_params(length=0)

    for spine in legend_ax.spines.values():
        spine.set_color("#555555")
        spine.set_linewidth(0.7)

    if cell_metric == "n_records":

        boundary_patch = Patch(
            facecolor="white",
            edgecolor="#4A4A4A",
            linewidth=1.2,
            label=boundary_legend,
        )

        boundary_legend_obj = fig.legend(
            handles=[boundary_patch],
            loc="lower left",
            bbox_to_anchor=(legend_left - 0.0035, legend_bottom - 0.0125 - 0.03), # 0.05
#            bbox_to_anchor=(legend_left + legend_width + 0.002, legend_bottom - 0.0125),
            bbox_transform=fig.transFigure,
            frameon=False,
            fontsize=8.5,
            handlelength=1.2,
            handleheight=1.0,
            handletextpad=0.6,
            borderaxespad=0,
        )

#        x_rect = 0.02
#        y_rect = 1.10
#        rect_w = 0.10
#        rect_h = 0.10
#
#        evenness_box = Rectangle(
#            (x_rect, y_rect),
#            rect_w,
#            rect_h,
#            transform=legend_ax.transAxes,
#            facecolor="white",
#            edgecolor="#3A3A3A",
#            linewidth=1.4,
#            clip_on=False,
#        )
#
#        legend_ax.add_patch(evenness_box)
#
#        legend_ax.text(
#            x_rect + rect_w + 0.05,
#            y_rect + rect_h / 2,
#            boundary_legend,
#            transform=legend_ax.transAxes,
#            fontsize=9,
#            ha="left",
#            va="center",
#            clip_on=False
#        )

#    fig.tight_layout()

    if outputdir is not None:
        print("Saving figure...")
        outputfile = os.path.join(outputdir, f'h3_bivariate_map_res{resolution}_1.png')
        fig.savefig(
            outputfile,
            dpi=300,
            bbox_inches="tight",
            facecolor=ocean_color,
        )
        print(f"Figure saved to: {os.path.abspath(outputfile)}")

    return fig, ax

if __name__=='__main__':

    parser = argparse.ArgumentParser(description='Aggregate biodiversity records into H3 cells and generate a bivariate world map combining species richness an number of records.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputfile_path', type=str, help='Path to the input delimited text file containing latitude, longitude, and species identifier columns.')
    parser.add_argument('--latitude-column', '--lat', type=str, help='Name of the column containing latitude values in decimal degrees.', required=True)
    parser.add_argument('--longitude-column', '--lon', type=str, help='Name of the column containing longitude values in decimal degrees.', required=True)
    parser.add_argument('--species-column', '--species', type=str, help='Name of the column containing the species identifier.', required=True)
    parser.add_argument('--delimiter', type=str, help='Field delimiter used in the input file. Enclose special characters or delimiters containing spaces in quotation marks', default='\t')
    # Warning: delimiter must be enclosed in quotation marks
    parser.add_argument('--resolution', type=int, metavar="0-15", help='H3 grid resolution. Higher values produce smaller cells and a more detailed map, but require more computation.', default=3)
    parser.add_argument('--lower-occurrence-threshold', type=int, help="Record-count threshold used to identify poorly represented species. A species with this number of records or fewer within an H3 cell is considered underrepresented.", default=10)
    parser.add_argument('--upper-occurrence-threshold', type=int, help="Record-count threshold used to identify well-represented species. A species with at least this number of records within an H3 cell is considered sufficiently represented.", default=50)
    parser.add_argument('--cell-metric', type=str, choices = ["n_records", "mean_records_per_species", "median_records_per_species"], help="Cell-level metric combined with species richness in the bivariate classification.", default='n_records')
    parser.add_argument('--classification-quantile', type=float, help='Quantile used to separate low and high values when explicit richness or effort thresholds are not provided. A value of 0.5 uses the median.', default=0.5)
    parser.add_argument('--richness-threshold', type=float, help='Explicit species-richness threshold used to classify cells as low or high richness. When omitted, the threshold is derived from --classification-quantile.', default=None)
    parser.add_argument('--second-metric-threshold', type=float, help='Explicit threshold used to classify cells as low or high. When omitted, the threshold is derived from --classification-quantile.', default=None)
    parser.add_argument('--boundary-metric', type=str, choices = ["species_representation", "record_evenness"], help="Criterion used to highlight H3 cells with a dark boundary. 'species_representation' flags cells where a large share of species has few records; 'record_evenness' flags cells where records are unevenly distributed across species.", default="species_representation")
    parser.add_argument('--boundary-metric-threshold', type=float, help="Threshold used to determine which H3 cells are highlighted with a boundary. Its interpretation depends on --boundary-metric. For 'species_representation', it is the minimum share of poorly represented species required to flag a cell. For 'record_evenness', it is the maximum Pielou evenness below which a cell is flagged.", default=None)
#    parser.add_argument('--title', type=str, help="Title displayed above the map.", default="Species Richness and Mean Records per Species")
    parser.add_argument('--palette', nargs=4, type=str, metavar=("LL", "HL", "LH", "HH"), help="Four colors assigned respectively to the LL, HL, LH, and HH: low richness/low number of records, high richness/low number of records, low richness/high number of records, and high richness/high number of records. Colors may be hexadecimal codes or Matplotlib color names.", default=None)
#    parser.add_argument('--output-path', '--output', type=str, help="Path of the output image file. The file format is inferred from its extension, for example '.png', '.pdf', or '.svg'. If omitted, the map is displayed without being saved.", default=None)
    parser.add_argument('--output-directory', '--outputdir', type=str, help="Directory path of the output image file. If omitted, the map is displayed without being saved.", default=None)
    args = parser.parse_args()

    file = args.inputfile_path
    sep = args.delimiter
    latkey = args.latitude_column
    lonkey = args.longitude_column
    specieskey = args.species_column
    params = {
               'resolution': args.resolution,
               'lower_occurrence_threshold': args.lower_occurrence_threshold,
               'upper_occurrence_threshold': args.upper_occurrence_threshold
             }

    df = pd.read_csv(file, sep=sep, usecols=[latkey, lonkey, specieskey], dtype={latkey:'float', lonkey:'float'})

    gdf = build_h3_metrics(df, latkey, lonkey, specieskey, **params)

    params = {
              'cell_metric': args.cell_metric,
              'classification_quantile': args.classification_quantile,
              'richness_threshold': args.richness_threshold,
              'second_metric_threshold': args.second_metric_threshold
             }

    result, thresholds = classify_bivariate(gdf, **params)

    palette = args.palette
    if palette:
        palette = dict(zip(["LL", "HL", "LH", "HH"], args.palette))

    if args.boundary_metric == "species_representation":
        boundary_metric = "share_species_le_threshold"
    elif args.boundary_metric == "record_evenness":
        boundary_metric = "pielou_evenness"

    params = {
              'richness_threshold': thresholds["richness_threshold"],
              'cell_metric_threshold': thresholds["second_metric_threshold"],
              'cell_metric': args.cell_metric,
              'boundary_metric': boundary_metric,
              'boundary_metric_threshold': args.boundary_metric_threshold,
              'palette': palette,
              'lower_occurrence_threshold': args.lower_occurrence_threshold,
              'outputdir': args.output_directory,
              'resolution': args.resolution
             }

    fig, ax = plot_bivariate_world(result, **params)

    plt.show()
