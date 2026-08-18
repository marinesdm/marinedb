
import os
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter


def plot_nspecies_per_occurrence_threshold(inputfile, specieskey, outputdir='./', sep='\t'):

    df = pd.read_csv(inputfile, sep=sep, usecols=[specieskey])

    species_counts = df[specieskey].value_counts()

    max_threshold = 1000
    candidate_thresholds = [10, 50, 100, 150]

    count_distribution = (
        species_counts
        .clip(upper=max_threshold)
        .value_counts()
        .reindex(range(1, max_threshold + 1), fill_value=0)
    )

    n_species = count_distribution.iloc[::-1].cumsum().iloc[::-1]

    N_species = df[specieskey].nunique()

    fig, ax = plt.subplots(figsize=(11, 5.5))

    dark_blue = "#17324D"

    ax.plot(n_species.index, n_species.values, color="#2F6B9A", linewidth=2)
#    ax.step(n_species.index, n_species.values, color="#2F6B9A", linewidth=2, where="post")

    for threshold in candidate_thresholds:
        n = n_species.loc[threshold]
        pct = round((n / N_species) * 100, 1)

        ax.axvline(threshold, color="#8FAEC4", linestyle="--", linewidth=0.9, alpha=0.6)
        ax.scatter(threshold, n, color="#2F6B9A", s=28, zorder=3)

        ax.annotate(
            f"{n:,} ({pct}%)",
            xy=(threshold, n),
            xytext=(7, 7),
            textcoords="offset points",
            fontsize=9,
            color=dark_blue # "#244A66"
        )

    n_at_1 = n_species.loc[1]
    pct_at_1 = round((n_at_1 / N_species) * 100, 1)

    ax.scatter(
        1,
        n_at_1,
        color="#2F6B9A",
        s=28,
        zorder=5
    )

    ax.annotate(
        f"{n_at_1:,} ({pct_at_1}%)",
        xy=(1, n_at_1),
        xytext=(10, 0),
        textcoords="offset points",
        ha="left",
        va="center",
        fontsize=9,
        color=dark_blue
    )

    n_at_1000 = n_species.loc[1000]
    pct_at_1000 = round((n_at_1000 / N_species) * 100, 1)

    ax.scatter(
        1000,
        n_at_1000,
        color="#2F6B9A",
        s=28,
        zorder=3
    )

    ax.annotate(
        f"{n_at_1000:,} ({pct_at_1000}%)",
        xy=(1000, n_at_1000),
        xytext=(0, 8),
        textcoords="offset points",
        ha="right",
        fontsize=9,
        color=dark_blue  # "#244A66"
    )

    ax.yaxis.set_major_formatter(
        StrMethodFormatter("{x:,.0f}")
    )

    ax.set_xlim(-5, 1030)
    ax.set_ylim(0, len(species_counts)*1.08)

    ax.set_xticks([10, 50, 100, 150, 250, 500, 750, 1000])

    ax.set_xlabel("Occurrence threshold", color=dark_blue)
    ax.set_ylabel("Number of species", color=dark_blue)

    ax.tick_params(
        axis="both",
        colors=dark_blue
    )

    ax.spines["left"].set_color(dark_blue)
    ax.spines["bottom"].set_color(dark_blue)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(axis="y", linestyle=":", linewidth=0.7, alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    outputfile = os.path.join(outputdir, "species_occurrence_threshold.png")
#    outputfile = os.path.join(outputdir, "species_occurrence_threshold_step.png")

    plt.tight_layout()

    print(f'INFO:Save figure to {os.path.abspath(outputfile)}')

    plt.savefig(
        outputfile,
        dpi=300,
        bbox_inches="tight"
    )

    plt.show()

if __name__=='__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('inputfile', type=str)
    parser.add_argument('--species-column', '--species', type=str, help='Name of the column containing the species identifier.', required=True)
    parser.add_argument('--outputdir', type=str)
    args = parser.parse_args()

    plot_nspecies_per_occurrence_threshold(args.inputfile, args.species_column, sep='\t', outputdir=args.outputdir)
