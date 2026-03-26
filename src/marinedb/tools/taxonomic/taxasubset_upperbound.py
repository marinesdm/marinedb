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
#    print('nloc_per_species', nloc_per_species) # debug
    if verbose_level == 0:
        verbose = False
    if verbose_level > 2:
        verbose_level = 2

    if max_resolution > 15:
        raise ValueError(f'`datasets.py` | `max_resolution` must be lower or equal to 15. See: https://h3geo.org/docs/core-library/restable/')

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
        if export_process:
            init = True

    if export_process and ('sampling' not in outputdir.split('/')):
        outputdir = os.path.join(outputdir, 'sampling', 'location')
#    outputdir_split = outputdir.split('/')
#    if (outputdir_split[-2] != 'sampling') or (outputdir_split[-1] != 'location'):
#        outputdir = os.path.join(outputdir, 'sampling/location')

#    if 'sampling' not in outputdir_split[-2:]:
#        outputdir = os.path.join(outputdir, 'sampling/location')
#    if outputdir_split[-1] != 'location':
#        outputdir = os.path.join(outputdir, 'location')

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
            species_location_subset = subset_maxresolution.reset_index()[['index',speciesidkey,'cell']].values.tolist()
            full_location_subset += species_location_subset
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

        count_step = 0 # debug
        while n < nloc_per_species:
#            if count_step%10==0: #debug
#                print(f'Progress : {n}/{nloc_per_species}')
#                print(f'Resolution : {resolution}')
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
                adjacent_grid_locations = set(np.concatenate(h3params.loc[list(sampled_grid_locations), 'ring_1'].values))
                # Exclude sampled grid cells and their neighbors from candidate cells to maximize spatial coverage
                remaining_grid_locations = grid_locations - adjacent_grid_locations

            if (nloc_per_species - n) >= len(remaining_grid_locations):

                # Fewer discrete locations than locations to sample

                # Sample one observation per discrete location
                condition = subset['cell'].isin(remaining_grid_locations)
                sampled_location_index = list(subset[condition].groupby(['cell']).sample(n=1, random_state=location_sampling_seed).index)

                if export_process:
                    previous_sampled_cells = set(sampled_grid_locations)
                    previous_adjacent_cells = set(adjacent_grid_locations)
                    sampled_grid_locations = remaining_grid_locations
                    adjacent_grid_locations = set(np.concatenate(h3params.loc[list(sampled_grid_locations), 'ring_1'].values))

                # Update set after sampling
                remaining_grid_locations = set()

            else:

                # More discrete locations than locations to sample

                # Sample one discrete location
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
            count_step +=1 # debug

            if export_process:

                params = {
                          'latkey': latkey,
                          'lonkey': lonkey,
                          'speciesidkey': speciesidkey,
                          'sampled_cells': sampled_grid_locations,
                          'adjacent_cells': adjacent_grid_locations,
                          'previous_sampled_cells': previous_sampled_cells,
                          'previous_adjacent_cells': previous_adjacent_cells,
                          'species': species,
                          'resolution': resolution,
                          'step': step,
                          'init': init,
                          'export_type': export_type,
                          'outputdir': outputdir,
                          'verbose': verbose,
                          'indent': indent + '  '
                         }

                plot_h3grid_sampling(subset, **params)
                init = False
                step += 1

        # Update the location subset

        sampled_grid_locations = subset_maxresolution.loc[sampled_location_indices, 'cell'].unique().tolist()

        if len(sampled_location_indices) != len(sampled_grid_locations):
            # H3 grid edge effects
            printv(f'INFO | Due to H3 grid edge effects, species {species} will be represented by only {len(sampled_grid_locations)} distinct locations', verbose=verbose, indent=indent)

        condition = subset_maxresolution['cell'].isin(sampled_grid_locations)
        species_location_subset = subset_maxresolution[condition].reset_index()[['index',speciesidkey,'cell']].values.tolist()
        full_location_subset += species_location_subset

        if export_process:
            if (export_type == 'both') or (export_type == 'gif'):
                create_gif_h3grid_sampling(outputdir, species, export_type, verbose=verbose, indent=indent) # + '  ')

    if export_process:
        import matplotlib.pyplot as plt
        plt.close()

    if verbose_level == 1:
        verbose = True
    printv(f'TIME | substep: {round(time.time() - start)}s', verbose=verbose, indent=indent)

    full_location_subset = pd.DataFrame(full_location_subset, columns=['index',speciesidkey,'cell'])

    return full_location_subset

def downsample_observations(df, latkey, lonkey, speciesidkey, maxobs_per_taxon, resolution=8, downsample_seed=None, outputfile=None, outputdir='./', export_process=False, export_type='gif', verbose=True, verbose_level=2, indent=''):

    if (outputfile is None) or (len(outputfile) == 0):
        outputfile = getdefaultoutputfile.apply(inputfile, 'taxasubset', outputdir=outputdir)

    printv(f'* Cap data at {maxobs_per_taxon} observations per species', verbose=verbose, indent=indent)
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
    if len(species_nobs_below_upperbound) > 0:
        downsample_indices += list(df[df[speciesidkey].isin(species_nobs_below_upperbound)].index)

    # Species with more observations than the specified upper bound

    species_nobs_above_upperbound = list(nobs_per_species[nobs_per_species >= maxobs_per_taxon].index)
    pct = round((len(species_nobs_above_upperbound) / len(nobs_per_species)) * 100, 2)

    if len(species_nobs_above_upperbound) > 0:

        printv(f'** Sample up to {maxobs_per_taxon} distinct locations for species with at least {maxobs_per_taxon} observations', verbose=verbose, indent=indent)
        printv(f'INFO | {len(species_nobs_above_upperbound)} species above threshold ({pct}%)', verbose=verbose, indent=indent + '   ')

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
            print('debug')
            print(debug)
            raise Exception

        ## Species with `maxobs_per_taxon` discrete locations
        ## Sample one observation per discrete location

        species_ncell_equal_upperbound = list(ncell_per_species[ncell_per_species == maxobs_per_taxon].index)

        printv(f'** Sample one observation per sampled location for species with at least {maxobs_per_taxon} distinct locations', verbose=verbose, indent=indent)
        printv(f'INFO | {len(species_ncell_equal_upperbound)} species', verbose=verbose, indent=indent + '   ')

        if len(species_ncell_equal_upperbound) > 0:
            condition = location_sample[speciesidkey].isin(species_ncell_equal_upperbound)
            downsample_indices += location_sample[condition].groupby([speciesidkey,'cell'])['index'].sample(n=1, random_state=downsample_seed).tolist()

        ## Species with fewer than `maxobs_per_taxon` discrete locations

        species_ncell_below_upperbound = list(ncell_per_species[ncell_per_species < maxobs_per_taxon].index)

        printv(f'** Sample {maxobs_per_taxon} observations evenly accross locations for species with fewer than {maxobs_per_taxon} distinct locations', verbose=verbose, indent=indent)
        printv(f'INFO | {len(species_ncell_below_upperbound)} species', verbose=verbose, indent=indent + '   ')

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

                increment_nsamples = (nsamples_remaining_per_species.loc[species_above] // ncell_per_species.loc[species_above]).values
                nsamples_per_species_per_cell.loc[species_cell_above] += increment_nsamples
                nsamples_per_species_per_cell.loc[species_cell_above] = (nsamples_per_species_per_cell.loc[species_cell_above].clip(upper=nobs_per_species_per_cell.loc[species_cell_above])).values

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
            for taxon_id, cell, nsamples in nsamples_per_species_per_cell.values:
                downsample_indices += location_sample.loc[(taxon_id, cell), 'index'].sample(n=nsamples, random_state=downsample_seed).tolist()

    # Downsample observations

    df = df.loc[downsample_indices, :]
    nobs_after = len(df)

    # Store

    printv(f'* Save to {outputfile}', verbose=verbose, indent=indent)
    df.to_csv(outputfile, sep='\t', index=False)

    printv(f'taxasubset (upperbound) | before: {nobs_before:,d}, after : {nobs_after:,d} ({nobs_after - nobs_before:,d})', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)
    printv(f'TIME | substep: {round(time.time() - start)}s', verbose=verbose, indent=indent)

    return outputfile

def plot_h3grid_sampling(df, latkey, lonkey, speciesidkey, sampled_cells, adjacent_cells, previous_sampled_cells, previous_adjacent_cells, species, resolution, step, init, export_type='image', outputdir='./', verbose=True, indent=''):

    import shapely
    import antimeridian
    import matplotlib.pyplot as plt
    from descartes import PolygonPatch
    from matplotlib.patches import Patch
    from mpl_toolkits.basemap import Basemap
    from matplotlib.collections import PatchCollection
    from matplotlib.colors import ListedColormap

    global projected_geom_cache # NEW
    try:
        projected_geom_cache
    except NameError:
        projected_geom_cache = {}

    cmap = ListedColormap(['seagreen', 'black', 'grey', 'salmon', 'orange'])
    labels = ['available', 'sampled (previous)', 'adjacent (previous)', 'sampled (current)', 'adjacent (current)']
    if export_type == 'gif':
#        dpi = 300
        dpi = 80
        figsize = (10, 8)
    else:
#        dpi = 100 * (resolution + 1)
        dpi = 150

    if init:

        plt.close()

        global basemap
        global fig
        global ax

        water = 'lightskyblue'
        earth = 'cornsilk'

        if export_type == 'gif':
            figsize = (10, 8)
            fontsize = 10
        else:
            figsize = (12, 10)
            fontsize = 11
        fig, ax = plt.subplots(figsize=figsize)
#        fig, ax = plt.subplots(figsize=(30,25))

        basemap = Basemap(
                          llcrnrlat = -80,
                          urcrnrlat = 80,
                          llcrnrlon = -180,
                          urcrnrlon = 180,
                          projection = 'merc',
                          resolution = 'i',
                          ellps = 'WGS84',
                          ax = ax
                         )

        basemap.drawcoastlines()
        basemap.drawcountries()
        basemap.drawmapboundary(fill_color=water)
        _ = basemap.fillcontinents(color=earth,lake_color=water)

        legend_elements = []
        for i in range(len(labels)):
            legend_elements.append(Patch(facecolor=cmap(i), edgecolor='white', label=labels[i]))
        ax.legend(handles=legend_elements, loc='lower right', title='CELL STATUS', fontsize=(fontsize - 1), title_fontsize=fontsize) # fontsize = 16

    df_plot = df[['cell', latkey, lonkey]].copy()
    df_plot = df_plot.groupby(['cell'])[[latkey, lonkey]].mean().reset_index()

    adjacent_cells = set(adjacent_cells - previous_adjacent_cells - sampled_cells)
    previous_adjacent_cells = set(previous_adjacent_cells - previous_sampled_cells)
    sampled_cells = set(sampled_cells - previous_sampled_cells)

    df_plot['set'] = 0
    df_plot.loc[df_plot['cell'].isin(previous_sampled_cells),'set'] = 1
    df_plot.loc[df_plot['cell'].isin(previous_adjacent_cells),'set'] = 2
    df_plot.loc[df_plot['cell'].isin(sampled_cells),'set'] = 3
    df_plot.loc[df_plot['cell'].isin(adjacent_cells),'set'] = 4

    df_plot = df_plot.set_index('cell').h3.h3_to_geo_boundary().reset_index()

    patches = []
    colors = []
    cells = df_plot['cell'].to_numpy()
    geoms = df_plot.geometry.to_list()
    sets  = df_plot['set'].to_numpy()

#    for i, polygon in enumerate(df_plot.geometry):
    for cell, polygon, set_id in zip(cells, geoms, sets):
        if cell not in projected_geom_cache:
            polygon = antimeridian.fix_polygon(polygon)
            projected_geom_cache[cell] = shapely.ops.transform(basemap, polygon)
#        polygon = antimeridian.fix_polygon(polygon)
#        mpoly = shapely.ops.transform(basemap, polygon)
#        patches.append(PolygonPatch(mpoly))
        patches.append(PolygonPatch(projected_geom_cache[cell]))
#        colors.append(cmap(df_plot.loc[i,'set']))
        colors.append(cmap(set_id))

    p = PatchCollection(patches, alpha=0.8, edgecolor='white', linewidths=0.5, zorder=2, facecolors=colors)
    ax.add_collection(p)
    title = ax.set_title(f'SPECIES: {species} - RES: {resolution:02} - STEP: {step:02}')

    outputfile = os.path.join(outputdir, f'{species}_RES{resolution:02}_STEP{step:02}.png')
    if export_type != 'gif':
        printv(f'INFO | save to {outputfile}', verbose=verbose, indent=indent)
    plt.savefig(outputfile, dpi=dpi, bbox_inches='tight')

    p.remove()

    return None

@export
def create_gif_h3grid_sampling(outputdir, species, export_type='gif', duration=2000, verbose=True, indent=''):

    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    images = sorted(glob.glob(os.path.join(outputdir,f'{species}*')))
    frames = [Image.open(image) for image in images]

    if (export_type == 'both'):
        for i, frame in enumerate(frames[1:]):
            frames[i+1] = frames[i+1].resize(frames[0].size)

    gif_path = os.path.join(outputdir, f'{species}_H3grid_sampling.gif')
    printv(f'INFO | save to {gif_path}', verbose=verbose, indent=indent)
    frames[0].save(gif_path, format="GIF", append_images=frames[1:], save_all=True, duration=duration)

    if (export_type == 'gif'):
        for image in images:
            os.remove(image)

    return None

@export
def apply(inputfile, limit, latkey, lonkey, sep='\t', speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, resolution=8, downsample_seed=None, dtypesfile=None, outputdir='./', outputfile=None, export_process=False, export_type='gif', verbose=True, verbose_level=2, indent=''):

    if export_process:
        if export_type not in {'gif', 'both', 'image'}:
            raise ValueError(f"`taxasubset.py` | Invalid export_type '{export_type}'. Valid values are: 'gbif', 'both', 'image'.")

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
                  'downsample_seed': downsample_seed,
                  'verbose': verbose,
                  'verbose_level': verbose_level,
                  'indent': indent
                 }

        outputfile = downsample_observations(df, **params)

    else:

        printv(
                f"WARNING | Insufficient available memory: "
                f"{convertbytes.apply(available_memory)} available, "
                f"at least {convertbytes.apply(required_memory)} required. "
                f"Distributed computation is not yet implemented."
                f"Processing aborted.",
                verbose=verbose,
                indent=indent
             )

        outputfile = inputfile

    return outputfile

