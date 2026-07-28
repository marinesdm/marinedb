#!/usr/bin/python
# coding: utf-8

# External import

import os
import json
import time
import glob
import psutil
import h3pandas # `h3pandas` automatically applies H3 functions to Pandas Dataframes
import numpy as np
import pandas as pd
from tqdm import tqdm

# Internal import

from marinedb.utils import resolvepath
from marinedb.utils import convertbytes
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv
from marinedb.utils import getdefaultoutputfile

from marinedb.tools.taxonomic import taxasubset_species_identifier
from marinedb.tools.taxonomic.plot_taxasubset_upperbound_sampling import H3GeometryCache, H3SamplingMapCartopy, STATUS_COLORS, create_gif_H3_sampling

# Global variable

__all__ = [] # populated using the @export decorator

def h3grid_locations(df, latkey, lonkey, resolution, return_params=True):

    # Use a copy to avoid side effects: h3grid_locations() modifies 'cell',
    # which can otherwise corrupt the original df and cause H3 index mismatches.
    df = df.copy()

    cdf = df[[latkey, lonkey]].h3.geo_to_h3(resolution=resolution, lat_col=latkey, lng_col=lonkey, set_index=False)
    df['cell'] = cdf[f'h3_{resolution:02}'].tolist()

    if return_params:

        h3params = pd.DataFrame([],index=df['cell'].unique())
        h3params = h3params.h3.cell_area(unit='km^2')
        h3params = h3params.h3.k_ring(k=1, explode=False)
        h3params = h3params.rename(columns={'h3_cell_area':'area_km2', 'h3_k_ring':'ring_1'})

        return df, h3params

    return df

def select_locations(df, latkey, lonkey, speciesidkey, nloc_per_species, species_subset=None, max_resolution=8, location_sampling_seed=None, export_process=False, export_type='gif', outputdir='./', verbose=True, verbose_level=2, indent=''):

    # Settings

    if verbose_level == 0:
        verbose = False
    if verbose_level > 2:
        verbose_level = 2

    if not 0 <= max_resolution <= 15:
        raise ValueError(f'`taxasubset.py` | `max_resolution` must be between 0 and 15. See: https://h3geo.org/docs/core-library/restable/')

    if export_process:
        printv(f'WARNING | Setting `export_process` to True will significantly slow down processing, and multiple images will be saved per species', verbose=verbose, indent=indent)
        nspecies = df[speciesidkey].nunique()
        if nspecies > 50:
            printv(f'WARNING | Detected {nspecies} species. Using `export_process` will store multiple images per species.', verbose=True, indent=indent)
            change_export_process = input(indent + f'Do you want to set `export_process` to False? (y/n) ').strip().lower()
            while change_export_process not in ['y', 'n']:
                printv('Please answer with "y" (yes) or "n" (no).', verbose=True, indent=indent)
                change_export_process = input(indent + f'Do you want to set `export_process` to False? (y/n) ').strip().lower()
            if change_export_process == 'y':
                export_process = False

    if export_process and ('sampling' not in outputdir.split('/')):
        outputdir = os.path.join(outputdir, 'sampling', 'location')

    if species_subset is None:
        # Apply filtering to all species
        species_subset = df[speciesidkey].unique().tolist()

    rng = np.random.default_rng(location_sampling_seed)
    start = time.time()
    full_location_subset = []

    if not verbose:
        process = species_subset
    if verbose:
        if (verbose_level == 2):
            process = species_subset
        else:
            process = tqdm(species_subset, desc=indent + 'Progress')
            verbose = False

    for species in process:

        if export_process:

            geometry_cache = H3GeometryCache(target_crs="EPSG:8857", backend="cartopy") # NEW

            sampling_map = H3SamplingMapCartopy(          # NEW
                geometry_cache=geometry_cache,
                export_type=export_type,
                cell_column="cell",
                palette=STATUS_COLORS,
                show_legend=True,
                show_coastlines=True,
                verbose=verbose,
                indent=indent
            )

        printv(f'>>> taxon_id {species}', verbose=verbose, indent=indent)
        subset = df.loc[df[speciesidkey] == species, [latkey, lonkey, speciesidkey]].copy()

        # Discretize locations using H3 grid at maximum resolution
        subset_maxresolution, h3params_maxresolution = h3grid_locations(subset, latkey, lonkey, resolution=max_resolution)

        # Check whether there are fewer discrete locations than locations to sample
        nloc = len(subset_maxresolution['cell'].unique())
        if nloc <= nloc_per_species:
            if  nloc < nloc_per_species:
                printv(f"INFO | '{species}' species has fewer than {nloc_per_species} distinct locations (i.e, {nloc}) at the maximum specified resolution (i.e., {max_resolution})", verbose=verbose, indent=indent)
            else:
                printv(f"INFO | '{species}' species has exactly {nloc_per_species} distinct locations at the maximum specified resolution (i.e., {max_resolution})", verbose=verbose, indent=indent)
            # Update the location subset
            species_location_subset = list(
                subset_maxresolution
                .reset_index()[['index',speciesidkey,'cell']]
                .itertuples(index=False, name=None)
            )
            full_location_subset.extend(species_location_subset)
            continue

        # Discretize locations using H3 grid at the coarsest resolution
        resolution = 0
        if export_process:
            step = 0
            os.makedirs(outputdir, exist_ok=True)

        subset, h3params = h3grid_locations(subset, latkey, lonkey, resolution=resolution)

        n = 0 # number of sampled grid cells
        sampled_grid_locations = set()
        adjacent_grid_locations = set()
        grid_locations = set(subset['cell'].unique())
        remaining_grid_locations = set(grid_locations) # use set() to create a distinct object
        sampled_location_indices = []

        while n < nloc_per_species:

            while (len(remaining_grid_locations) == 0):

                # If all discretized locations at a given resolution have been sampled,
                # continue at a finer resolution

                resolution += 1

                if (resolution > max_resolution):
                    if len(adjacent_grid_locations) == 0:
                        raise Exception('[DEV] Unexpected error during processing')
                    resolution -= 1
                    # Sample from neighboring discretized locations
                    adjacent_grid_locations = set()
                    remaining_grid_locations = grid_locations - sampled_grid_locations
                    break

                if resolution != max_resolution:
                    # Discretize locations using H3 grid at resolution `resolution`
                    subset, h3params = h3grid_locations(subset[[latkey,lonkey]], latkey, lonkey, resolution=resolution)
                else:
                    subset, h3params = subset_maxresolution, h3params_maxresolution

                ## grid cell identifiers
                grid_locations = set(h3params.index)
                ## sampled grid cell identifiers
                sampled_grid_locations = set(subset.loc[sampled_location_indices, 'cell'])
                ## neighboring grid cell identifiers
                adjacent_grid_locations = {
                    cell
                    for neighbors in h3params.loc[list(sampled_grid_locations), 'ring_1']
                    for cell in neighbors
                }

                # Exclude sampled grid cells and their neighbors from candidate cells to maximize spatial coverage
                remaining_grid_locations = grid_locations - adjacent_grid_locations

                if export_process and (len(remaining_grid_locations) == 0): # NEW

                    params = {
                              'sampled_cells': remaining_grid_locations,
                              'adjacent_cells': set(),
                              'previous_sampled_cells': sampled_grid_locations,
                              'previous_adjacent_cells': adjacent_grid_locations,
                              'species': species,
                              'resolution': resolution,
                              'step': step,
                              'outputdir': outputdir,
                             }

                    plot_H3_sampling(subset, sampling_map, **params) # NEW
                    step += 1

            if (nloc_per_species - n) >= len(remaining_grid_locations):

                # Fewer discrete locations than locations to sample

                # Sample one observation per discrete location
                condition = subset['cell'].isin(remaining_grid_locations)
                sampled_location_index = list(subset[condition].groupby(['cell']).sample(n=1, random_state=location_sampling_seed).index)

                if export_process:
                    previous_sampled_cells = set(sampled_grid_locations)
                    previous_adjacent_cells = set(adjacent_grid_locations)
                    sampled_grid_locations = remaining_grid_locations
                    adjacent_grid_locations = {
                        cell
                        for neighbors in h3params.loc[list(sampled_grid_locations), 'ring_1']
                        for cell in neighbors
                    }

                # Update set after sampling
                remaining_grid_locations = set()

            else:

                # More discrete locations than locations to sample

                # Sample one discrete location based on cell area
                candidate_grid_locations = list(remaining_grid_locations)
                probabilities = h3params.loc[candidate_grid_locations, 'area_km2'] / h3params.loc[candidate_grid_locations, 'area_km2'].sum()
                probabilities = probabilities.tolist()
                sampled_grid_location = rng.choice(candidate_grid_locations, replace=False, p=probabilities)
                # Sample one observation
                condition = (subset['cell'] == sampled_grid_location)
                sampled_location_index = list(subset[condition].sample(n=1, random_state=location_sampling_seed).index)

                if export_process:
                    previous_sampled_cells = set(sampled_grid_locations)
                    previous_adjacent_cells = set(adjacent_grid_locations)

                # Update sets after sampling
                sampled_grid_locations.add(sampled_grid_location)
                adjacent_grid_locations.update(h3params.loc[sampled_grid_location,'ring_1'])
                remaining_grid_locations = remaining_grid_locations - adjacent_grid_locations

            sampled_location_indices += sampled_location_index

            # Update number of sampled grid cells
            n += len(sampled_location_index)

            if export_process:

                params = {
                          'sampled_cells': sampled_grid_locations,
                          'adjacent_cells': adjacent_grid_locations,
                          'previous_sampled_cells': previous_sampled_cells,
                          'previous_adjacent_cells': previous_adjacent_cells,
                          'species': species,
                          'resolution': resolution,
                          'step': step,
                          'outputdir': outputdir,
                         }

                plot_H3_sampling(subset, sampling_map, **params) # NEW
                step += 1

        # Update the location subset

        sampled_grid_locations = subset_maxresolution.loc[sampled_location_indices, 'cell'].unique().tolist()

        if len(sampled_location_indices) != len(sampled_grid_locations):
            # H3 grid edge effects
            printv(f'INFO | Due to H3 grid edge effects, species {species} will be represented by only {len(sampled_grid_locations)} distinct locations', verbose=verbose, indent=indent)

        condition = subset_maxresolution['cell'].isin(sampled_grid_locations)
        species_location_subset = list(
            subset_maxresolution[condition]
            .reset_index()[['index', speciesidkey, 'cell']]
            .itertuples(index=False, name=None)
        )
        full_location_subset.extend(species_location_subset)

        if export_process:

            if (export_type == 'both') or (export_type == 'gif'):
                create_gif_H3_sampling(outputdir, species, export_type, verbose=verbose, indent=indent) # + '  ')

            sampling_map.close()
            geometry_cache.clear()

    if verbose_level == 1:
        verbose = True
    printv(f'TIME | substep: {round(time.time() - start)}s', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    full_location_subset = pd.DataFrame(full_location_subset, columns=['index',speciesidkey,'cell'])

    return full_location_subset

def downsample_observations(df, latkey, lonkey, speciesidkey, maxobs_per_taxon, outputfile, resolution=8, downsample_seed=None, outputdir='./', export_process=False, export_type='gif', verbose=True, verbose_level=2, indent=''):

    printv(f'* Cap data at {maxobs_per_taxon} observations per species', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)
    indent = indent + '  '

    start = time.time()
    nobs_before = len(df)
    downsample_indices = []

    # Count observations per species

    nobs_per_species = df[speciesidkey].value_counts()

    # Species with fewer observations than the specified upper bound

    species_nobs_below_upperbound = list(nobs_per_species[nobs_per_species < maxobs_per_taxon].index)
    pct = round((len(species_nobs_below_upperbound) / len(nobs_per_species)) * 100, 2)
    printv(f'** Keep all observations for species with fewer than {maxobs_per_taxon} observations', verbose=verbose, indent=indent)
    printv(f'INFO | {len(species_nobs_below_upperbound)} species below threshold ({pct}%)', verbose=verbose, indent=indent + '   ')
    printv('', verbose=verbose, indent=indent)

    if len(species_nobs_below_upperbound) > 0:
        downsample_indices += list(df[df[speciesidkey].isin(species_nobs_below_upperbound)].index)

    # Species with more observations than the specified upper bound

    species_nobs_above_upperbound = list(nobs_per_species[nobs_per_species >= maxobs_per_taxon].index)
    pct = round((len(species_nobs_above_upperbound) / len(nobs_per_species)) * 100, 2)

    if len(species_nobs_above_upperbound) > 0:

        printv(f'** Sample up to {maxobs_per_taxon} distinct locations for species with at least {maxobs_per_taxon} observations', verbose=verbose, indent=indent)
        printv(f'INFO | {len(species_nobs_above_upperbound)} species above threshold ({pct}%)', verbose=verbose, indent=indent + '   ')
        printv('', verbose=verbose, indent=indent)

        params = {
                  'latkey': latkey,
                  'lonkey': lonkey,
                  'speciesidkey': speciesidkey,
                  'species_subset': None,
                  'nloc_per_species': maxobs_per_taxon,
                  'max_resolution': resolution,
                  'location_sampling_seed': downsample_seed,
                  'export_process': export_process,
                  'export_type': export_type,
                  'outputdir': outputdir,
                  'verbose': verbose,
                  'verbose_level': verbose_level,
                  'indent': indent + '   '
                 }

        ## Sample discrete locations

        location_sample = select_locations(df.loc[df[speciesidkey].isin(species_nobs_above_upperbound),[latkey, lonkey, speciesidkey]], **params)

        ## Count discrete locations per species

        ncell_per_species = location_sample[[speciesidkey,'cell']].drop_duplicates()[speciesidkey].value_counts()

        debug = ncell_per_species[ncell_per_species > maxobs_per_taxon] #debug
        if len(debug) > 0:
            print('[DEV] Unexpected')
            print(debug)
            raise Exception

        ## Species with `maxobs_per_taxon` discrete locations
        ## Sample one observation per discrete location

        species_ncell_equal_upperbound = list(ncell_per_species[ncell_per_species == maxobs_per_taxon].index)

        printv(f'** Sample one observation per sampled location for species with at least {maxobs_per_taxon} distinct locations', verbose=verbose, indent=indent)
        printv(f'INFO | {len(species_ncell_equal_upperbound)} species', verbose=verbose, indent=indent + '   ')
        printv('', verbose=verbose, indent=indent)

        if len(species_ncell_equal_upperbound) > 0:
            condition = location_sample[speciesidkey].isin(species_ncell_equal_upperbound)
            downsample_indices += location_sample[condition].groupby([speciesidkey,'cell'])['index'].sample(n=1, random_state=downsample_seed).tolist()

        ## Species with fewer than `maxobs_per_taxon` discrete locations

        species_ncell_below_upperbound = list(ncell_per_species[ncell_per_species < maxobs_per_taxon].index)

        printv(f'** Sample {maxobs_per_taxon} observations evenly accross locations for species with fewer than {maxobs_per_taxon} distinct locations', verbose=verbose, indent=indent)
        printv(f'INFO | {len(species_ncell_below_upperbound)} species', verbose=verbose, indent=indent + '   ')
        printv('', verbose=verbose, indent=indent)

        if len(species_ncell_below_upperbound) > 0:

            condition = location_sample[speciesidkey].isin(species_ncell_below_upperbound)
            location_sample = location_sample[condition]

            # Compute the number of observations to sample per species per cell

            nobs_per_species_per_cell = location_sample[[speciesidkey,'cell']].value_counts().sort_index()
            ncell_per_species = ncell_per_species.loc[species_ncell_below_upperbound].sort_index()
            ## even sampling accross locations
            nsamples_per_species_per_cell = maxobs_per_taxon // ncell_per_species
            nsamples_per_species_per_cell = nsamples_per_species_per_cell.repeat(ncell_per_species)
            nsamples_per_species_per_cell = nsamples_per_species_per_cell.set_axis(nobs_per_species_per_cell.index)
            ## ensure samples per species per cell do not exceed available observations
            nsamples_per_species_per_cell = nsamples_per_species_per_cell.clip(upper=nobs_per_species_per_cell)
            ## compute remaining samples per species after per-cell allocation
            nsamples_remaining_per_species = maxobs_per_taxon - nsamples_per_species_per_cell.groupby(level=speciesidkey).sum()
            nsamples_remaining_per_species = nsamples_remaining_per_species[nsamples_remaining_per_species > 0]

            i = 0
            while len(nsamples_remaining_per_species) > 0:

                nobs_per_species_per_cell_subset = nobs_per_species_per_cell - nsamples_per_species_per_cell
                nobs_per_species_per_cell_subset = nobs_per_species_per_cell_subset[nobs_per_species_per_cell_subset > 0]
                nobs_per_species_per_cell_subset = nobs_per_species_per_cell_subset.loc[list(nsamples_remaining_per_species.index)]

                ncell_per_species = nobs_per_species_per_cell_subset.groupby(level=speciesidkey).size()

                ## species with fewer discrete locations than the target sample size

                species_nsamples_above_ncell = list(nsamples_remaining_per_species[nsamples_remaining_per_species >= ncell_per_species].index)
                species_cell_above = nobs_per_species_per_cell_subset.loc[species_nsamples_above_ncell].index
                species_above = species_cell_above.get_level_values(speciesidkey)

                increment_nsamples = (nsamples_remaining_per_species.loc[species_above] // ncell_per_species.loc[species_above]).to_numpy()
                nsamples_per_species_per_cell.loc[species_cell_above] += increment_nsamples
                nsamples_per_species_per_cell.loc[species_cell_above] = nsamples_per_species_per_cell.loc[species_cell_above].clip(upper=nobs_per_species_per_cell.loc[species_cell_above])

                ## species with more discrete locations than the target sample size

                species_nsamples_below_ncell = list(nsamples_remaining_per_species[nsamples_remaining_per_species < ncell_per_species].index)

                for species in species_nsamples_below_ncell:
                    random_species_cell = nobs_per_species_per_cell_subset.loc[species].sample(n=nsamples_remaining_per_species.loc[species], random_state=downsample_seed).index
                    random_species_cell = [(species, cell) for cell in random_species_cell]
                    nsamples_per_species_per_cell.loc[random_species_cell] += 1

                ## compute remaining samples per species after per-cell allocation

                nsamples_remaining_per_species = maxobs_per_taxon - nsamples_per_species_per_cell.groupby(level=speciesidkey).sum()
                nsamples_remaining_per_species = nsamples_remaining_per_species[nsamples_remaining_per_species > 0]

                i+=1

            # Sample observations

            nsamples_per_species_per_cell = nsamples_per_species_per_cell.reset_index()

            location_sample = location_sample.set_index([speciesidkey,'cell']).sort_index()
            for taxon_id, cell, nsamples in nsamples_per_species_per_cell.itertuples(index=False, name=None):
                downsample_indices.extend(
                    location_sample.loc[(taxon_id, cell), 'index']
                    .sample(n=nsamples, random_state=downsample_seed)
                    .tolist()
                )

    # Downsample observations

    df = df.loc[downsample_indices, :]
    nobs_after = len(df)

    # Store

    printv(f'* Save to {outputfile}', verbose=verbose, indent=indent)
    df.to_csv(outputfile, sep='\t', index=False)

    printv('', verbose=verbose, indent=indent)
    printv(f'taxasubset (upperbound) | before: {nobs_before:,d}, after : {nobs_after:,d} ({nobs_after - nobs_before:,d})', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    printv(f'TIME | substep: {round(time.time() - start)}s', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    return outputfile

def plot_H3_sampling(df, sampling_map, sampled_cells, adjacent_cells, previous_sampled_cells, previous_adjacent_cells, species, resolution, step, outputdir='./'):

    current_cell_ids = (df["cell"].astype(str).drop_duplicates())

    sampling_map.update(
        cell_ids=current_cell_ids,
        previous_sampled_cells=previous_sampled_cells,
        previous_adjacent_cells=previous_adjacent_cells,
        sampled_cells=sampled_cells,
        adjacent_cells=adjacent_cells,
        species=species,
        resolution=resolution,
        step=step
    )

    sampling_map.save(species, step, resolution, outputdir)

@export
def apply(inputfile, limit, latkey, lonkey, sep='\t', speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, resolution=8, cleanup=False, dtypesfile=None, outputdir='./', outputfile=None, export_process=False, export_type='gif', verbose=True, verbose_level=2, indent=''):
    """Spatially subsample overrepresented taxa.

    Limits the number of records associated with each taxon to a
    user-defined maximum while promoting broad spatial coverage. Taxa are
    evaluated using a species identifier supplied through `speciesidkey` or
    constructed from the available taxonomic classification columns.

    Taxa represented by fewer than `limit` records are retained unchanged.
    For taxa meeting or exceeding this threshold, occurrence coordinates are
    discretized with the H3 hierarchical hexagonal grid. Discrete locations
    are selected progressively from coarse to fine resolutions, with
    selection probabilities weighted by cell area and neighboring cells
    temporarily excluded to promote spatial dispersion.

    After the discrete locations have been selected, records are sampled
    across them as evenly as possible, subject to the number of observations
    available in each cell. All original columns are retained.

    !!! Warning

        The function assumes that species identifiers and geographic
        coordinates have already been cleaned. It should be applied only to
        datasets without missing or invalid values in the identifier,
        latitude, and longitude columns.

    Args:
        inputfile (str):
            Path to the input tabular file.

        limit (int):
            Maximum number of records to retain per taxon. Taxa represented
            by fewer than this number of records are retained unchanged.
            Taxa meeting or exceeding the threshold are submitted to the
            spatial subsampling procedure.

        latkey (str):
            Name of the column containing decimal latitude values.

        lonkey (str):
            Name of the column containing decimal longitude values.

        sep (str, optional):
            Field delimiter used in the input and output files. 

        speciesidkey (str, optional):
            Name of the column containing the species identifier used to
            group records. When omitted, species identifiers are constructed
            from the available taxonomic classification columns.

            When `taxasubset` is used after `isinworms` in the integrated
            workflow, this argument is supplied automatically and corresponds
            to the WoRMS `AphiaID`. 

        specieskey (str, optional):
            Name of the species column used, together with the available
            higher-rank columns, to construct species identifiers when
            `speciesidkey` is not provided.

        genuskey (str, optional):
            Name of the genus column used to construct species identifiers
            when needed. 

        familykey (str, optional):
            Name of the family column used to construct species identifiers
            when needed. 

        orderkey (str, optional):
            Name of the order column used to construct species identifiers
            when needed. 

        classkey (str, optional):
            Name of the class column used to construct species identifiers
            when needed.

        phylumkey (str, optional):
            Name of the phylum column used to construct species identifiers
            when needed. 

        kingdomkey (str, optional):
            Name of the kingdom column used to construct species identifiers
            when needed. 

        resolution (int, optional):
            Maximum H3 resolution used to discretize occurrence locations.
            Sampling begins at resolution `0` and progresses toward this
            maximum resolution as additional discrete locations are needed.
            Valid H3 resolutions range from `0` to `15`. 
            
            The default  `resolution` of `8` corresponds to cells of 
            approximately 0.74 km², with a maximum within-cell distance of 
            approximately 1.06 km. 

        cleanup (bool, optional):
            Whether to remove the input file after successful processing
            when it differs from the output file. 

        dtypesfile (str, optional):
            Path to a JSON file defining column data types when reading the
            input file. 

        outputdir (str, optional):
            Directory in which to write the processed dataset and, when
            requested, sampling visualizations. 

        outputfile (str, optional):
            Path or name of the output file. When omitted, or when identical
            to `inputfile`, a default filename is generated using the
            `taxasubset` processing suffix. 

        export_process (bool, optional):
            Whether to export a visualization of each discrete-location
            selection step for every taxon submitted to spatial
            subsampling. Exports are written under
            `sampling/location` within the output directory unless that
            directory already contains a `sampling` component. 

        export_type ({"gif", "image", "both"}, optional):
            Format used to export the location-selection process. `"image"`
            retains one image for each sampling step, `"gif"` combines the
            images into an animation and removes the individual images, and
            `"both"` retains both outputs. 

    Returns:
        (str):
            Path to the processed output file. When insufficient memory is
            available, processing is aborted and `inputfile` is returned
            unchanged.

    Raises:
        ValueError:
            If `export_process=True` and `export_type` is not `"gif"`,
            `"image"`, or `"both"`.
        ValueError:
            If `max_resolution` is outside the supported H3 range from `0` to `15`.          

    Notes:

        H3 discretization is applied only to taxa meeting or exceeding
        `limit`. Taxa represented by fewer than `limit` records are retained 
        unchanged.

        For overrepresented taxa, discrete locations are selected from coarse 
        to fine H3 resolutions until enough locations have been selected. At 
        each step, candidate cells are sampled with probabilities proportional 
        to their area, and neighboring cells are temporarily excluded to reduce
        spatial clustering. 

        Records are subsequently allocated as evenly as possible across the
        selected cells. When some cells contain fewer records than their
        provisional allocation, the remaining quota is redistributed among
        cells with additional available records.

        The procedure normally retains exactly `limit` records for each
        subsampled taxon. In exceptional cases involving H3 grid-edge
        effects, fewer records may be retained.

        Sampling within cells is random and no fixed random seed is currently
        exposed. Results are therefore not guaranteed to be reproducible
        across runs.

        Distributed processing is not currently implemented for this step.
        The full input dataset must fit in memory; otherwise, processing is
        aborted and the input file is left unchanged.
    """

    if export_process:
        if export_type not in {'gif', 'both', 'image'}:
            raise ValueError(f"`taxasubset.py` | Invalid export_type '{export_type}'. Valid values are: 'gif', 'both', 'image'.")

    if dtypesfile is not None:
        with open(dtypesfile,'r') as f:
            dtypes = json.load(f)
    else:
        dtypes = None

    outputdir = resolvepath.apply(outputdir)
    if (outputfile is None) or (len(outputfile) == 0) or (inputfile == outputfile):
        outputfile = getdefaultoutputfile.apply(inputfile, 'taxasubset', outputdir=outputdir, verbose=verbose, indent=indent)

    # Ensure enough memory is available for processing

    available_memory = psutil.virtual_memory().available
    file_size = os.path.getsize(inputfile)
    required_memory = 15 * file_size

    if available_memory >= required_memory:

        sep = sep.encode('utf-8').decode('unicode_escape')
        df = pd.read_csv(inputfile, sep=sep, dtype=dtypes)

        params = {
                   'speciesidkey':speciesidkey,
                   'specieskey':specieskey,
                   'genuskey':genuskey,
                   'familykey':familykey,
                   'orderkey':orderkey,
                   'classkey':classkey,
                   'phylumkey':phylumkey,
                   'kingdomkey':kingdomkey,
                   'distributed': False,
                   'verbose': verbose,
                   'indent': indent
                  }

        df, speciesidkey, _ = taxasubset_species_identifier.apply(df, **params)

        params = {
                  'latkey': latkey,
                  'lonkey': lonkey,
                  'speciesidkey': speciesidkey,
                  'maxobs_per_taxon': limit,
                  'resolution': resolution,
                  'outputdir': outputdir,
                  'outputfile': outputfile,
                  'export_process': export_process,
                  'export_type': export_type,
                  'verbose': verbose,
                  'verbose_level': verbose_level,
                  'indent': indent
                 }

        outputfile = downsample_observations(df, **params)

        # Clean

        if cleanup and (inputfile != outputfile):
            printv(f'* Delete {inputfile}', verbose=verbose, indent=indent)
#            os.remove(inputfile) # debug

    else:

        printv(
                f"WARNING | Insufficient available memory: "
                f"{convertbytes.apply(available_memory)} available, "
                f"at least {convertbytes.apply(required_memory)} required. "
                f"Distributed computation is not yet implemented. "
                f"Processing aborted.",
                verbose=verbose,
                indent=indent
             )

        outputfile = inputfile

    return outputfile

