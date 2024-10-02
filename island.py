#!/usr/bin/python3

import sys
import os
import glob
import argparse
import time
import random
from multiprocessing import Pool

import numpy as np
import pandas as pd
from tqdm import tqdm
from mpl_toolkits.basemap import Basemap
from matplotlib.path import Path
import pathlib
import socket
from functools import partial


_path = pathlib.Path(__file__).parent.resolve()
print(_path)

# Load the mask data.
print("Preliminary step | Loading GLOBE mask")
_mask_filename = os.path.join(_path,'globe_mask_coastline.npz')
print(os.path.join(_path,'globe_mask_coastline.npz'))

_mask_fid = np.load(_mask_filename)

_mask = _mask_fid['mask']
_lat = _mask_fid['lat']
_lon = _mask_fid['lon']

#Create the basemap map.
print("Preliminary step | Loading Basemap map")
_basemap = Basemap(
  area_thresh=1,
  resolution="f",
  llcrnrlon=-180,
  llcrnrlat=-80.,
  urcrnrlon=180,
  urcrnrlat=80
)
print("Preliminary step | Creating land polygons")
_polygons = [Path(p.boundary) for p in _basemap.landpolygons]


def lat_to_index(lat):
    """
    Convert latitude to index on the mask

    Parameters
    ----------
    lat : numeric
        Latitude to get in degrees

    Returns
    -------
    index : numeric
        index of the latitude axis.

    """
    lat = np.array(lat)

    if np.any(lat>90):
        raise ValueError('latitude must be <= 90')

    if np.any(lat<-90):
        raise ValueError('latitude must be >= -90')


    lat[lat > _lat.max()] = _lat.max()
    lat[lat < _lat.min()] = _lat.min()

    return ((lat - _lat[0])/(_lat[1]-_lat[0])).astype('int')


def lon_to_index(lon):
    """
    Convert longitude to index on the mask

    Parameters
    ----------
    lon : numeric
        Longitude to get in degrees

    Returns
    -------
    index : numeric
        index of the longitude axis.

    """

    lon = np.array(lon)

    if np.any(lon > 180):
        raise ValueError('longitude must be <= 180')

    if np.any(lon < -180):
        raise ValueError('longitude must be >= -180')


    lon[lon > _lon.max()] = _lon.max()
    lon[lon < _lon.min()] = _lon.min()


    return ((lon - _lon[0]) / (_lon[1] - _lon[0])).astype('int')


def is_land_basemap(lat,lon):
    """

    Return boolean array of whether the coordinates are on land or at sea.
    Code from Basemap documentation. 
    See: https://basemaptutorial.readthedocs.io/en/latest/utilities.html#is-land

    Parameters
    ----------
    lat : ndarray or float

        latitude in degrees

    lon : ndarray or float

        longitude in degrees

    Returns
    -------
    is_land_mask : ndarray or float

        boolean array denoting whether the corresponding point is on land.

    """
    x, y = _basemap(lon, lat)
    locations = np.c_[x, y]
    
    result = np.zeros(len(locations), dtype=bool) 

    for polygon in _polygons:
        result += np.array(polygon.contains_points(locations))
    
    return result


def is_land(lat,lon):
    """

    Return boolean array of whether the coordinates are on land or at sea. 
    Following an approach suggested by:
    Karin, Todd. Global Land Mask. October 5, 2020. https://doi.org/10.5281/zenodo.4066722
    See: https://github.com/toddkarin/global-land-mask/tree/master

    Parameters
    ----------
    lat : ndarray or float

        latitude in degrees

    lon : ndarray or float

        longitude in degrees

    Returns
    -------
    is_land_mask : ndarray or float

        boolean array denoting whether the corresponding point is on land.

    """
    lat_i = lat_to_index(lat)
    lon_i = lon_to_index(lon)

    print(f"    STEP N°1 | Using GLOBE mask")
    land_points = np.logical_not(_mask[lat_i,lon_i])

    coastline_i = np.where(_mask[lat_i,lon_i]==2)[0]
    print(f"    {len(coastline_i)} observations on coast")
    if len(coastline_i)!=0:
        print(f"    STEP N°2 | Using basemap & GSHHS coastline data")
        land_points[coastline_i] = is_land_basemap(lat[coastline_i],lon[coastline_i])

    df = pd.DataFrame(land_points, columns=["is_land"])
    df["latitude"]=lat
    df["longitude"]=lon
    df["mask"]=_mask[lat_i,lon_i]

    return df


def process_one_file(filepath, sep='\t', outputdir='./', store_time=True):

    sep=sep.encode('utf-8').decode('unicode_escape')

    start = time.time()

    base = os.path.basename(filepath)
    hostname = socket.gethostname().split(".")[0]

    res = os.path.join(outputdir,f"{base}_{hostname}")

    if len(glob.glob(f"{base}_*"))>0:
        return '0\n'

    print("Processing " + filepath)

    data = pd.read_csv(filepath, sep=sep, engine='python')
    data_processed = is_land(data["decimalLatitude"],data["decimalLongitude"])
    data_processed["index"] = data["index"].values

    print(f"    Done | Saving as {res}")
    data_processed.to_csv(res, index=False, sep=sep, encoding='utf-8')

    span = np.round((time.time() - start),2)
    print("--- %s seconds ---" % span)
    if store_time:
        span = str(span)+'\n'
        timefilepath = os.path.join(outputdir,f"time_{base}")
        with open(timefilepath, 'a+', encoding='utf-8') as f:
            f.write(span)

    del data
    del data_processed

    return str(span)+'\n'


def display_progress(inputdir, outputdir):

    files2process = [file for file in os.listdir(inputdir)]
    todo = len(files2process)

    processedfiles = [file for file in os.listdir(outputdir) if 'time' not in file]
    processedfiles = pd.DataFrame(np.array(processedfiles).reshape(-1,1), columns=["filename"])
    processedfiles = processedfiles["filename"].str.split('_').str[:-1]
    processedfiles = processedfiles.unique()
    done = len(processedfiles)

    print(f"{done}/{todo} ({np.round(done/todo,4)*100}%) files processed")

    return True


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Identify locations in the ocean')
    parser.add_argument('inputdir', type=str, help='path to directory containing files to be processed')
    parser.add_argument('--delimiter', type=str, help='file delimiter', default='\t')
    parser.add_argument('--outputpath', type=str, help='path to folder where output files will be stored', default='./')
    parser.add_argument('--store_time', action='store_true', help='store processing time')
    args = parser.parse_args()

    inputdir = args.inputdir
    sep = args.delimiter
    outputdir = os.path.join(args.outputpath,'processed')
    store_time = args.store_time

    try:
        os.mkdir(outputdir)
    except:
        pass

    fileslist = [os.path.join(inputdir,file) for file in os.listdir(inputdir)]
    random.shuffle(fileslist)

    with Pool(16) as p:
        lo = p.map(partial(process_one_file, sep=sep, outputdir=outputdir, store_time=store_time), fileslist)

    if store_time:

        files2process = [os.path.join(outputdir,file) for file in os.listdir(outputdir) if 'time' in file]

        outputfile = os.path.join(outputdir,'time')

        init=True
        for filepath in files2process:

            print(filepath)
            content = pd.read_csv(filepath, names=["time"])
            content["file"] = os.path.basename(filepath)
            if init:
                timefile = content.copy()
                init=False
            else:
                timefile = pd.concat([timefile,content], ignore_index=True, axis=0)
            print(timefile)
            os.remove(filepath)

        timefile.to_csv(outputfile, mode='w', index=False)
