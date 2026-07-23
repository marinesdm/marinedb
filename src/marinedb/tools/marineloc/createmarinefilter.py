#!/usr/bin/python
# coding: utf-8

# External import

import os
import glob
import time
import argparse
import numpy as np
import pandas as pd
from tqdm import tqdm

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools.marineloc import island

# Global variable

__all__ = [] # populated using the @export decorator

def write(df, txt_filename, sep='\t', init=False):

    sep = sep.encode('utf-8').decode('unicode_escape')

    if init:
        df.to_csv(txt_filename, mode='w', index=False, header=True, sep=sep)
    else:
        df.to_csv(txt_filename, mode='a', index=False, header=False, sep=sep)

    return True

def extract_marine_locations(inputdir, latkey, lonkey, idxkey, controlkey=None, sep='\t', fileslist=None, maskfile=None, outputdir='', store_time=True, store_stats=True, overwrite_reports=False, parallel=False, cpu=None, verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    params = {
              'fileslist': fileslist,
              'latkey': latkey,
              'lonkey': lonkey,
              'idxkey': idxkey,
              'controlkey': controlkey,
              'sep': sep,
              'maskfile': maskfile,
              'outputdir': outputdir,
              'overwrite_reports': overwrite_reports,
              'parallel': parallel,
              'cpu': cpu,
              'store_time': store_time,
              'store_stats': store_stats,
              'verbose': verbose,
              'indent': indent
             }

    printv(f'* Extract marine coordinates', verbose=verbose, indent=indent)

    params['indent'] += '  '

    outputdir = island.apply(inputdir, **params)

    return outputdir

def extract_marine_indices(inputdir, controlkey=None, outputfile='marine_filter', sep='\t', verbose=True, indent=''):

    printv(f'* Extract indices corresponding to marine coordinates', verbose=verbose, indent=indent)

    start = time.time()

    sep = sep.encode('utf-8').decode('unicode_escape')

    if 'filter' not in outputfile:
        temp = outputfile.split('.')
        outputfile = temp[0] + '_filter'
        if len(temp) == 2:
            outputfile += f'.{temp[1]}'

    if len(os.path.dirname(outputfile)) == 0:
        outputfile = os.path.join(inputdir,outputfile)

    # If a file has been processed multiple times,
    # consider only one corresponding `island.py` output file

    files = sorted([os.path.join(inputdir,file) for file in os.listdir(inputdir) if os.path.isfile(os.path.join(inputdir,file)) and ('time' not in file) and ('filter' not in file)])
    Nfiles = len(files)

    printv(f'* Deduplicate entries across the {Nfiles} files in {inputdir}', verbose=verbose, indent=indent + '  ')

    unique_files = {}
    for f in files:
        basename = os.path.basename(f).rsplit('_', 1)[0]
        unique_files.setdefault(basename, f)
    files = list(unique_files.values())

    # Keep only the indices corresponding to locations not classified as land

    printv(f'* Extract indices from {len(files)} files', verbose=verbose, indent=indent + '  ')

    chunks = []
    nrows = 0
    init_storage = True
    columns = ['index','mask','latitude','longitude']
    if (controlkey is not None) and (len(controlkey) != 0):
        columns.append(controlkey)

    if verbose:
        process = tqdm(files, total=len(files), desc=indent + '  Progress')
    else:
        process = files

    for file in process:

        df_file = pd.read_csv(file, sep=sep, engine='python')
        df_file = df_file.loc[~df_file['island'], columns]

        if len(df_file) == 0:
            continue

        chunks.append(df_file)
        nrows += len(df_file)

        if nrows >= 1_000_000:
            marinedata = pd.concat(chunks, ignore_index=True)
            marinedata['index'] = marinedata['index'].astype(int)
            write(marinedata, outputfile, init=init_storage, sep=sep)

            chunks = []
            nrows = 0
            init_storage = False

    if chunks:
        marinedata = pd.concat(chunks, ignore_index=True)
        marinedata['index'] = marinedata['index'].astype(int)
        write(marinedata, outputfile, init=init_storage, sep=sep)

    end = time.time()

    printv('', verbose=verbose, indent=indent + '  ')
    printv(f'TIME | substep: {round(end - start,0)}s', verbose=verbose, indent=indent + '  ')

    return outputfile

@export
def apply(inputdir, latkey, lonkey, idxkey, controlkey=None, sep='\t', fileslist=None, maskfile=None, outputdir='', store_time=True, store_stats=True, parallel=False, cpu=None, outputfile='marine_filter', overwrite_reports=False, cleanup=True, verbose=True, indent=''):
    """Create a filter identifying records classified as marine.

    Classify the coordinates contained in the split files from ``inputdir``, then
    extract the indices of records whose final binary land-sea classification is
    sea. The resulting filter can subsequently be applied to the original dataset
    to retain marine occurrences.

    Coordinate classification is performed by
    [`marinedb.tools.marineloc.island.apply`](island/#island). 
    If corresponding processed outputs already exist, they are reused. Only 
    unprocessed input files are classified. 

    !!! warning

        Missing or out-of-range coordinates are treated as records to exclude.
        They are therefore classified as land and absent from the resulting 
        marine filter.

    Args:
        inputdir (str):
            Directory containing the split input files to classify.

        latkey (str):
            Name of the column containing latitude values.

        lonkey (str):
            Name of the column containing longitude values.

        idxkey (str):
            Name of the column containing the record index used to associate the
            marine filter with the original dataset.

        controlkey (str, optional):
            Name of an additional column retained in the marine filter to verify
            record alignment when the filter is later applied to the original
            dataset.

            Using both the record index and the control value reduces the risk that
            an index offset or ordering error selects the wrong record.

        sep (str, optional):
            Field separator used in the split, processed, and filter files.

            For tab-separated files, relying on the default value is recommended.
            When specified explicitly from the command line, escaped separators
            such as ``"\\t"`` should be enclosed in quotes.

        fileslist (str, optional):
            Path to a text file listing the split files to classify, with one file
            per line.

            Relative file names are resolved within ``inputdir``. If omitted, all
            files directly contained in ``inputdir`` are considered.

        maskfile (str, optional):
            Path to a custom ``.npz`` land-sea-coast mask. If omitted, the mask
            bundled with ``marinedb`` is used.

        outputdir (str, optional):
            Directory used for the intermediate coordinate-classification files.
            A ``processed`` subdirectory is added unless the supplied path already
            points to one.

            If omitted, the processed files are written to a ``processed``
            subdirectory within ``inputdir``.

        store_time (bool, optional):
            Whether to record the processing time for each classified input file
            and generate an aggregated timing report.

        store_stats (bool, optional):
            Whether to generate classification statistics for each processed input
            file.

            The statistics report includes the number of records initially assigned
            to ocean, land, and coast by the mask, the final number classified as
            sea or land, and the proportion initially assigned to the coastal
            category.

        parallel (bool, optional):
            Whether to classify several input files concurrently using multiple
            CPUs.

        cpu (int, optional):
            Maximum number of CPUs used for local parallel processing.

            If ``None`` or ``-1``, all CPUs available to the current process are
            used when ``parallel=True``. If fewer files than CPUs are available,
            the number of workers is automatically reduced to the number of files.

        outputfile (str, optional):
            Path or name of the marine-filter file.

            If only a file name is provided, the filter is written to the directory
            containing the processed classification files. If the name does not
            contain ``"filter"``, ``"_filter"`` is added before the file extension,
            when present.

        cleanup (bool, optional):
            !!! danger
                Whether to permanently remove the split input files and intermediate 
                classification files after the marine filter has been created.

            Timing and statistics reports, as well as the marine-filter file, are
            retained.

        overwrite_reports (bool, optional):
            Whether to overwrite existing timing and classification
            statistics reports.

            !!! info

                This option applies only to the reporting files. It
                does not control coordinate classification: input files with an
                existing processed output are always skipped.

    Returns:
        (str):
            Path to the marine-filter file.

    !!! note
        The resulting marine filter contains the standardized columns ``index``,
        ``mask``, ``latitude``, and ``longitude``, together with the optional
        control column. ``mask`` retains the initial classification produced 
        by the land-sea-coast mask, using ``0`` for ocean and ``2`` for coast.
    """

    sep = sep.encode('utf-8').decode('unicode_escape')

    params_marineloc = {
                        'inputdir': inputdir,
                        'fileslist': fileslist,
                        'latkey': latkey,
                        'lonkey': lonkey,
                        'idxkey': idxkey,
                        'controlkey': controlkey,
                        'sep': sep,
                        'maskfile': maskfile,
                        'outputdir': outputdir,
                        'parallel': parallel,
                        'cpu': cpu,
                        'store_time': store_time,
                        'store_stats': store_stats,
                        'overwrite_reports': overwrite_reports,
                        'verbose': verbose,
                        'indent': indent
                       }

    outputdir = extract_marine_locations(**params_marineloc)

    printv('', verbose=verbose)

    params_marineidx = {
                        'inputdir': outputdir,
                        'controlkey': controlkey,
                        'outputfile': outputfile,
                        'sep': sep,
                        'verbose': verbose,
                        'indent': indent
                       }

    outputfile = extract_marine_indices(**params_marineidx)

    printv('', verbose=verbose)

    if cleanup:

        printv('* Cleaning up intermediate files', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        files = glob.glob(os.path.join(inputdir, '*'))
        files += [os.path.join(outputdir,file)
                  for file in os.listdir(outputdir)
                  if os.path.isfile(os.path.join(outputdir,file)) and ('time' not in file) and ('filter' not in file)]

        for file in files:
            printv(f'  >>> {file}', verbose=verbose, indent=indent)
            os.remove(file)

        if len(os.listdir(inputdir)) == 0:
            printv(f'  >>> {inputdir}', verbose=verbose, indent=indent)
            os.rmdir(inputdir)

        if len(os.listdir(outputdir)) == 0:
            printv(f'  >>> {outputdir}', verbose=verbose, indent=indent)
            os.rmdir(outputdir)

    return outputfile

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Extract indices corresponding to marine occurrences', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputdir-path', type=str, help='directory path containing files to be processed')
    parser.add_argument('--fileslist-path', type=str, help='path to the file that lists the files to be processed', default=None)
    parser.add_argument('--latitude-column', type=str, help='latitude column name', required=True)
    parser.add_argument('--longitude-column', type=str, help='longitude column name', required=True)
    parser.add_argument('--index-column', type=str, help='index column name', required=True)
    parser.add_argument('--control-column', type=str, help='control column name', default=None)
    parser.add_argument('--delimiter', type=str, help='delimiter used in the input files', default='\t')
    # Warning: delimiter must be enclosed in quotation marks
    parser.add_argument('--maskfile-path', type=str, help='path to the .npz file containing the land/sea/coast mask', default=None)
    parser.add_argument('--outputdir-path', type=str, help='path to the directory where output files from `island.py` will be saved', default='./')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='whether to enable parallel processing across multiple CPUs', default=False)
    parser.add_argument('--cpu', type=int, help='number of CPUs to be used', default=None)
    parser.add_argument('--store-time', action=argparse.BooleanOptionalAction, help='whether to store the processing times', default=True)
    parser.add_argument('--store-stats', action=argparse.BooleanOptionalAction, help='whether to store the processing statistics', default=True)
    parser.add_argument('--outputfile-path', type=str, help='path to the file where the filter will be saved', default='./marine_filter')
    parser.add_argument('--cleanup', action=argparse.BooleanOptionalAction, help='whether to clean up intermediate files', default=True)
    args = parser.parse_args()

    print()
    print(f'`createmarinefilter.py` | Extract the indices of marine occurrences from {args.inputdir_path} files')
    print()

    params = {
              'inputdir': args.inputdir_path,
              'fileslist': args.fileslist_path,
              'latkey': args.latitude_column,
              'lonkey': args.longitude_column,
              'idxkey': args.index_column,
              'controlkey': args.control_column,
              'sep': args.delimiter.encode('utf-8').decode('unicode_escape'),
              'maskfile': args.maskfile_path,
              'outputdir': args.outputdir_path,
              'parallel': args.parallel,
              'cpu': args.cpu,
              'store_time': args.store_time,
              'store_stats': args.store_stats,
              'outputfile': args.outputfile_path,
              'cleanup': args.cleanup
             }

    start = time.time()

    _ = apply(**params)

    end = time.time()

    print()
    print(f'TIME : {round(end - start,0)}s')
