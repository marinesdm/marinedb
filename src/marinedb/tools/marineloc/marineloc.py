#!/usr/bin/python
# coding: utf-8

# External import

import os
import glob
import pandas as pd

# Internal import

from marinedb.utils.printverbose import printv
from marinedb.utils import getdefaultoutputfile

from marinedb.tools.marineloc import createmask
from marinedb.tools.marineloc import createmarinefilter
from marinedb.tools.marineloc import filtermarinelocations
from marinedb.tools.marineloc import split_pandas_parquet

# Global variables

__all__ = ['apply']

CHUNKSIZE = 100000

def apply(inputfile, latkey='', lonkey='', idxkey='', controlkey='', uncompressed_chunks_dir='',  sep='\t', split_type='', chunksize=CHUNKSIZE, fileslist=None, kernel_type=None, kernel_size=None, maskfile=None, keep_mask=False, outputdir='./marineloc', store_time=True, store_stats=True, parallel=False, cpu=None, filterfile='marine_filter', outputfile='', cleanup=True, verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    if len(outputdir) == 0:
        outputdir = './marineloc'
    if 'marineloc' not in outputdir.split('/'):
        outputdir = os.path.join(outputdir, 'marineloc')

    try:
        os.mkdir(outputdir)
    except FileExistsError:
        pass

    if (len(filterfile) == 0) or ((len(filterfile) != 0) and (not os.path.isfile(filterfile))):

        if len(latkey) == 0:
            raise ValueError(f'`marineloc.py` | `latkey` must be specified when no `filterfile` is provided')
        if len(lonkey) == 0:
            raise ValueError(f'`marineloc.py` | `lonkey` must be specified when no `filterfile` is provided')

        # Split the file into CHUNKSIZE-line chunks

        issplitdirname = (len(uncompressed_chunks_dir) != 0)
        if not issplitdirname:
            uncompressed_chunks_dir = os.path.join(os.path.dirname(inputfile), 'marineloc')

        issplitdir = os.path.isdir(uncompressed_chunks_dir)
        isnotempty = issplitdir and any(os.path.isfile(f) for f in glob.glob(os.path.join(uncompressed_chunks_dir, '*_split*')))
        issplit = issplitdirname and isnotempty

        if not issplit:

            columns = [latkey, lonkey]
            if len(controlkey) != 0:
                columns.append(controlkey)

            params = {
                      'split_type': split_type,
                      'columns': columns,
                      'sep': sep,
                      'chunksize': chunksize,
                      'outputdir': uncompressed_chunks_dir,
                      'verbose': verbose,
                      'indent': indent
                     }

            uncompressed_chunks_dir = split_pandas_parquet.apply(inputfile, **params)
            idxkey = 'index'
            printv('', verbose=verbose)

        else:

            printv(
                f"INFO | Reusing existing split chunks in {uncompressed_chunks_dir}",
                verbose=verbose,
                indent=indent
            )

            if len(idxkey) == 0:

                files = [f for f in glob.glob(os.path.join(uncompressed_chunks_dir, '*_split*')) if os.path.isfile(f)]

                with open(files[0],'r') as f:
                    header = f.readline().strip('\n').split(sep)

                if 'index' in header:
                    idxkey = 'index'
                    printv(f"INFO | `idxkey` set to 'index'", verbose=verbose, indent=indent)
                else:
                    raise ValueError('`marineloc.py` | `idxkey` must be specified when `inputfile` has already been split into multiple files')

            printv('', verbose=verbose, indent=indent)

        # Generate a mask differentiating land, sea, and coast

        if (kernel_type is not None) and (kernel_size is not None):

            printv('** createmask', verbose=verbose, indent=indent)
            printv('', verbose=verbose)

            if (maskfile is not None) and (len(maskfile) != 0) and os.path.isfile(maskfile):

                printv('INFO | Since `maskfile` is provided, `mask_type` and `mask_size` will be ignored', verbose=verbose, indent=indent)

            else:

                params_mask = {
                               'kernel_type': kernel_type,
                               'kernel_size': kernel_size,
                               'outputdir': outputdir,
                               'verbose': verbose,
                               'indent': indent + '   '
                              }

                maskfile = createmask.apply(**params_mask)

                printv('', verbose=verbose)

        # Extract indices corresponding to marine occurrences

        printv('** createmarinefilter', verbose=verbose, indent=indent)
        printv('', verbose=verbose)

        params_marinefilter = {
                               'inputdir': uncompressed_chunks_dir,
                               'fileslist': fileslist,
                               'latkey': latkey,
                               'lonkey': lonkey,
                               'idxkey': idxkey,
                               'controlkey': controlkey,
                               'sep': sep,
                               'maskfile': maskfile,
                               'outputdir': outputdir,
                               'outputfile': filterfile,
                               'parallel': parallel,
                               'cpu': cpu,
                               'store_time': store_time,
                               'store_stats': store_stats,
                               'cleanup': cleanup,
                               'verbose': verbose,
                               'indent': indent + '   '
                              }

        filterfile = createmarinefilter.apply(**params_marinefilter)

        printv('', verbose=verbose)

    # Filter for marine occurrences

    printv('** filtermarinelocations', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    if len(outputdir) != 0:

        if 'marineloc' not in outputdir.split('/'):
            outputdir = os.path.join(outputdir, 'marineloc')
            try:
                os.mkdir(outputdir)
            except FileExistsError:
                pass

        if (outputfile is None) or (len(outputfile) == 0):
            outputfile = getdefaultoutputfile.apply(inputfile, 'marineloc', outputdir=outputdir, add_processedby=False, verbose=verbose, indent=indent)
        if len(os.path.dirname(outputfile)) == 0:
            outputfile = os.path.join(outputdir, outputfile)

    params_filterdata = {
                         'inputfile': inputfile,
                         'filterfile': filterfile,
                         'inputfile_format': split_type,
                         'controlkey': controlkey,
                         'inputfile_sep': sep,
                         'filter_sep': sep,
                         'keep_mask': keep_mask,
                         'outputfile': outputfile,
                         'cleanup': cleanup,
                         'verbose': verbose,
                         'indent': indent  + '   '
                        }

    outputfile = filtermarinelocations.apply(**params_filterdata)

    return outputfile
