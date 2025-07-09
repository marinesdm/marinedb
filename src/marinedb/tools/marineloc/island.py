#!/usr/bin/python
# coding: utf-8

# from: https://basemaptutorial.readthedocs.io/en/latest/utilities.html#is-land
# from: https://github.com/toddkarin/global-land-mask/tree/master

# External import

import os
import glob
import time
import random
import socket
import pathlib
import argparse
import numpy as np
import pandas as pd
import seaborn as sns
from functools import partial
import matplotlib.pyplot as plt
from matplotlib.path import Path
from multiprocessing import Pool
from os.path import join, isfile
from importlib.resources import files
from mpl_toolkits.basemap import Basemap

# Internal import

from marinedb.utils import resolvepath
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variables

__all__ = [] # populated using the @export decorator


# Processing


def setup(mask_filepath=None, verbose=True, indent=''):

    if mask_filepath is None:
        _mask_filename = files('marinedb.tools.data').joinpath('globe_mask_coastline.npz')
    else:
        _mask_filename = mask_filepath

    # Load the mask data

    printv(f'* Load GLOBE mask ({_mask_filename})', verbose=verbose, indent=indent)

    _mask_fid = np.load(_mask_filename)

    global _mask
    global _lat
    global _lon

    _mask = _mask_fid['mask'].copy()
    _lat = _mask_fid['lat'].copy()
    _lon = _mask_fid['lon'].copy()

    del _mask_fid

    # Create the basemap map

    printv('* Load Basemap map', verbose=verbose, indent=indent)

    global _basemap

    _basemap = Basemap(
      area_thresh=1,
      resolution='f',
      llcrnrlon=-180,
      llcrnrlat=-80.,
      urcrnrlon=180,
      urcrnrlat=80
    )

    printv('* Create land polygons', verbose=verbose, indent=indent)

    global _polygons

    _polygons = [Path(p.boundary) for p in _basemap.landpolygons]

    global _lat_exclusion
    global _lon_exclusion

    _lat_exclusion = lat_to_index(49.102040)
    _lon_exclusion = lon_to_index(6.214525)

    return True


def lat_to_index(lat, verbose=True, indent=''):

    """
    Convert latitude to its corresponding index on the mask

    Parameters
    ----------
    lat : numeric
        Latitude in degrees

    Returns
    -------
    numeric
        Index in the mask corresponding to the specified latitude

    """

    step = (_lat[1] - _lat[0])
    exclusion_value = (_lat[0] - step)

    lat = np.array(lat)

    if np.any(lat < -90):
        printv(f'WARNING | ValueError: latitude < -90 detected - line(s) excluded', verbose=verbose, indent=indent)
        lat[lat < -90] = -1000

    if np.any(lat > 90):
        printv(f'WARNING | ValueError: latitude > 90 detected - line(s) excluded', verbose=verbose, indent=indent)
        lat[lat > 90] = -1000

    if np.any(pd.isnull(lat)):
        printv(f'WARNING | ValueError: missing latitude detected - line(s) excluded', verbose=verbose, indent=indent)
        lat[pd.isnull(lat)] = -1000

    lat[lat > _lat.max()] = _lat.max()
    lat[(lat < _lat.min()) & (lat != -1000)] = _lat.min()

    lat[(lat == -1000)] = exclusion_value

    return ((lat - _lat[0]) / step).astype('int')


def lon_to_index(lon, verbose=True, indent=''):

    """
    Convert longitude to its corresponding index on the mask

    Parameters
    ----------
    lon : numeric
        Longitude in degrees

    Returns
    -------
    numeric
        Index in the mask corresponding to the specified longitude

    """

    step = (_lon[1] - _lon[0])
    exclusion_value = (_lon[0] - step)

    lon = np.array(lon)

    if np.any(lon < -180):
        printv(f'WARNING | ValueError: longitude < -180 detected - line(s) excluded', verbose=verbose, indent=indent)
        lon[lon < -180] = -1000

    if np.any(lon > 180):
        printv(f'WARNING | ValueError: longitude > 180 detected - line(s) excluded', verbose=verbose, indent=indent)
        lon[lon > 180] = -1000

    if np.any(pd.isnull(lon)):
        printv(f'WARNING | ValueError: missing longitude detected - line(s) excluded', verbose=verbose, indent=indent)
        lon[pd.isnull(lon)] = -1000

    lon[lon > _lon.max()] = _lon.max()
    lon[(lon < _lon.min()) & (lon != -1000)] = _lon.min()

    lon[(lon == -1000)] = exclusion_value

    return ((lon - _lon[0]) / step).astype('int')

@export
def island_basemap(lat, lon):

    """

    Return a boolean array indicating whether the coordinates are on land or at sea.
    Code from Basemap documentation.
    See: https://basemaptutorial.readthedocs.io/en/latest/utilities.html#is-land

    Parameters
    ----------
    lat : ndarray or float

        Latitude in degrees

    lon : ndarray or float

        Longitude in degrees

    Returns
    -------
    ndarray or float

        Boolean array denoting whether the corresponding point is on land.

    """

    x, y = _basemap(lon, lat)
    locations = np.c_[x, y]

    result = np.zeros(len(locations), dtype=bool)

    for polygon in _polygons:
        result += np.array(polygon.contains_points(locations))

    return result

@export
def island(lat, lon, verbose=True, indent=''):

    """

    Return a boolean array indicating whether the coordinates are on land or at sea.
    Following an approach suggested by:
    Karin, Todd. Global Land Mask. October 5, 2020. https://doi.org/10.5281/zenodo.4066722
    See: https://github.com/toddkarin/global-land-mask/tree/master

    Parameters
    ----------
    lat : ndarray or float

        Latitude in degrees

    lon : ndarray or float

        Longitude in degrees

    Returns
    -------
    ndarray or float

        Boolean array denoting whether the corresponding point is on land.

    """

    lat_i = lat_to_index(lat, verbose=verbose, indent=indent)
    lon_i = lon_to_index(lon, verbose=verbose, indent=indent)

    # Exclude records with missing or invalid latitude and/or
    # longitude by assigning them a default land-based location

    lat_i[lat_i < 0] = _lat_exclusion
    lon_i[lat_i < 0] = _lon_exclusion

    lat_i[lon_i < 0] = _lat_exclusion
    lon_i[lon_i < 0] = _lon_exclusion

    # Step n°1: Use land/sea/coast mask to classify the most
    # easily distinguishable coordinate pairs

    printv(f'STEP N°1 | GLOBE mask', verbose=verbose, indent=indent)
    land_points = np.logical_not(_mask[lat_i,lon_i])

    # Step n°2: Use Basemap & GSHHS coastlines to classify
    # coordinates near the coast, i.e where land/sea
    # classification is ambiguous

    coastline_i = np.where(_mask[lat_i,lon_i] == 2)[0]
    if len(coastline_i) != 0:
        printv(f'STEP N°2 | Basemap & GSHHS coastline data ({len(coastline_i)} coastal observations)', verbose=verbose, indent=indent)
        land_points[coastline_i] = island_basemap(lat[coastline_i],lon[coastline_i])

    df = pd.DataFrame(land_points, columns=['island'])
    df['latitude'] = lat
    df['longitude'] = lon
    df['mask'] = _mask[lat_i,lon_i]

    return df

@export
def process_one_file(filepath, latkey, lonkey, idxkey, controlkey=None, sep='\t', outputdir='./', store_time=True, parallel=False, mask_filepath=None, verbose=True, indent='', cluster_mode=False):

    outputdir = resolvepath(outputdir)

    verbose_func = (not parallel)

    if '_mask' not in globals():
        setup(mask_filepath=mask_filepath, verbose=verbose, indent=indent)

    sep = sep.encode('utf-8').decode('unicode_escape')
    start = time.time()

    base = os.path.basename(filepath)
    hostname = socket.gethostname().split('.')[0]
    res = join(outputdir,f'{base}_{hostname}')

    procfiles = join(outputdir,f'{base}_*')
    if len(glob.glob(procfiles)) > 0:
        return '0\n'

    printv('* Processing ' + filepath, verbose=verbose_func, indent=indent)

    data = pd.read_csv(filepath, sep=sep, engine='python')
    data_processed = island(data[latkey], data[lonkey], verbose=verbose_func, indent=indent)
    data_processed['index'] = data[idxkey].values
    if (controlkey is not None) and (len(controlkey) != 0):
        data_processed[controlkey] = data[controlkey]

    printv(f'>>> save to {res}', verbose=verbose_func, indent=indent)

    columns = ['index','latitude','longitude','mask','island']
    if (controlkey is not None) and (len(controlkey) != 0):
        columns.append(controlkey)
    data_processed[columns].to_csv(res, index=False, sep=sep, encoding='utf-8')

    span = round((time.time() - start),2)
    printv('--- %s seconds ---' % span, verbose=verbose_func, indent=indent)
    if store_time:
        span = str(span)+'\n'
        timefilepath = join(outputdir, f'time_{base}')
        with open(timefilepath, 'a+', encoding='utf-8') as f:
            f.write('\t'.join([hostname, span]))

    del data
    del data_processed

    # Display progress

    if parallel and verbose:
        print('#', end='', flush=True)

    return str(span)+'\n'

@export
def apply(inputdir, latkey, lonkey, idxkey, sep='\t', fileslist=None, maskfile=None, outputdir='', store_time=True, parallel=False, cpu=None, verbose=True, indent='', controlkey=None, cluster_mode=False):

    if cluster_mode:
        verbose = False

    sep = sep.encode('utf-8').decode('unicode_escape')

    inputdir = resolvepath(inputdir)
    if not os.path.isdir(inputdir):
        raise FileNotFoundError(f'`island.py` | Directory specified for `inputdir` not found: {inputdir}')

    if (fileslist is not None) and (len(fileslist) == 0):
        fileslist = None
    if fileslist is not None:
        if not isinstance(fileslist, str):
            raise TypeError(f'`island.py` | `fileslist` must be a string path')
        fileslist = resolvepath(fileslist)
        if not os.path.exists(fileslist):
            raise FileNotFoundError(f'`island.py` | File specified for `fileslist` not found: {fileslist}')

    if (maskfile is not None) and (len(maskfile) == 0):
        maskfile = None
    if maskfile is not None:
        if not isinstance(maskfile, str):
            raise TypeError(f'`island.py` | `maskfile` must be a string path')
        maskfile = resolvepath(maskfile)
        if not os.path.exists(maskfile):
            raise FileNotFoundError(f'`island.py` | File specified for `maskfile` not found: {maskfile}')

    if (fileslist is None):
        fileslist = [join(inputdir,file) for file in os.listdir(inputdir) if isfile(join(inputdir,file))]
    else:
        printv(f'INFO | Only the files listed in {fileslist} will be processed', verbose=verbose, indent=indent)
        with open(fileslist,'r') as file:
            temp = file.read().splitlines()
        fileslist = [join(inputdir,file) if (os.path.dirname(file) == '') else file for file in temp]

    if len(outputdir) == 0:
        outputdir = inputdir
    else:
        outputdir = resolvepath(outputdir)
    if 'processed' not in outputdir.split('/'):
        outputdir = join(outputdir,'processed')
    try:
        os.mkdir(outputdir)
    except:
        pass

    if (cpu is None) or (cpu == -1):
        if parallel:
            cpu = len(os.sched_getaffinity(0))
        else:
            cpu = 1
    cpu = min(cpu,len(fileslist))
    if cpu == 1:
        parallel = False

    params = {
              'latkey': latkey,
              'lonkey': lonkey,
              'idxkey': idxkey,
              'sep': sep,
              'outputdir': outputdir,
              'store_time': store_time,
              'parallel': parallel,
              'verbose': verbose,
              'indent': indent,
              'mask_filepath': maskfile,
              'controlkey': controlkey,
              'cluster_mode': cluster_mode
             }

    # Create global variables

    setup(mask_filepath=maskfile, verbose=verbose, indent=indent)

    # Parallelize the processing of `process_one_file`

    # This script is intended to be executed across multiple machines in parallel,
    # with each machine utilizing multiple CPUs.The shuffling process ensures that
    # no two machines process the same file simultaneously. The shuffling would not
    # be necessary if the script is to run on only a single machine
    # see `parallel_island.sh`
    random.shuffle(fileslist)

    printv(f'Processing {len(fileslist)} files on {cpu} CPUs', verbose=verbose, indent=indent)

    start = time.time()

    if parallel:
        with Pool(cpu) as p:
            p.map(partial(process_one_file, **params), fileslist)
    else:
        for filepath in fileslist:
            _ = process_one_file(filepath, **params)

    end = time.time()

    if parallel:
        printv('', verbose=verbose, indent=indent)
    printv(f'TIME : {round(end - start,0)}s', verbose=verbose, indent=indent)

    return outputdir

# Progress monitoring

@export
def compute_status(inputdir, outputdir, fileslistpath=None):

    if fileslistpath is None:
        files2process = [file for file in os.listdir(inputdir) if isfile(join(inputdir,file))]
    else:
        file = open(fileslistpath,'r')
        fileslist = file.read().splitlines()
        file.close()
        files2process = [os.path.basename(file) for file in fileslist if isfile(file)]

    processedfiles = [file for file in os.listdir(outputdir) if isfile(join(outputdir,file)) and ('time' not in file) and ('filter' not in file)]
    processedfiles = pd.DataFrame(np.array(processedfiles).reshape(-1,1), columns=['filename'])
    processedfiles = processedfiles['filename'].str.split('_').str[:-1].str.join('_')
    processedfiles = list(processedfiles.unique())

    return files2process, processedfiles

@export
def display_progress(inputdir, outputdir):

    files2process, processedfiles = compute_status(inputdir, outputdir)
    processedfiles = list(set(files2process).intersection(processedfiles))

    todo = len(files2process)
    done = len(processedfiles)

    print(f'{done}/{todo} ({np.round(done/todo,4)*100}%) files processed')

    return True

@export
def list_unprocessed_files(inputdir, outputdir):

    files2process, processedfiles = compute_status(inputdir, outputdir)
    remaining_files = list(set(files2process) - set(processedfiles))

    remaining_files = [str(join(inputdir,file)) for file in remaining_files]

    with open(join(os.path.dirname(outputdir),'remaining_files.txt'),'w') as f:
        f.write('\n'.join(remaining_files))

    return True


# Analysis of results

## Times

@export
def concat_times(inputdir, outputfile='time.txt', delete=False, overwrite=False):

    files2process = [join(inputdir,file) for file in os.listdir(inputdir) if 'time_' in file]

    if os.path.dirname(outputfile) == '':
        directory = join(inputdir,'stats')
        try:
            os.mkdir(directory)
        except FileExistsError:
            pass
        outputfile = join(directory,outputfile)

    if isfile(outputfile):
        if not overwrite:
            count = 0
            outputfile_temp = outputfile
            outputfile = outputfile.split('.')
            while isfile(outputfile_temp):
                count += 1
                outputfile_temp = outputfile[0] + f'{count:02}'
                if len(outputfile) == 2:
                    outputfile_temp += f'.{outputfile[1]}'
            outputfile = outputfile_temp
        else:
            print(f'WARNING | {ouputfile} will be overwritten')

    print(f'* Store times in {outputfile}')

    init = True
    columns = ['filename_input', 'machine','time']
    for filepath in files2process:

        content = pd.read_csv(filepath, sep='\t', names=['machine','time'])
        content['filename_input'] = '_'.join(os.path.basename(filepath).split('_')[1:])

        if init:
            times = content[columns].copy()
            init = False
        else:
            times = pd.concat([times[columns],content[columns]], ignore_index=True, axis=0)

        if delete:
            os.remove(filepath)

    times['hour'] = (times['time']/60)/60
    times['minute'] = np.floor((times['hour'] - np.floor(times['hour']))*60)
    times['hour'] = np.floor(times['hour'])
    times[['hour','minute']] = times[['hour','minute']].astype(int)

    times[columns + ['hour','minute']].to_csv(outputfile, sep='\t', mode='w', index=False)

    return times

## Land/sea/coast statistics

@export
def land_sea_statistics(inputdir, outputfile='statistics.txt', sep='\t', overwrite=False):

    sep = sep.encode('utf-8').decode('unicode_escape')

    files = [join(inputdir,file) for file in os.listdir(inputdir) if ('split' in file) and ('time' not in file)]

    # Compute statistics

    print(f'* Compute land/sea/coast statistics ({len(files)} files)')

    stats=[]
    for filepath in files:

        df = pd.read_csv(filepath, sep=sep)
        filestats = df['mask'].value_counts().sort_index()
        mask = filestats.index.astype(int)
        filestats = filestats.tolist()

        if 0 not in mask:
            filestats.insert(0,0)
        if 1 not in mask:
            filestats.insert(1,0)
        if 2 not in mask:
            filestats.insert(2,0)

        filename = os.path.basename(filepath)
        filestats.insert(0,filename)
        filename = '_'.join(filename.split('_')[:-1])
        filestats.insert(1,filename)

        res_island = df['island'].value_counts().sort_index()
        islandbool = res_island.index.astype(int)
        res_island = res_island.tolist()

        if 0 not in islandbool:
            res_island.insert(0,0)
        if 1 not in islandbool:
            res_island.insert(1,0)

        filestats += res_island

        stats.append(filestats)

        del df

        if ((len(stats)+1)%100) == 0:
            print(f'Processing | {len(stats)+1} files done')

    stats = pd.DataFrame(stats, columns=['filename_output','filename_input','mask_0','mask_1','mask_2','sea','land'])
    stats['pct_coast'] = np.round(stats['mask_2']/stats[['mask_0','mask_1','mask_2']].sum(axis=1),2)

    # Store

    if os.path.dirname(outputfile) == '':
        directory = join(inputdir,'stats')
        try:
            os.mkdir(directory)
        except FileExistsError:
            pass
        outputfile = join(directory,outputfile)

    if isfile(outputfile):
        if not overwrite:
            count = 0
            outputfile_temp = outputfile
            outputfile = outputfile.split('.')
            while isfile(outputfile_temp):
                count += 1
                outputfile_temp = outputfile[0] + f'{count:02}'
                if len(outputfile) == 2:
                    outputfile_temp += f'.{outputfile[1]}'
            outputfile = outputfile_temp
        else:
            print(f'WARNING | {ouputfile} will be overwritten')


    print(f'* Store land/sea/coast statistics in {outputfile}')
    stats.to_csv(outputfile, sep=sep, mode='w', index=False)

    return stats

## Plot

@export
def plot_time(df_time, show=True, store=True, outputfile='time.png', outputdir='./'):

    df_time['hour_rounded'] = round((df_time['time']/60)/60,0)
    df_time['hour_rounded'] = df_time['hour_rounded'].astype('int')
    column = 'hour_rounded'

    if len(df_time['hour_rounded'].unique()) < 3:
        column = 'minute_rounded'
        df_time['minute_rounded'] = round(df_time['time']/60,0)
        df_time['minute_rounded'] = df_time['minute_rounded'].astype('int')

    fig, axarr = plt.subplots(1, 2, figsize=(15,8), width_ratios=[1,4]) # matplotlib >= 3.6.0
    plt.tight_layout(pad=4)

    sns.boxplot(y='time', data=df_time, notch=True, showcaps=False, medianprops={'color':'coral'}, whis=[1,99], showmeans=True, ax=axarr[0])
    axarr[0].set_ylabel('')
    axarr[0].set_xlabel('time per file (seconds)')

    sns.countplot(x='hour_rounded', data=df_time, color='teal', ax=axarr[1])
    axarr[1].set_xlabel(f"time per file ({column.split('_')[0]}s)")

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
            directory = outputdir
            if 'images' not in directory.split('/'):
                directory = join(directory,'images')
            try:
                os.mkdir(directory)
            except FileExistsError:
                pass
            outputfile = join(directory,outputfile)

        fig.savefig(outputfile, bbox_inches='tight', dpi=96)

    plt.close(fig)

    return True

@export
def plot_stats(df_stats, show=True, store=True, outputfile='statistics.png', outputdir='./'):

    plt.rcParams['font.sans-serif'] = ['Tahoma', 'DejaVu Sans', 'Lucida Grande', 'Verdana']

    fig, axarr = plt.subplots(1, 2, figsize=(15,8), width_ratios=[1,2])
    plt.tight_layout(pad=4)

    df_plot = df_stats.drop_duplicates(subset=['filename_input'], ignore_index=True)
    df_plot = df_plot[['mask_0','mask_1','mask_2','sea','land']].astype('int').sum(axis=0)

    df_plot[['mask_0','mask_1','mask_2']] = np.round((df_plot[['mask_0','mask_1','mask_2']] / df_plot[['mask_0','mask_1','mask_2']].sum(axis=0))*100,1)
    df_plot[['land','sea']] = np.round((df_plot[['land','sea']] / df_plot[['land','sea']].sum(axis=0))*100,1)

    bar_container = axarr[0].bar(['land','sea','coast'], df_plot[['mask_0','mask_1','mask_2']].to_list(), alpha=0.6, color=['coral','teal','forestgreen'])
    axarr[0].set_ylabel(f'percentage')
    axarr[0].set_title('Step n°1: GLOBE mask', y=-0.08)
    axarr[0].bar_label(bar_container, fmt='%.1f%%', padding=0.07)

    bar_container = axarr[1].bar(['land','sea'], df_plot[['land','sea']].to_list(), alpha=0.6, color=['coral','teal'])
    axarr[1].set_ylabel(f'percentage')
    axarr[1].set_title('Step n°2: Basemap & GSHHS coastline data', y=-0.08)
    axarr[1].bar_label(bar_container, fmt='%.1f%%', padding=0.07)

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
            directory = outputdir
            if 'images' not in directory.split('/'):
                directory = join(outputdir,'images')
            try:
                os.mkdir(directory)
            except FileExistsError:
                pass
            outputfile = join(directory,outputfile)

        fig.savefig(outputfile, bbox_inches='tight', dpi=96)

    plt.close(fig)

    return True

@export
def plot_coast_time(df_time, df_stats, show=True, store=True, outputfile='coast_time.png', outputdir='./'):

    df_stats = df_stats.drop_duplicates(subset=['filename_input'],keep='first')
    df_time = df_time[['time','filename_input']].groupby('filename_input').agg({'time':'mean'}).reset_index()

    table = pd.merge(df_time,df_stats[['filename_input','mask_2','pct_coast']], how='inner', on='filename_input')

    ax = table.plot.scatter(x='mask_2', y='time', alpha=0.6, figsize=(30,20), s=20)
    ax.set_xlabel('number of coastal locations')
    ax.set_ylabel('time (seconds)')
    ax.ticklabel_format(style='plain')

    fig = ax.get_figure()

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
            directory = outputdir
            if 'images' not in directory.split('/'):
                directory = join(directory,'images')
            try:
                os.mkdir(directory)
            except FileExistsError:
                pass
            outputfile = join(directory,outputfile)

        fig.savefig(outputfile, bbox_inches='tight', dpi=96)

    plt.close(fig)

    return True

@export
def plot_file_redundancy(df_time, show=True, store=True, outputfile='file_redundancy.png', outputdir='./'):

    fig, ax = plt.subplots(figsize=(15,8))
    plt.tight_layout(pad=4)

    df_time_counts = df_time['filename_input'].value_counts().reset_index(drop=True).to_frame()

    sns.countplot(x='filename_input', data=df_time_counts, color='teal', ax=ax)
    ax.set_xlabel(f"number of times each file has been processed")

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
            directory = outputdir
            if 'images' not in directory.split('/'):
                directory = join(outputdir,'images')
            try:
                os.mkdir(directory)
            except FileExistsError:
                pass
            outputfile = join(directory,outputfile)

        fig.savefig(outputfile, bbox_inches='tight', dpi=96)

    plt.close(fig)

    return True

@export
def plot_process_features(inputdir, delete_times=False, sep='\t', overwrite=False, show=True, store=True, outputdir=''):

    if len(outputdir) == 0:
        outputdir = inputdir

    times = concat_times(inputdir, delete=delete_times, overwrite=overwrite)
    stats = land_sea_statistics(inputdir, sep=sep, overwrite=overwrite)

    plot_time(times, show=show, store=store, outputdir=outputdir)
    plot_stats(stats, show=show, store=store, outputdir=outputdir)
    plot_file_redundancy(times, show=show, store=store, outputdir=outputdir)
    plot_coast_time(times, stats, show=show, store=store, outputdir=outputdir)

    return times, stats

@export
def plot_island(df, latkey='latitude', lonkey='longitude', background=False, show=True, store=True, outputfile='island.png', outputdir='./'):

    fig, ax = plt.subplots(figsize=(20,15))

    # basemap >= 1.3.2 (before: missing half of Antartic coast)
    basemap = Basemap(
        llcrnrlat = -80,
        urcrnrlat = 80,
        llcrnrlon = -180,
        urcrnrlon = 180,
        projection='merc',
        resolution="l",
        ellps='WGS84'
        )

    if background:
        basemap.bluemarble(scale=0.6)
        basemap.drawcoastlines(color='white', linewidth=0.2)
        basemap.drawrivers(color='white')
        cmap = colors.ListedColormap(['green', 'red'])
    else:
        basemap.drawcoastlines()
        basemap.drawcountries()
        basemap.drawmapboundary()
        basemap.drawrivers()
        basemap.fillcontinents()
        cmap = colors.ListedColormap(['seagreen', 'salmon'])

    missing_coords = pd.isnull(df[lonkey]) | pd.isnull(df[latkey])
    invalid_coords = (df[lonkey] < -180) | (df[lonkey] > 180) | (df[latkey] < -90) | (df[latkey] > 90)
    dfviz = df[(~missing_coords) & (~invalid_coords)]

    plot = basemap.scatter(dfviz[lonkey], dfviz[latkey], latlon=True, marker="o", c=df['island'], cmap=cmap)
    plt.legend(handles=plot.legend_elements()[0], labels=('False', 'True'), title='island')

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
            directory = outputdir
            if 'images' not in directory.split('/'):
                directory = join(outputdir,'images')
            try:
                os.mkdir(directory)
            except FileExistsError:
                pass
            outputfile = join(directory,outputfile)

        fig.savefig(outputfile, bbox_inches='tight', dpi=96)

    plt.close(fig)

    return True

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Identify marine coordinates', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputdir-path', type=str, help='directory path containing files to be processed')
    parser.add_argument('--fileslist-path', type=str, help='path to the file that lists the files to be processed', default=None)
    parser.add_argument('--latitude-column', type=str, help='latitude column name', required=True)
    parser.add_argument('--longitude-column', type=str, help='longitude column name', required=True)
    parser.add_argument('--index-column', type=str, help='index column name', required=True)
    parser.add_argument('--control-column', type=str, help='control column name', default=None)
    parser.add_argument('--delimiter', type=str, help='delimiter used in the input files', default='\t')
    # Warning: delimiter must be enclosed in quotation marks
    parser.add_argument('--maskfile-path', type=str, help='path to the .npz file containing the land/sea/coast mask', default=None)
    parser.add_argument('--outputdir-path', type=str, help='path to the directory where the output files will be stored', default='./')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='whether to parallelize on multiple CPUs', default=False)
    parser.add_argument('--cpu', type=int, help='number of CPUs to be used', default=None)
    parser.add_argument('--store-time', action=argparse.BooleanOptionalAction, help='whether to store the processing times', default=True)
    parser.add_argument('--cluster-mode', action=argparse.BooleanOptionalAction, help='whether the script is parallelized across multiple machines', default=False)
    args = parser.parse_args()

    inputdir = args.inputdir_path
    fileslist_path = args.fileslist_path
    sep = args.delimiter
    latkey = args.latitude_column
    lonkey = args.longitude_column
    idxkey = args.index_column
    controlkey = args.control_column
    mask_filepath = args.maskfile_path
    outputdir = args.outputdir_path
    parallel = args.parallel
    cpu = args.cpu
    store_time = args.store_time
    cluster_mode = args.cluster_mode

    if (fileslist_path is not None) and (len(fileslist_path) == 0):
        fileslist_path = None

    if (mask_filepath is not None) and (len(mask_filepath) == 0):
        maskfile = None

    if (cpu is None) or (cpu == -1):
        cpu = len(os.sched_getaffinity(0))
    if cpu == 1:
        parallel = False

    if (controlkey is not None) and (len(controlkey) == 0):
        controlkey = None

    params = {
              'fileslist': fileslist_path,
              'latkey': latkey,
              'lonkey': lonkey,
              'idxkey': idxkey,
              'sep': sep,
              'maskfile': mask_filepath,
              'outputdir': outputdir,
              'parallel': parallel,
              'cpu': cpu,
              'store_time': store_time,
              'controlkey': controlkey,
              'cluster_mode': cluster_mode
             }

    if not cluster_mode:
        print(f'`island.py` | Identify marine coordinates')
        print()
        print('Parameters')
        print('----------')
        print(f'inputdir: {inputdir}')
        for key, value in params.items():
            print(f'{key}: {value}')
        print()

    _ = apply(inputdir, **params)
