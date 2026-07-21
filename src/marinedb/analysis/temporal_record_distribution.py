#!/usr/bin/python
# coding: utf-8

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.colors import PowerNorm

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

    ax.spines["left"].set_color(text_color)
    ax.spines["bottom"].set_color(text_color)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.4)

    plt.tight_layout()

    if outputdir is not None:
        fig.savefig(
            os.path.join(outputdir,"yearly_record_distribution.png"),
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

    fig, ax = plt.subplots(figsize=(10, 5))

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

    ax.spines["left"].set_color(text_color)
    ax.spines["bottom"].set_color(text_color)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.4)

    plt.tight_layout()

    if outputdir is not None:
        fig.savefig(
            os.path.join(outputdir,"monthly_record_distribution.png"),
            dpi=300,
            bbox_inches="tight"
        )

    plt.show()

def plot_records_by_month_year(df, year_column=None, month_column=None, date_column=None, outputdir=None):

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

    cmap = LinearSegmentedColormap.from_list(
        "custom_blues",
        ["#F7FAFC", "#D9E6F2", "#8FAFCC", "#4E6A86", "#24507F", "#16324F"]
    )
#    cmap.set_bad("#F5F7FA")
    norm = PowerNorm(gamma=0.8)
    text_color = "#2F4358"

    n_rows = len(heatmap_data)
#    fig_height = min(max(6.0, 0.24 * n_rows), 13)
#    fig_height = min(max(5.5, 0.22 * n_rows), 12)
    fig_height = min(max(3.8, 0.12 * n_rows), 7)
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
        fig.savefig(
            os.path.join(outputdir, "monthly_yearly_record_heatmap.png"),
            dpi=300,
            bbox_inches="tight"
        )

    plt.show()



