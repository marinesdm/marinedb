#!/usr/bin/python
# coding: utf-8

# External import

import os
import pandas as pd

# Internal import

from marinedb.tools.marineloc import createmask
from marinedb.tools.marineloc import createmarinefilter
from marinedb.tools.marineloc import filtermarinelocations

# Global variables

__all__ = ['apply']

CHUNKSIZE = 100000

def apply(datafile, latkey, lonkey, idxkey='', uncompressed_chunks_dir='',  sep='\t', fileslist=None, kernel_type=None, kernel_size=None, maskfile=None, outputdir='', store_time=True, parallel=False, cpu=None, filterfile='marine_filter', outputfile='', indent=''):

    # Split the file into CHUNKSIZE-line chunks

    if (len(uncompressed_chunks_dir) == 0):
        uncompressed_chunks_dir = os.path.join(os.path.dirname(datafile), 'split')

    if (not os.path.isdir(uncompressed_chunks_dir)):
        os.mkdir(uncompressed_chunks_dir)

    if (len(os.listdir(uncompressed_chunks_dir)) == 0):

        print(indent + f'* Split {datafile} into {CHUNKSIZE}-lines chunks')
        print()

        isindex = (len(idxkey) != 0)
        if not isindex:
            idxkey = 'index'

        i = 0
        basename = os.path.basename(datafile).split('.')[0]
        with pd.read_csv(datafile, sep='\t', chunksize=CHUNKSIZE) as reader:
            for chunk in reader:
                if not isindex:
                    chunk = chunk.reset_index()
                chunkpath = os.path.join(uncompressed_chunks_dir, basename + '_split%04d' % i)
                print(indent + '   ' + f'>>> store {chunkpath}')
                chunk[[latkey, lonkey, idxkey]].to_csv(chunkpath, sep='\t', index=False)
                i += 1
        print()
    else:
        if len(idxkey) == 0:
            raise ValueError('`marineloc.py` | `idxkey` must be specified when `datafile` has already been split into multiple files')

    if len(outputdir) == 0:
        outputdir = os.path.join(uncompressed_chunks_dir,'marineloc')
        try:
            os.mkdir(outputdir)
        except FileExistsError:
            pass

    # Generate a mask differentiating land, sea, and coast

    if (kernel_type is not None) and (kernel_size is not None):

        print(indent + '** createmask')
        print()

        if maskfile is not None:

            print(indent + 'INFO | Since `maskfile` is provided, `mask_type` and `mask_size` will be ignored')

        else:

            params_mask = {
                           'kernel_type': kernel_type,
                           'kernel_size': kernel_size,
                           'outputdir': outputdir,
                           'indent': indent + '   '
                          }

            maskfile = createmask.apply(**params_mask)

            print()

    # Extract indices corresponding to marine occurrences

    print(indent + '** createmarinefilter')
    print()

    params_marinefilter = {
                           'inputdir': uncompressed_chunks_dir,
                           'fileslist': fileslist,
                           'latkey': latkey,
                           'lonkey': lonkey,
                           'idxkey': idxkey,
                           'sep': sep,
                           'maskfile': maskfile,
                           'outputdir': outputdir,
                           'outputfile': filterfile,
                           'parallel': parallel,
                           'cpu': cpu,
                           'store_time': store_time,
                           'indent': indent + '   '
                          }

    filterfile = createmarinefilter.apply(**params_marinefilter)

    print()

    # Filter for marine occurrences

    print(indent + '** filtermarinelocations')
    print()

    params_filterdata = {
                         'inputfile': datafile,
                         'filterfile': filterfile,
                         'inputfile_sep': sep,
                         'filter_sep': sep,
                         'outputpath': outputfile,
                         'indent': indent  + '   '
                        }

    outputfile = filtermarinelocations.apply(**params_filterdata)

    return outputfile
