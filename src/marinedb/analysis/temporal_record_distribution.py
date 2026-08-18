#!/usr/bin/python
# coding: utf-8

import os
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import StrMethodFormatter
from matplotlib.colors import PowerNorm
from matplotlib.colors import TwoSlopeNorm
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

def plot_records_by_year(df, year_column=None, date_column=None, outputdir=None):

    if year_column is None:
        if date_column is None:
            raise
        else:
            year = df[date_column].str.split('-').str[0].astype('int')
    else:
        year = df[year_column].astype('int')

    year = year.apply(lambda year: "≤1950" if year <= 1950 else year)

    records_per_year = year.astype('str').value_counts()
    years_after_1950 = sorted(
        year
        for year in records_per_year.index
        if year != "≤1950"
    )
    ordered_categories = ["≤1950"] + years_after_1950
    records_per_year = records_per_year.reindex(ordered_categories)

    fig, ax = plt.subplots(figsize=(12, 6))

    x_positions = range(len(records_per_year))

    text_color = "#2F4358"
    colors = [
        "#4E6A86" if label == "<=1950" else "#16324F"
        for label in records_per_year.index
    ] #2C425E #6F8FAF

    ax.bar(
        x_positions,
        records_per_year.values,
        width=0.98,
#        color= "#5B7C99",
        color=colors,
        edgecolor="white",
        linewidth=0.4
    )

    ax.margins(x=0.01)

    ax.set_xticks(x_positions)
    ax.set_xticklabels(
        records_per_year.index,
        rotation=90,
        ha="center"
    )

    ax.set_xlabel("Year", color=text_color, fontweight="medium", fontsize=11, labelpad=6)
    ax.set_ylabel("Number of records", color=text_color, fontweight="medium", fontsize=11, labelpad=6)

    ax.tick_params(axis="both", colors=text_color, labelsize=9)

    ax.ticklabel_format(
        axis="y",
        style="plain",
        useOffset=False
    )

    ax.yaxis.set_major_formatter(
        StrMethodFormatter("{x:,.0f}")
    )

    ax.spines["left"].set_color(text_color)
    ax.spines["bottom"].set_color(text_color)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.4)

    plt.tight_layout()

    if outputdir is not None:
        outputfile = os.path.join(outputdir,"yearly_record_distribution.png")
        print(f'INFO:save {outputfile}')
        fig.savefig(
            outputfile,
            dpi=300,
            bbox_inches="tight"
        )

    plt.show()

def plot_records_by_month(df, month_column=None, date_column=None, outputdir=None):

    if month_column is None:
        if date_column is None:
            raise
        else:
            month = df[date_column].str.split('-').str[1].astype('Int64')
    else:
        month = df[month_column].astype('Int64')

    month = month[~month.isna()]
    records_per_month = month.value_counts().sort_index()

    month_labels = [
        "Jan.", "Feb.", "Mar.", "Apr.",
        "May", "Jun.", "Jul.", "Aug.",
        "Sep.", "Oct.", "Nov.", "Dec."
    ]

    text_color = "#2F4358"
#    season_colors = {
#        "winter": "#16324F",
#        "spring": "#4E6A86",
#        "summer": "#5E88A8",
#        "autumn": "#24507F",
#    }
#    month_colors = [
#        season_colors["winter"],  # Jan.
#        season_colors["winter"],  # Feb.
#        season_colors["spring"],  # Mar.
#        season_colors["spring"],  # Apr.
#        season_colors["spring"],  # May
#        season_colors["summer"],  # Jun.
#        season_colors["summer"],  # Jul.
#        season_colors["summer"],  # Aug.
#        season_colors["autumn"],  # Sep.
#        season_colors["autumn"],  # Oct.
#        season_colors["autumn"],  # Nov.
#        season_colors["winter"],  # Dec.
#    ]

    fig, ax = plt.subplots(figsize=(12, 6))

    x_positions = range(len(records_per_month))
    ax.bar(
        x_positions,
        records_per_month.values,
        width=0.98,
        color="#4E6A86", #24507F
#        color=month_colors,
        edgecolor="white",
        linewidth=0.4
    )

    ax.margins(x=0.01)

    ax.set_xticks(range(12))
    ax.set_xticklabels(month_labels)

    ax.set_xlabel("Month", color=text_color, fontweight="medium", fontsize=11, labelpad=6)
    ax.set_ylabel("Number of records", color=text_color, fontweight="medium", fontsize=11, labelpad=6)

    ax.tick_params(axis="both", colors=text_color, labelsize=9)

    ax.ticklabel_format(
        axis="y",
        style="plain",
        useOffset=False
    )

    ax.yaxis.set_major_formatter(
        StrMethodFormatter("{x:,.0f}")
    )

    ax.spines["left"].set_color(text_color)
    ax.spines["bottom"].set_color(text_color)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.4)

    plt.tight_layout()

    if outputdir is not None:
        outputfile = os.path.join(outputdir,"monthly_record_distribution.png")
        print(f'INFO:save {outputfile}')
        fig.savefig(
            outputfile,
            dpi=300,
            bbox_inches="tight"
        )

    plt.show()

def plot_record_counts_by_month_year(df, year_column=None, month_column=None, date_column=None, outputdir=None):

    data = df.copy()

    if year_column is None:
        if date_column is None:
            raise
        else:
            data['year'] = data[date_column].str.split('-').str[0].astype('int')
            year_column = 'year'
    else:
        data[year_column] = data[year_column].astype('int')

    data[year_column] = data[year_column].apply(lambda y: "≤1950" if y <= 1950 else y)

    if month_column is None:
        if date_column is None:
            raise
        else:
            data['month'] = data[date_column].str.split('-').str[1].astype('Int64')
            month_column = 'month'
    else:
        data[month_column] = data[month_column].astype('Int64')

    data[month_column] = data[month_column].fillna(13).astype(int)

    heatmap_data = (
        data
        .groupby([year_column, month_column])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=range(1, 14), fill_value=0)
    )

    years_after_1950 = sorted([y for y in heatmap_data.index if y != "≤1950"])
    ordered_index = ["≤1950"] + years_after_1950
    heatmap_data = heatmap_data.reindex(ordered_index, fill_value=0)

    heatmap_plot = heatmap_data.copy()
    heatmap_plot[14] = heatmap_plot[13]
    heatmap_plot[13] = np.nan
    heatmap_plot = heatmap_plot[[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]]

    plot_values = np.ma.masked_invalid(heatmap_plot.values)

    month_labels = [
        "Jan.", "Feb.", "Mar.", "Apr.",
        "May", "Jun.", "Jul.", "Aug.",
        "Sep.", "Oct.", "Nov.", "Dec.",
        "Unk."
    ]

#    cmap = LinearSegmentedColormap.from_list(
#        "custom_blues",
#        ["#F7FAFC", "#D9E6F2", "#8FAFCC", "#4E6A86", "#24507F", "#16324F"]
#    )

    cmap = plt.get_cmap("YlGnBu")

#    cmap.set_bad("#F5F7FA")
    norm = PowerNorm(gamma=0.5) # 0.8
    text_color = "#2F4358"

    n_rows = len(heatmap_data)
#    fig_height = min(max(6.0, 0.24 * n_rows), 13)
#    fig_height = min(max(5.5, 0.22 * n_rows), 12)
    fig_height = min(max(4.2, 0.14 * n_rows), 8.5)
    fig, ax = plt.subplots(figsize=(11.5, fig_height))

    spacer_width = 0.2

    x_edges = np.array(list(range(13)) + [12 + spacer_width, 13 + spacer_width])
    y_edges = np.arange(n_rows + 1)

    ax.axvspan(
        x_edges[-2], x_edges[-1],
        color="#F3F6F9",
        zorder=0
    )

    mesh = ax.pcolormesh(
        x_edges,
        y_edges,
        plot_values,
        cmap=cmap,
        norm=norm,
        edgecolors="white",
        linewidth=0.35,
        shading="flat",
        zorder=1
    )

#    ax.invert_yaxis()

    month_tick_positions = list(np.arange(12) + 0.5) + [(x_edges[-2] + x_edges[-1]) / 2]
    ax.set_xticks(month_tick_positions)
    ax.set_xticklabels(month_labels, color=text_color, fontsize=9, ha="center")

    if n_rows <= 20:
        step = 1
    elif n_rows <= 50:
        step = 5
    else:
        step = 10

    ytick_idx = list(range(0, n_rows, step))
    if 0 not in ytick_idx:
        ytick_idx.insert(0, 0)
    if ytick_idx[-1] != n_rows - 1:
        ytick_idx.append(n_rows - 1)

    ax.set_yticks(np.array(ytick_idx) + 0.5)
    ax.set_yticklabels([heatmap_data.index[i] for i in ytick_idx], color=text_color, fontsize=8.5, va="center")

    ax.set_xlabel("Month", color=text_color, fontsize=11, fontweight="medium", labelpad=6)
    ax.set_ylabel("Year", color=text_color, fontsize=11, fontweight="medium", labelpad=6)

    ax.tick_params(axis="x", colors=text_color, length=0, pad=4)
    ax.tick_params(axis="y", colors=text_color, length=3.5, width=0.8, pad=4)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(text_color)
    ax.spines["bottom"].set_visible(False)

    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, fraction=0.04)
    cbar.set_label("Number of records", color=text_color, fontsize=11, fontweight="medium")
    cbar.ax.tick_params(colors=text_color, labelsize=9, length=3.5, width=0.8)
    cbar.outline.set_visible(False)
    for spine in cbar.ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout()

    if outputdir is not None:
        outputfile = os.path.join(outputdir, "monthly_yearly_record_count_heatmap.png")
        print(f'INFO:save {outputfile}')
        fig.savefig(
            outputfile,
            dpi=300,
            bbox_inches="tight"
        )

    plt.show()


def plot_record_share_by_month_year(df, year_column=None, month_column=None, date_column=None, outputdir=None, cmap_strategy='uniform_deviation'):

    # 'uniform_centered' : divergent colormap centered on the uniform monthly share (100/12 ≈ 8.33%)
    # 'percentile_99' : sequential colormap scaled to the 99th percentile, with higher values clipped (improve contrast among lower values)

    if cmap_strategy not in ['percentile_99', 'uniform_deviation', 'uniform_deviation']:
        raise ValueError(f"Invalid value for `cmap_strategy`: '{cmap_strategy}'. Expected values: 'percentile_99', 'uniform_deviation', 'uniform_deviation'.")

    data = df.copy()

    if year_column is None:
        if date_column is None:
            raise
        else:
            data["year"] = data[date_column].str.split("-").str[0].astype("int")
            year_column = "year"
    else:
        data[year_column] = data[year_column].astype("int")

    data[year_column] = data[year_column].apply(
        lambda y: "≤1950" if y <= 1950 else y
    )

    if month_column is None:
        if date_column is None:
            raise
        else:
            data["month"] = (
                data[date_column]
                .str.split("-")
                .str[1]
                .astype("Int64")
            )
            month_column = "month"
    else:
        data[month_column] = data[month_column].astype("Int64")

    data[month_column] = data[month_column].fillna(13).astype(int)

    # Number of records by year and month
    heatmap_data = (
        data
        .groupby([year_column, month_column])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=range(1, 14), fill_value=0)
    )

    years_after_1950 = sorted(
        y for y in heatmap_data.index
        if y != "≤1950"
    )

    ordered_index = ["≤1950"] + years_after_1950

    heatmap_data = heatmap_data.reindex(
        ordered_index,
        fill_value=0
    )

    record_counts = heatmap_data.copy()

    # Convert monthly record counts to within-year percentages
    if cmap_strategy == "percentile_99":

        # Monthly and unknown shares relative to all annual records

        heatmap_data = (
            record_counts
            .div(record_counts.sum(axis=1), axis=0)
            .mul(100)
        )

        unknown_share = heatmap_data[13].copy()

    else:

        # Monthly shares relative only to records with a known month,
        # so that a uniform distribution corresponds to 100 / 12 ≈ 8.33%
        known_month_counts = record_counts.loc[:, 1:12]

        heatmap_data = (
            known_month_counts
            .div(known_month_counts.sum(axis=1).replace(0, np.nan), axis=0)
            .mul(100)
        )

        # Unknown-month share remains relative to all annual records
        unknown_share = (
            record_counts[13]
            .div(record_counts.sum(axis=1))
            .mul(100)
        )

    # Add spacer before unknown month
    heatmap_plot = heatmap_data.copy()

    if cmap_strategy == "percentile_99":
        heatmap_plot[14] = heatmap_plot[13]
        heatmap_plot[13] = np.nan
    else:
        heatmap_plot[13] = np.nan # spacer
        heatmap_plot[14] = np.nan  # unknown handled separately

    heatmap_plot = heatmap_plot[
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    ]

    plot_values = np.ma.masked_invalid(
        heatmap_plot.values
    )

    if cmap_strategy == 'percentile_99':
        month_labels = [
            "Jan.", "Feb.", "Mar.", "Apr.",
            "May", "Jun.", "Jul.", "Aug.",
            "Sep.", "Oct.", "Nov.", "Dec.",
            "Unk."
        ]
    else:
        month_labels = [
            "Jan.", "Feb.", "Mar.", "Apr.",
            "May", "Jun.", "Jul.", "Aug.",
            "Sep.", "Oct.", "Nov.", "Dec.",
            "Unk. (%)",
        ]

    # Fixed scale
#    max_share = np.nanmax(heatmap_plot.values)
#    cbar_max = min(100, np.ceil(max_share * 1.05 / 5)*5)
#    norm = plt.Normalize(vmin=0, vmax=cbar_max)

    values = heatmap_data.to_numpy().ravel()
    values = values[np.isfinite(values)]

    if cmap_strategy == 'percentile_99':

        cbar_max = np.ceil(np.percentile(values, 99) / 5) * 5
        cbar_max = min(cbar_max, 100)

        cmap = LinearSegmentedColormap.from_list("custom_blues", ["#F5F9FC","#DCEAF4","#B7D3E8","#7DAFD3","#3E82B8","#1F568C","#123A63"])
        norm = Normalize(vmin=0, vmax=cbar_max, clip=True)

    elif cmap_strategy == 'uniform_centered':

        expected_share = 100 / 12

#        cbar_max = min(100, np.ceil(values.max() * 1.05 / 5)*5)
        cbar_max = 25

        norm = TwoSlopeNorm(
            vmin=0,
            vcenter=expected_share,
            vmax=cbar_max
        )

        cmap = plt.get_cmap("RdBu_r")

    elif cmap_strategy == 'uniform_deviation':

        expected_share = 100 / 12  # 8.33

        delta = 5

        vmin = max(0, expected_share - delta)
        vmax = expected_share + delta

        norm = TwoSlopeNorm(
            vmin=vmin,
            vcenter=expected_share,
            vmax=vmax
        )

        base_cmap = plt.get_cmap("RdBu_r")
        cmap = LinearSegmentedColormap.from_list(
            "RdBu_r_truncated",
            base_cmap(np.linspace(0.08, 0.92, 256))
        ) # soften

    text_color = "#2F4358"

    n_rows = len(heatmap_data)
    fig_height = min(max(3.8, 0.12 * n_rows), 7)

    fig, ax = plt.subplots(
        figsize=(11.5, fig_height)
    )

    spacer_width = 0.2

    x_edges = np.array(
        list(range(13))
        + [12 + spacer_width, 13 + spacer_width]
    )

    y_edges = np.arange(n_rows + 1)

    if cmap_strategy == 'percentile_99':
        ax.axvspan(
            x_edges[-2],
            x_edges[-1],
            color="#F3F6F9",
            zorder=0
        )
    else:
        ax.axvspan(
            x_edges[-2] - spacer_width,
            x_edges[-2],
            color="#F5F7F9",
            zorder=0,
        )

    mesh = ax.pcolormesh(
        x_edges,
        y_edges,
        plot_values,
        cmap=cmap,
        norm=norm,
        edgecolors="white",
        linewidth=0.35,
        shading="flat",
        zorder=1
    )

    if cmap_strategy in ['uniform_centered', 'uniform_deviation']:

        unknown_values = unknown_share.to_numpy()
        unknown_vmax = max(5, np.ceil(np.nanmax(unknown_values) / 5) * 5)

        unknown_norm = Normalize(
            vmin=0,
            vmax=unknown_vmax,
            clip=True
        )

        base_greys = plt.get_cmap("Greys")
        unknown_cmap = LinearSegmentedColormap.from_list(
            "truncated_greys",
            base_greys(np.linspace(0.10, 0.75, 256))
        )

        unknown_x0 = x_edges[-2]
        unknown_x1 = x_edges[-1]

        for row_idx, share in enumerate(unknown_share):

            facecolor = (
                unknown_cmap(unknown_norm(share))
                if pd.notna(share)
                else "#F3F6F9"
            )

            # Neutral gray cell
            ax.add_patch(
                Rectangle(
                    (unknown_x0, row_idx),
                    unknown_x1 - unknown_x0,
                    1,
                    facecolor=facecolor,
                    edgecolor="white",
                    linewidth=0.35,
                    zorder=1,
                )
            )

            # Display unknown-month percentage
            if pd.notna(share):
                ax.text(
                    (unknown_x0 + unknown_x1) / 2,
                    row_idx + 0.5,
                    f"{share:.0f}",
                    ha="center",
                    va="center",
                    fontsize=5,
                    color=text_color,
                    zorder=2,
                )

    month_tick_positions = (
        list(np.arange(12) + 0.5)
        + [(x_edges[-2] + x_edges[-1]) / 2]
    )

    ax.set_xticks(month_tick_positions)

    ax.set_xticklabels(
        month_labels,
        color=text_color,
        fontsize=9,
        ha="center"
    )

    if n_rows <= 20:
        step = 1
    elif n_rows <= 50:
        step = 5
    else:
        step = 10

    ytick_idx = list(range(0, n_rows, step))

    if 0 not in ytick_idx:
        ytick_idx.insert(0, 0)

    if ytick_idx[-1] != n_rows - 1:
        ytick_idx.append(n_rows - 1)

    ax.set_yticks(
        np.array(ytick_idx) + 0.5
    )

    ax.set_yticklabels(
        [heatmap_data.index[i] for i in ytick_idx],
        color=text_color,
        fontsize=8.5,
        va="center"
    )

    ax.set_xlabel(
        "Month",
        color=text_color,
        fontsize=11,
        fontweight="medium",
        labelpad=6
    )

    ax.set_ylabel(
        "Year",
        color=text_color,
        fontsize=11,
        fontweight="medium",
        labelpad=6
    )

    ax.tick_params(
        axis="x",
        colors=text_color,
        length=0,
        pad=4
    )

    ax.tick_params(
        axis="y",
        colors=text_color,
        length=3.5,
        width=0.8,
        pad=4
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(text_color)
    ax.spines["bottom"].set_visible(False)

    if cmap_strategy == 'percentile_99':

        cbar = fig.colorbar(
            mesh,
            ax=ax,
            pad=0.02,
            fraction=0.04,
            extend="max"
        )

    elif cmap_strategy == 'uniform_centered':

        cbar = fig.colorbar(
            mesh,
            ax=ax,
            pad=0.02,
            fraction=0.04,
            extend="max"
        )

    elif cmap_strategy == 'uniform_deviation':

        cbar = fig.colorbar(
            mesh,
            ax=ax,
            pad=0.02,
            fraction=0.04,
            extend="both"
        )

    if cmap_strategy == 'percentile_99':

        cbar.set_label(
            "Share of annual records (%)",
            color=text_color,
            fontsize=11,
            fontweight="medium"
        )

    else:

        cbar.set_label(
            "Share of annual records (%)\n(centered on uniform monthly share)",
            color=text_color,
            fontsize=11,
            fontweight="medium"
        )

#    cbar.set_ticks(np.linspace(0, cbar_max, 6))

    if cmap_strategy == 'percentile_99':

        cbar.set_ticks(np.arange(0, cbar_max + 1, 5))

    elif cmap_strategy == 'uniform_centered':

#        cbar.set_ticks([0, expected_share, 25, 50, 75, 100])
#        cbar.ax.set_yticklabels(["0", "8.3", "25", "50", "75", "100"])

        ticks = np.arange(0, cbar_max + 1, 5)
        if expected_share not in ticks:
            ticks = np.sort(np.append(ticks, expected_share))
        cbar.set_ticks(ticks)

        cbar.set_ticklabels([
            f"{tick:.1f}" if np.isclose(tick, expected_share) else f"{tick:.0f}"
            for tick in ticks
        ])

    elif cmap_strategy == 'uniform_deviation':

        cbar.set_ticks([
            vmin,
            expected_share,
            vmax,
        ])

        cbar.set_ticklabels([
            f"{vmin:.1f} (−{delta})",
            f"{expected_share:.1f}",
            f"{vmax:.1f} (+{delta})",
        ])

    cbar.ax.tick_params(
        colors=text_color,
        labelsize=9,
        length=3.5,
        width=0.8
    )

    cbar.outline.set_visible(False)

    for spine in cbar.ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout()

    if outputdir is not None:
        outputfile = os.path.join(outputdir, f"monthly_yearly_record_share_heatmap_{cmap_strategy}.png")
        print(f'INFO:save {outputfile}')
        fig.savefig(outputfile, dpi=300, bbox_inches="tight")

    plt.show()

if __name__=='__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('inputfile', type=str)
    parser.add_argument('--year-column', '--year', type=str, help='Name of the column containing the year.', default=None)
    parser.add_argument('--month-column', '--month', type=str, help='Name of the column containing the year.', default=None)
    parser.add_argument('--date-column', '--date', type=str, help='Name of the column containing the date.', default=None)
    parser.add_argument('--cmap', type=str, help='Color strategy, either `percentile_99`, `uniform_centered` or `uniform_deviation`', default='uniform_deviation')
    parser.add_argument('--outputdir', type=str, default=None)
    args = parser.parse_args()

    year = args.year_column
    month = args.month_column
    date = args.date_column
    outputdir = args.outputdir
    cmap = args.cmap

    if year is None and month is None and date is None:
        raise ValueError(f"Either date or year and month mus be supplied.")

    df = pd.read_csv(args.inputfile, sep='\t', usecols=[year, month])

    print('Year distribution...')
    plot_records_by_year(df, year_column=year, date_column=date, outputdir=outputdir)
    print('done')

    print('Month distribution...')
    plot_records_by_month(df, month_column=month, date_column=date, outputdir=outputdir)
    print('done')

    print('Year X Month count distribution ...')
    plot_record_counts_by_month_year(df, year_column=year, month_column=month, date_column=date, outputdir=outputdir)
    print('done')

    print('Year X Month share distribution ...')
    plot_record_share_by_month_year(df, year_column=year, month_column=month, date_column=date, outputdir=outputdir, cmap_strategy=cmap)
    print('done')
