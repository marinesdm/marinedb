#!/usr/bin/python
# coding: utf-8

# External import

import os
import glob
import pandas as pd
from pathlib import Path

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

def apply(inputfile, inputfile_format, latkey='', lonkey='', idxkey='', controlkey='', sep='\t', splitdir='',  chunksize=CHUNKSIZE, fileslist=None, kernel_type=None, kernel_size=None, maskfile=None, keep_mask=False, outputdir='./marineloc', store_time=True, store_stats=True, parallel=False, cpu=None, filterfile='marine_filter', outputfile='', cleanup=True, verbose=True, indent=''):
    """Run the complete land-sea filtering workflow.

    Create or reuse a marine filter and apply it to ``inputfile`` to retain
    records classified as marine. 
    
    When no existing marine filter is provided, the workflow successively
    splits the input file, optionally creates a custom land-sea-coast mask, 
    classifies coordinates and creates the marine filter. 
    
    When ``filterfile`` points to an existing file, all preceding stages are
    skipped and the supplied marine filter is applied directly to ``inputfile``.

    For a standard run from the original occurrence file, users generally need to
    specify ``inputfile``, ``inputfile_format``, ``latkey``, ``lonkey``, and must 
    set ``sep`` when the file is not tab-delimited. ``controlkey`` can optionally be 
    provided to verify record alignment. Local parallel classification can be enabled 
    with ``parallel=True`` and controlled with ``cpu``.

    !!! warning

        Missing or out-of-range coordinates are treated as records to exclude.
        They are classified as land and are therefore absent from the final output.

    Args:
        inputfile (str):
            Path to the original occurrence file to filter.

        inputfile_format (str):
            Format of ``inputfile``, which determines the methods used to split and
            filter it. Accepted values are:

            - ``"uncompressed_gzip"`` for plain text or gzip-compressed files;
            - ``"pandas"`` for text formats supported by ``pandas.read_csv``;
            - ``"parquet"`` for Parquet files.

        latkey (str, optional):
            Name of the column containing latitude values.

            This argument is required when an existing ``filterfile`` is not
            provided.

        lonkey (str, optional):
            Name of the column containing longitude values.

            This argument is required when an existing ``filterfile`` is not
            provided.

        idxkey (str, optional):
            Name of the index column in existing split files.

            When the input file is split by this function, an ``index`` column is
            retained or created automatically and used regardless of the supplied
            value. When existing split files are reused and ``idxkey`` is omitted,
            a column named ``index`` is used when available. Otherwise, an error is 
            raised.

        controlkey (str, optional):
            Name of a column used to verify that the marine filter is aligned with
            the original dataset.

            The column is retained during file splitting and marine-filter creation,
            then compared between the filter and the original file during final
            filtering. Any mismatch interrupts processing.

        sep (str, optional):
            Field separator used for non-Parquet input, split, classification, and
            marine-filter files.

            For tab-separated files, relying on the default value is recommended.
            When specified explicitly from the command line, escaped separators
            such as ``"\\t"`` should be enclosed in quotes.

        splitdir (str, optional):
            Directory containing existing split files or in which new split files
            are written.

            Existing files matching ``*_split*`` are reused when this directory is
            explicitly provided and is not empty. If omitted, a ``marineloc``
            directory is created alongside ``inputfile``, and the split files are
            written to its ``split`` subdirectory.

        chunksize (int, optional):
            Maximum number of rows written to each split file. Defaults to
            ``100000``.

        fileslist (str, optional):
            Path to a text file listing the split files to classify, with one file
            per line.

            This argument is passed to the marine-filter creation stage. Relative
            file names are resolved within the split-file directory.

        kernel_type (str, optional):
            Shape of the morphological kernel used to identify the coastal zone when
            creating a custom land-sea-coast mask. Accepted values are ``"square"``
            and ``"ellipse"``.

            A custom mask is created only when ``kernel_size`` is also provided and 
            no existing ``maskfile`` is supplied.

        kernel_size (int, optional):
            Size of the morphological kernel used to identify the coastal zone.

            Larger values produce a broader coastal category, causing more
            locations to be classified using the higher-resolution coastline
            procedure.

            A custom mask is created only when ``kernel_type`` is also provided and 
            no existing ``maskfile`` is supplied.

        maskfile (str, optional):
            Path to an existing ``.npz`` land-sea-coast mask.

            The mask must contain the arrays ``lat``, ``lon``, and ``mask``, where
            ``mask`` uses ``0`` for ocean, ``1`` for land, and ``2`` for coast.

            When an existing mask is provided, ``kernel_type`` and ``kernel_size`` 
            are ignored. If omitted and no custom mask is requested, the mask bundled 
            with ``marinedb`` is used.

        keep_mask (bool, optional):
            Whether to include the initial ``mask`` classification in the final
            output when ``inputfile_format`` is ``"pandas"`` or ``"uncompressed_gzip"``.

        outputdir (str, optional):
            Base directory used for intermediate and final outputs.

            A ``marineloc`` subdirectory is added unless the supplied path already
            points to one. Defaults to ``"./marineloc"``.

        store_time (bool, optional):
            Whether to generate timing information during coordinate
            classification.

        store_stats (bool, optional):
            Whether to generate land-sea classification statistics during 
            coordinate classification.

        parallel (bool, optional):
            Whether to classify several split files concurrently using multiple
            CPUs.

        cpu (int, optional):
            Maximum number of CPUs used for local parallel classification.

            If fewer split files than CPUs are available, the number of workers is
            automatically reduced to the number of files.

        filterfile (str, optional):
            Path or name of the marine-filter file to create or reuse.

            If this argument points to an existing file, splitting, mask creation,
            coordinate classification, and marine-filter creation are skipped. If
            a file name without a directory is used for a newly created filter, it
            is written within the intermediate processed-file directory.

        outputfile (str, optional):
            Path or name of the final tabular file containing marine records.

            If omitted, a default name is derived from ``inputfile`` and the file
            is written within ``outputdir``. A file name without a directory is
            also resolved within ``outputdir``.

        cleanup (bool, optional):

            !!! danger

                Whether to remove intermediate split files, classification files, 
                and the marine-filter file after they are no longer required.

            Timing and classification-statistics reports are retained.

    Returns:
        (str):
            Path to the final tabular file containing marine records.

    Raises:
        ValueError:
            If ``inputfile_format`` is unsupported.
        ValueError:
            If ``latkey`` or ``lonkey`` is omitted when no existing marine filter
            is provided.
        ValueError:
            If existing split files do not contain an ``index`` column and ``idxkey``
            is omitted.

    !!! Note

        When an existing marine filter is supplied, its ``index`` column must be
        sorted in ascending order. When ``controlkey`` is provided, the filter must
        also contain the corresponding control column.
    """

    sep = sep.encode('utf-8').decode('unicode_escape')

    if (len(filterfile) == 0) or ((len(filterfile) != 0) and (not os.path.isfile(filterfile))):

        if len(latkey) == 0:
            raise ValueError(f'`marineloc.py` | `latkey` must be specified when no `filterfile` is provided')
        if len(lonkey) == 0:
            raise ValueError(f'`marineloc.py` | `lonkey` must be specified when no `filterfile` is provided')

        # Split the file into CHUNKSIZE-line chunks

        issplitdirname = (len(splitdir) != 0)
        if not issplitdirname:
            splitdir = os.path.join(os.path.dirname(inputfile), 'marineloc')

        issplitdir = os.path.isdir(splitdir)
        isnotempty = issplitdir and any(os.path.isfile(f) for f in glob.glob(os.path.join(splitdir, '*_split*')))
        issplit = issplitdirname and isnotempty

        if not issplit:

            columns = [latkey, lonkey]
            if len(controlkey) != 0:
                columns.append(controlkey)

            params = {
                      'split_type': inputfile_format,
                      'columns': columns,
                      'sep': sep,
                      'chunksize': chunksize,
                      'outputdir': splitdir,
                      'verbose': verbose,
                      'indent': indent
                     }

            splitdir = split_pandas_parquet.apply(inputfile, **params)
            idxkey = 'index'
            printv('', verbose=verbose)

        else:

            printv(
                f"INFO | Reusing existing split chunks in {splitdir}",
                verbose=verbose,
                indent=indent
            )

            if len(idxkey) == 0:

                files = [f for f in glob.glob(os.path.join(splitdir, '*_split*')) if os.path.isfile(f)]

                with open(files[0],'r') as f:
                    header = f.readline().strip('\n').split(sep)

                if 'index' in header:
                    idxkey = 'index'
                    printv(f"INFO | `idxkey` set to 'index'", verbose=verbose, indent=indent)
                else:
                    raise ValueError('`marineloc.py` | `idxkey` must be specified when `inputfile` has already been split into multiple files')

            printv('', verbose=verbose, indent=indent)

        if (outputdir is None) or (len(outputdir) == 0):
            outputdir = './marineloc'

        try:
            os.mkdir(outputdir)
        except FileExistsError:
            pass

        if (not any(Path(outputdir).iterdir())) and ('marineloc' not in outputdir.split('/')):
            outputdir = os.path.join(outputdir, 'marineloc')

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
                               'inputdir': splitdir,
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
                         'inputfile_format': inputfile_format,
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
