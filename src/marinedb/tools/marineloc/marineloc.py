#!/usr/bin/python
# coding: utf-8

# External import

import os
import pandas as pd

# Internal import

from marinedb.utils.printverbose import printv

from marinedb.tools.marineloc import createmask
from marinedb.tools.marineloc import createmarinefilter
from marinedb.tools.marineloc import filtermarinelocations
from marinedb.tools.marineloc import split_pandas_parquet

# Global variables

__all__ = ['apply']

CHUNKSIZE = 100000

def apply(inputfile, latkey='', lonkey='', idxkey='', controlkey='', uncompressed_chunks_dir='',  sep='\t', fileslist=None, kernel_type=None, kernel_size=None, maskfile=None, chunksize=CHUNKSIZE, split_type='', outputdir='', store_time=True, parallel=False, cpu=None, filterfile='marine_filter', outputfile='', verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    if (len(filterfile) == 0) or ((len(filterfile) != 0) and (not os.path.isfile(filterfile))):

        if len(latkey) == 0:
            raise ValueError(f'`marineloc.py` | `latkey` must be specified when no `filterfile` is provided')
        if len(lonkey) == 0:
            raise ValueError(f'`marineloc.py` | `lonkey` must be specified when no `filterfile` is provided')

        # Split the file into CHUNKSIZE-line chunks

        issplitdir = (len(uncompressed_chunks_dir) != 0)
        if not issplitdir:
            uncompressed_chunks_dir = os.path.dirname(inputfile)

        isnotempty = os.path.isdir(uncompressed_chunks_dir) and (len(os.listdir(uncompressed_chunks_dir)) != 0)
        issplit = issplitdir and isnotempty
        if not issplit:
            columns = [latkey, lonkey]
            if controlkey is not None:
                columns.append(controlkey)
            uncompressed_chunks_dir = split_pandas_parquet.apply(inputfile, split_type=split_type, columns=columns, sep=sep, chunksize=chunksize, outputdir=uncompressed_chunks_dir, verbose=verbose, indent=indent)
            idxkey = 'index'
            printv('', verbose=verbose)
        else:
            if len(idxkey) == 0:
                raise ValueError('`marineloc.py` | `idxkey` must be specified when `inputfile` has already been split into multiple files')

        if len(outputdir) == 0:
            uncompressed_chunks_dir_wo_split = '/'.join(uncompressed_chunks_dir.split('/')[:-1])
            outputdir = os.path.join(uncompressed_chunks_dir_wo_split,'marineloc')
        else:
            outputdir = os.path.join(outputdir, 'marineloc')
        try:
            os.mkdir(outputdir)
        except FileExistsError:
            pass

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

        if len(outputfile) == 0:
            temp = os.path.basename(inputfile).split('.')
            outputfile = temp[0] + '_marine'
            if len(temp) == 2:
                outputfile += f'.{temp[1]}'
#            outputfile = os.path.join(outputdir, outputfile)
        if len(os.path.dirname(outputfile)) == 0:
            outputfile = os.path.join(outputdir, outputfile)

    params_filterdata = {
                         'inputfile': inputfile,
                         'filterfile': filterfile,
                         'inputfile_format': split_type,
                         'controlkey': controlkey,
                         'inputfile_sep': sep,
                         'filter_sep': sep,
                         'outputfile': outputfile,
                         'verbose': verbose,
                         'indent': indent  + '   '
                        }

    outputfile = filtermarinelocations.apply(**params_filterdata)

    return outputfile
