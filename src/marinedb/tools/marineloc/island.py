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
from mpl_toolkits.basemap import Basemap

# Internal import

from marinedb.utils.allexport import export

# Global variables

__all__ = [] # populated using the @export decorator


# Processing


def setup(path=None):

    if path is None:
        _path = pathlib.Path(__file__).parent.resolve()
        _path = os.path.join(_path, 'data/')
    else:
        _path = path

    # Load the mask data

    _mask_filename = os.path.join(_path,'globe_mask_coastline.npz')

    print(f'Preliminary step | Loading GLOBE mask ({_mask_filename})')

    _mask_fid = np.load(_mask_filename)

    global _mask
    global _lat
    global _lon

    _mask = _mask_fid['mask'].copy()
    _lat = _mask_fid['lat'].copy()
    _lon = _mask_fid['lon'].copy()

    del _mask_fid

    # Create the basemap map

    print('Preliminary step | Loading Basemap map')

    global _basemap

    _basemap = Basemap(
      area_thresh=1,
      resolution='f',
      llcrnrlon=-180,
      llcrnrlat=-80.,
      urcrnrlon=180,
      urcrnrlat=80
    )

    print('Preliminary step | Creating land polygons')

    global _polygons

    _polygons = [Path(p.boundary) for p in _basemap.landpolygons]

    return True


def printv(message, verbose, indent=''):
    if verbose:
        print(indent + message)
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
def island_mask(lat,lon,parallel=False):

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

    printv(f'STEP N°1 | Using GLOBE mask', verbose=(not parallel), indent='    ')
    land_points = np.logical_not(_mask[lat_i,lon_i])

    coastline_i = np.where(_mask[lat_i,lon_i] == 2)[0]
    if len(coastline_i)!=0:
        printv(f'STEP N°2 | Using basemap & GSHHS coastline data ({len(coastline_i)} coastal observations)', verbose=(not parallel), indent='    ')
        land_points[coastline_i] = island_basemap(lat[coastline_i],lon[coastline_i])

    df = pd.DataFrame(land_points, columns=['island'])
    df['latitude'] = lat
    df['longitude'] = lon
    df['mask'] = _mask[lat_i,lon_i]

    return df

@export
def process_one_file(filepath, latkey, lonkey, idxkey, sep='\t', outputdir='./', store_time=True, parallel=False):

    if not parallel:
        setup()

    sep = sep.encode('utf-8').decode('unicode_escape')
    start = time.time()

    base = os.path.basename(filepath)
    hostname = socket.gethostname().split('.')[0]
    res = os.path.join(outputdir,f'{base}_{hostname}')

    if len(glob.glob(f'{base}_*')) > 0:
        return '0\n'

    printv('* Processing ' + filepath, verbose=(not parallel))

    data = pd.read_csv(filepath, sep=sep)
    data_processed = island_mask(data[latkey], data[lonkey], parallel=parallel)
    data_processed['index'] = data[idxkey].values

    printv(f'Done | Saving as {res}', verbose=(not parallel), indent='  ')
    data_processed.to_csv(res, index=False, sep=sep, encoding='utf-8')

    span = np.round((time.time() - start),2)
    printv('--- %s seconds ---' % span, verbose=(not parallel), indent='  ')
    if store_time:
        span = str(span)+'\n'
        timefilepath = os.path.join(outputdir, f'time_{base}')
        with open(timefilepath, 'a+', encoding='utf-8') as f:
            f.write(','.join([hostname, span]))

    del data
    del data_processed

    # Display progress

    if parallel:
        print('#', end='', flush=True)

    return str(span)+'\n'


# Progress monitoring

@export
def compute_status(inputdir, outputdir, fileslistpath=None):

    if fileslistpath is None:
        files2process = [file for file in os.listdir(inputdir)]
    else:
        file = open(fileslistpath,'r')
        fileslist = file.read().splitlines()
        file.close()
        files2process = [os.path.basename(file) for file in fileslist]

    processedfiles = [file for file in os.listdir(outputdir) if 'time' not in file]
    processedfiles = pd.DataFrame(np.array(processedfiles).reshape(-1,1), columns=['filename'])
    processedfiles = processedfiles['filename'].str.split('_').str[:-1].str.join('_')
    processedfiles = processedfiles.unique()

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

    remaining_files = [str(os.path.join(inputdir,file)) for file in remaining_files]

    with open(os.path.join(os.path.dirname(outputdir),'remaining_files.txt'),'w') as f:
        f.write('\n'.join(remaining_files))

    return True


# Analysis of results

## Times

@export
def concat_times(outputdir, outputfile='time', delete=True, overwrite=False):

    files2process = [os.path.join(outputdir,file) for file in os.listdir(outputdir) if 'time_' in file]

    if os.path.dirname(outputfile) == '':
        outputfile = os.path.join(outputdir,outputfile)

    if os.path.isfile(outputfile):
        if not overwrite:
            count = 1
            while os.path.isfile(outputfile + str(count)):
                count += 1
            outputfile = outputfile + str(count)
        else:
            print(f'WARNING | {ouputfile} will be overwritten')

    print(f'Storing times in {outputfile}')

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
def land_sea_statistics(outputdir, outputfile='statistics', sep='\t', overwrite=False):

    sep = sep.encode('utf-8').decode('unicode_escape')
    files = [os.path.join(outputdir,file) for file in os.listdir(outputdir) if ('split' in file) and ('time' not in file)]

    # Compute statistics

    print(f'Compute land/sea/coast statistics ({len(files)} files)')

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
            print(f'    Processing | {len(stats)+1} files done')

    stats = pd.DataFrame(stats, columns=['filename_output','filename_input','mask_0','mask_1','mask_2','sea','land'])
    stats['pct_coast'] = np.round(stats['mask_2']/stats[['mask_0','mask_1','mask_2']].sum(axis=1),2)

    # Store

    if os.path.dirname(outputfile) == '':
        outputfile = os.path.join(outputdir,outputfile)

    if os.path.isfile(outputfile):
        if not overwrite:
            count = 1
            while os.path.isfile(outputfile + str(count)):
                count += 1
            outputfile = outputfile + str(count)
        else:
            print(f'WARNING | {ouputfile} will be overwritten')


    print(f'Storing land/sea/coast statistics in {outputfile}')
    stats.to_csv(outputfile, sep=sep, mode='w', index=False)

    return True

## Plot

@export
def plot_time(time, show=True, store=True, outputfile='time.png', outputdir='./'):

    time['hour_rounded'] = np.round((time['time']/60)/60,0)
    time['hour_rounded'] = time['hour'].astype('int')

    fig, axarr = plt.subplots(1,2,figsize=(15,8), width_ratios=[1,4])
    plt.tight_layout(pad=4)

    sns.boxplot(y='time', data=time, notch=True, showcaps=False, medianprops={'color':'coral'}, whis=[1,99], showmeans=True, ax=axarr[0])
    #sns.swarmplot(y='time', data=time, color='black', alpha=0.5, ax=axarr[0])
    axarr[0].set_ylabel('')
    axarr[0].set_xlabel('time (seconds)')

    sns.countplot(x='hour_rounded', data=time, color='teal', ax=axarr[1])
    axarr[1].set_xlabel('time per file (hours)')

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
            outputfile = os.path.join(outputdir,outputfile)

        #fig = axarr.get_figure()
        fig.savefig(outputfile, bbox_inches='tight', dpi=96)

    plt.close(fig)

    return True

@export
def plot_coastVStime(time, stats, show=True, store=True, outputfile='coastVStime.png', outputdir='./'):

    stats = stats.drop_duplicates(subset=['filename_input'],keep='first')
    time = time[['time','filename_input']].groupby('filename_input').agg({'time':'mean'}).reset_index()

    table = pd.merge(time,stats[['filename_input','mask_2','pct_coast']],how='inner',on='filename_input')

    ax = table.plot.scatter(x='mask_2',y='time',alpha=0.6,figsize=(30,20),s=20)
    ax.set_xlabel('number of coastal locations')
    ax.set_ylabel('time (seconds)')
    ax.ticklabel_format(style='plain')

    fig = ax.get_figure()

    if show:
        plt.show()

    if store:

        if os.path.dirname(outputfile) == '':
            outputfile = os.path.join(outputdir,outputfile)

        fig.savefig(outputfile, bbox_inches='tight', dpi=96)

    plt.close(fig)

    return True


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Identify marine coordinates', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputdir_path', type=str, help='directory path containing files to be processed')
    parser.add_argument('--latitude_column', type=str, help='latitude column name', required=True)
    parser.add_argument('--longitude_column', type=str, help='longitude column name', required=True)
    parser.add_argument('--index_column', type=str, help='index column name', required=True)
    parser.add_argument('--files_list_path', type=str, help='path to the file that contains the list of files to be processed', default=None)
    parser.add_argument('--delimiter', type=str, help='delimiter used in the input files', default='\t') #!! delimiter must be enclosed in quotation marks !!
    parser.add_argument('--cpu', type=int, help='number of CPUs to be used', default=None)
    parser.add_argument('--outputdir_path', type=str, help='path to the directory where the output files will be stored', default='./')
    parser.add_argument('--store_time', action=argparse.BooleanOptionalAction, help='whether to store the processing times', default=True)
    args = parser.parse_args()

    print()
    print(f'`island.py` | Identify marine coordinates')

    inputdir = args.inputdir_path
    outputdir = args.outputdir_path
    files_list_path = args.files_list_path
    sep = args.delimiter
    latkey = args.latitude_column
    lonkey = args.longitude_column
    idxkey = args.index_column
    cpu = args.cpu
    store_time = args.store_time

    if (files_list_path is None) or (len(files_list_path) == 0):
        fileslist = [os.path.join(inputdir,file) for file in os.listdir(inputdir) if (file != 'processed')]
    else:
        print(f'INFO | Only the files listed in {files_list_path} will be processed')
        with open(files_list_path,'r') as file:
            fileslist = file.read().splitlines()
        fileslist = [os.path.join(inputdir,file) if (os.path.dirname(file) == '') else file for file in fileslist]

    if len(outputdir) == 0:
        outputdir = './'
    outputdir = os.path.join(outputdir,'processed')
    try:
        os.mkdir(outputdir)
    except:
        pass

    if (cpu is None) or (cpu == -1):
        cpu = len(os.sched_getaffinity(0))

    params = {
              'latkey': latkey,
              'lonkey': lonkey,
              'idxkey': idxkey,
              'sep': sep,
              'outputdir': outputdir,
              'store_time': store_time,
              'parallel': True,
             }

    print()
    print('Parameters')
    print('----------')
    for key, value in params.items():
        print(f'{key}: {value}')
    print(f'cpu: {cpu}')
    print()

    # Create global variables

    setup()

    # Parallelize the processing of `process_one_file`

    # This script is intended to be executed across multiple machines in parallel,
    # with each machine utilizing multiple CPUs.The shuffling process ensures that
    # no two machines process the same file simultaneously. The shuffling would not
    # be necessary if the script is to run on only a single machine
    # see `parallel_island.sh`
    random.shuffle(fileslist)

    print(f'Processing {len(fileslist)} files on {cpu} CPUs')

    start = time.time()

    with Pool(cpu) as p:
        p.map(partial(process_one_file, **params), fileslist)

    end = time.time()

    print(f'    TIME : {round(end - start,0)}s')
