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

    return True


def lat_to_index(lat):

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

    lat = np.array(lat)

    if np.any(lat > 90):
        raise ValueError('`island.py` | latitude must be <= 90')

    if np.any(lat <- 90):
        raise ValueError('`island.py` | latitude must be >= -90')

    lat[lat > _lat.max()] = _lat.max()
    lat[lat < _lat.min()] = _lat.min()

    return ((lat - _lat[0])/(_lat[1]-_lat[0])).astype('int')


def lon_to_index(lon):

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

    lon = np.array(lon)

    if np.any(lon > 180):
        raise ValueError('`island.py` | longitude must be <= 180')

    if np.any(lon < -180):
        raise ValueError('`island.py` | longitude must be >= -180')


    lon[lon > _lon.max()] = _lon.max()
    lon[lon < _lon.min()] = _lon.min()


    return ((lon - _lon[0]) / (_lon[1] - _lon[0])).astype('int')

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

    lat_i = lat_to_index(lat)
    lon_i = lon_to_index(lon)

    printv(f'STEP N°1 | GLOBE mask', verbose=verbose, indent=indent)
    land_points = np.logical_not(_mask[lat_i,lon_i])

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
def process_one_file(filepath, latkey, lonkey, idxkey, sep='\t', outputdir='./', store_time=True, parallel=False, mask_filepath=None, verbose=True, indent=''):

    outputdir = os.path.expanduser(outputdir)

    verbose_func = (not parallel)

    if '_mask' not in globals():
        setup(mask_filepath=mask_filepath, indent=indent)

    sep = sep.encode('utf-8').decode('unicode_escape')
    start = time.time()

    base = os.path.basename(filepath)
    hostname = socket.gethostname().split('.')[0]
    res = join(outputdir,f'{base}_{hostname}')

    procfiles = join(outputdir,f'{base}_*')
    if len(glob.glob(procfiles)) > 0:
        return '0\n'

    printv('* Processing ' + filepath, verbose=verbose_func, indent=indent)

    data = pd.read_csv(filepath, sep=sep)
    data_processed = island(data[latkey], data[lonkey], verbose=verbose_func, indent=indent)
    data_processed['index'] = data[idxkey].values

    printv(f'>>> save to {res}', verbose=verbose_func, indent=indent)
    data_processed[['index','latitude','longitude','mask','island']].to_csv(res, index=False, sep=sep, encoding='utf-8')

    span = np.round((time.time() - start),2)
    printv('--- %s seconds ---' % span, verbose=verbose_func, indent=indent)
    if store_time:
        span = str(span)+'\n'
        timefilepath = join(outputdir, f'time_{base}')
        with open(timefilepath, 'a+', encoding='utf-8') as f:
            f.write(','.join([hostname, span]))

    del data
    del data_processed

    # Display progress

    if parallel and verbose:
        print('#', end='', flush=True)

    return str(span)+'\n'

@export
def apply(inputdir, latkey, lonkey, idxkey, sep='\t', fileslist=None, maskfile=None, outputdir='', store_time=True, parallel=False, cpu=None, verbose=True, indent=''):

    inputdir = os.path.expanduser(inputdir)
    if not os.path.isdir(inputdir):
        raise FileNotFoundError(f'`island.py` | Directory specified for `inputdir` not found: {inputdir}')
    if fileslist is not None:
        if not isinstance(fileslist, str):
            raise TypeError(f'`island.py` | `fileslist` must be a string path')
        fileslist = os.path.expanduser(fileslist)
        if not os.path.exists(fileslist):
            raise FileNotFoundError(f'`island.py` | File specified for `fileslist` not found: {fileslist}')
    if maskfile is not None:
        if not isinstance(maskfile, str):
            raise TypeError(f'`island.py` | `maskfile` must be a string path')
        maskfile = os.path.expanduser(maskfile)
        if not os.path.exists(maskfile):
            raise FileNotFoundError(f'`island.py` | File specified for `maskfile` not found: {maskfile}')

    if (fileslist is None) or (len(fileslist) == 0):
        fileslist = [join(inputdir,file) for file in os.listdir(inputdir) if isfile(join(inputdir,file))]
    else:
        printv(f'INFO | Only the files listed in {fileslist} will be processed', verbose=verbose, indent=indent)
        with open(fileslist,'r') as file:
            temp = file.read().splitlines()
        fileslist = [join(inputdir,file) if (os.path.dirname(file) == '') else file for file in temp]

    if (maskfile is not None) and (len(maskfile) == 0):
        maskfile = None

    if len(outputdir) == 0:
        outputdir = inputdir
    else:
        outputdir = os.path.expanduser(outputdir)
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
             }

    # Create global variables

    setup(mask_filepath=maskfile, indent=indent)

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
def concat_times(inputdir, outputfile='time.csv', delete=True, overwrite=False):

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

        content = pd.read_csv(filepath, sep=',', names=['machine','time'])
        content['filename_input'] = '_'.join(os.path.basename(filepath).split('_')[1:])

        if init:
            timefile = content[columns].copy()
            init = False
        else:
            timefile = pd.concat([timefile[columns],content[columns]], ignore_index=True, axis=0)

        if delete:
            os.remove(filepath)

    timefile['hour'] = (timefile['time']/60)/60
    timefile['minute'] = np.floor((timefile['hour'] - np.floor(timefile['hour']))*60)
    timefile['hour'] = np.floor(timefile['hour'])
    timefile[['hour','minute']] = timefile[['hour','minute']].astype(int)

    timefile[columns + ['hour','minute']].to_csv(outputfile, sep=',', mode='w', index=False)

    return True

## Land/sea/coast statistics

@export
def land_sea_statistics(inputdir, outputfile='statistics', sep='\t', overwrite=False):

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
            count = 1
            while isfile(outputfile + str(count)):
                count += 1
            outputfile = outputfile + str(count)
        else:
            print(f'WARNING | {ouputfile} will be overwritten')


    print(f'* Store land/sea/coast statistics in {outputfile}')
    stats.to_csv(outputfile, sep=sep, mode='w', index=False)

    return True

## Plot

@export
def plot_time(df_time, show=True, store=True, outputfile='time.png', outputdir='./'):

    df_time['hour_rounded'] = np.round((df_time['time']/60)/60,0)
    df_time['hour_rounded'] = df_time['hour'].astype('int')

    fig, axarr = plt.subplots(1,2,figsize=(15,8), width_ratios=[1,4])
    plt.tight_layout(pad=4)

    sns.boxplot(y='time', data=df_time, notch=True, showcaps=False, medianprops={'color':'coral'}, whis=[1,99], showmeans=True, ax=axarr[0])
    #sns.swarmplot(y='time', data=df_time, color='black', alpha=0.5, ax=axarr[0])
    axarr[0].set_ylabel('')
    axarr[0].set_xlabel('time per file (seconds)')

    sns.countplot(x='hour_rounded', data=df_time, color='teal', ax=axarr[1])
    axarr[1].set_xlabel('time per file (hours)')

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
            directory = join(outputdir,'images')
            try:
                os.mkdir(directory)
            except FileExistsError:
                pass
            outputfile = join(directory,outputfile)

        #fig = axarr.get_figure()
        fig.savefig(outputfile, bbox_inches='tight', dpi=96)

    plt.close(fig)

    return True

@export
def plot_coastVStime(df_time, df_stats, show=True, store=True, outputfile='coastVStime.png', outputdir='./'):

    df_stats = df_stats.drop_duplicates(subset=['filename_input'],keep='first')
    df_time = df_time[['time','filename_input']].groupby('filename_input').agg({'time':'mean'}).reset_index()

    table = pd.merge(df_time,df_stats[['filename_input','mask_2','pct_coast']],how='inner',on='filename_input')

    ax = table.plot.scatter(x='mask_2',y='time',alpha=0.6,figsize=(30,20),s=20)
    ax.set_xlabel('number of coastal locations')
    ax.set_ylabel('time (seconds)')
    ax.ticklabel_format(style='plain')

    fig = ax.get_figure()

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
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
    parser.add_argument('inputdir_path', type=str, help='directory path containing files to be processed')
    parser.add_argument('--fileslist_path', type=str, help='path to the file that lists the files to be processed', default=None)
    parser.add_argument('--latitude_column', type=str, help='latitude column name', required=True)
    parser.add_argument('--longitude_column', type=str, help='longitude column name', required=True)
    parser.add_argument('--index_column', type=str, help='index column name', required=True)
    parser.add_argument('--delimiter', type=str, help='delimiter used in the input files', default='\t')
    # Warning: delimiter must be enclosed in quotation marks
    parser.add_argument('--maskfile_path', type=str, help='path to the .npz file containing the land/sea/coast mask', default=None)
    parser.add_argument('--outputdir_path', type=str, help='path to the directory where the output files will be stored', default='./')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='whether to parallelize on multiple CPUs', default=False)
    parser.add_argument('--cpu', type=int, help='number of CPUs to be used', default=None)
    parser.add_argument('--store_time', action=argparse.BooleanOptionalAction, help='whether to store the processing times', default=True)
    args = parser.parse_args()

    print(f'`island.py` | Identify marine coordinates')

    inputdir = args.inputdir_path
    fileslist_path = args.fileslist_path
    sep = args.delimiter
    latkey = args.latitude_column
    lonkey = args.longitude_column
    idxkey = args.index_column
    mask_filepath = args.maskfile_path
    outputdir = args.outputdir_path
    parallel = ars.parallel
    cpu = args.cpu
    store_time = args.store_time

    if (len(mask_filepath) == 0):
        maskfile = None

    if len(outputdir) == 0:
        outputdir = './'
    outputdir = join(outputdir,'processed')

    if (cpu is None) or (cpu == -1):
        cpu = len(os.sched_getaffinity(0))
    if cpu == 1:
        parallel = False

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
             }

    print()
    print('Parameters')
    print('----------')
    print(f'inputdir: {inputdir}')
    for key, value in params.items():
        print(f'{key}: {value}')
    print()

    _ = apply(inputdir, **params)
