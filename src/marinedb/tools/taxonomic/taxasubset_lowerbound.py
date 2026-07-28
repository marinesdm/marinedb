#!/usr/bin/python
# coding: utf-8

# External import

import os
import json
import time
import shutil
import psutil
import subprocess
import pandas as pd
import dask.dataframe as dd
from collections import deque
from importlib.resources import files

# Internal import

from marinedb.utils import resolvepath
from marinedb.utils import convertbytes
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv
from marinedb.utils import getdefaultoutputfile

from marinedb.tools.taxonomic import taxasubset_species_identifier

# Global variable

__all__ = [] # populated using the @export decorator


@export
def lowerbound_subset_inmemory(inputfile, sep='\t', dtypes=None, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, limit=50, flag=False, dropna=False, verbose=True, indent='', outputdir='./', outputfile=''):

    if len(outputfile) == 0:
        raise ValueError(f'`taxasubset.py` | `outputfile` is required')

    start = time.time()

    printv(f'* Loading data from {inputfile}', verbose=verbose, indent=indent)

    if dtypes is not None:
        df = pd.read_csv(inputfile, sep=sep, dtype=dtypes)
    else:
        df = pd.read_csv(inputfile, sep=sep, low_memory=False)

    nobs_before = len(df)

    # Generate species identifiers from taxonomic classification if no `speciesidkey` is provided

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

    df, speciesidkey, is_species_id = taxasubset_species_identifier.apply(df, **params)

    # Count the number of observations per species

    printv(f'* Count observations per species', verbose=verbose, indent=indent)

    count = df[speciesidkey].value_counts()
    isabovelimit_speciesidkey = list(count[count >= limit].index)
    isabovelimit = df[speciesidkey].isin(isabovelimit_speciesidkey).astype('boolean')
    ismissing = pd.isnull(df[speciesidkey])
    isabovelimit[ismissing] = pd.NA

    nspecies = len(count)
    nspecies_below_limit = (count < limit).sum()
    pct = round((nspecies_below_limit / nspecies) * 100, 2)

    if flag:

        # Flag rows corresponding to taxa with more than `limit` occurrences in the dataset

        printv(f'* Flag species with more than {limit} occurrences', verbose=verbose, indent=indent)
        printv(f'INFO | {nspecies_below_limit} species below threshold ({pct}%)', verbose=verbose, indent=indent + '  ')

        df[f'flag_taxasubset_isabove_{limit}'] = isabovelimit

    else:

        # Drop rows:
        #   - corresponding to taxa with less than `limit` occurrences in the dataset
        #   - with missing values in `speciesidkey` if `dropna`

        printv(f'* Filter out species with fewer than {limit} occurrences', verbose=verbose, indent=indent)
        printv(f'INFO | {nspecies_below_limit} species below threshold ({pct}%)', verbose=verbose, indent=indent + '  ')

        isabovelimit[ismissing] = (not dropna)
        df = df[isabovelimit]

    printv(f'* Save to {outputfile}', verbose=verbose, indent=indent)
    if len(os.path.dirname(outputfile)) == 0:
        outputfile = os.path.join(outputdir, outputfile)
    df.to_csv(outputfile, sep=sep, index=False)

    nobs_after = len(df)

    printv('', verbose=verbose, indent=indent)
    printv(f'taxasubset (lowerbound) | before: {nobs_before:,d}, after : {nobs_after:,d} ({nobs_after - nobs_before:,d})', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)
    printv(f'TIME | substep: {round(time.time() - start)}s', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    return outputfile, speciesidkey

def store_lines(lines, outputfile, verbose=True, indent=''):

    printv(f'>>> save {len(lines)} lines to {outputfile}', verbose=verbose, indent=indent)

    with open(outputfile, 'a') as file:
        file.writelines(lines)

    return True

def populate_flag(lines, index, line, isabovelimit_indices, ismissing_indices, sep):

    obs = line.strip('\n').split(sep)

    if (len(isabovelimit_indices) != 0) and (index == isabovelimit_indices[0]):
        obs.append('True')
        isabovelimit_indices.popleft()
    elif (len(ismissing_indices) != 0) and (index == ismissing_indices[0]):
        obs.append('')
        ismissing_indices.popleft()
    else:
        obs.append('False')

    obs[-1] += '\n'
    lines.append(sep.join(obs))

    return False

def populate_inplace(lines, index, line, isabovelimit_indices, *ignore_arg, **ignore_kwargs):

    if index == isabovelimit_indices[0]:
        lines.append(line)
        isabovelimit_indices.popleft()

    if (len(isabovelimit_indices) == 0):
        stop = True
    else:
        stop = False

    return stop

def populate_method(flag):
    if flag:
        return populate_flag
    else:
        return populate_inplace

@export
def lowerbound_subset_distributed(inputfile, sep='\t', limit=50, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, flag=False, dropna=False, verbose=True, indent='', outputdir='./', outputfile=None):

    _, _, available_disk_space = shutil.disk_usage(outputdir)
    inputfile_size = os.stat(inputfile).st_size
    required_space = inputfile_size + inputfile_size // 10

    if available_disk_space < required_space:
        raise Exception(
                f"`taxasubset.py` | Not enough disk space in {outputdir}: "
                f"{convertbytes.apply(available_disk_space)} available, "
                f"at least {convertbytes.apply(required_space)} required."
             )

    start = time.time()

    # Generate species identifiers from taxonomic classification if no `speciesidkey` is provided

    params = {
               'speciesidkey': speciesidkey,
               'specieskey': specieskey,
               'genuskey': genuskey,
               'familykey': familykey,
               'orderkey': orderkey,
               'classkey': classkey,
               'phylumkey': phylumkey,
               'kingdomkey': kingdomkey,
               'distributed': True,
               'sep': sep,
               'outputdir': outputdir,
               'verbose': verbose,
               'indent': indent
              }

    species_id_values, speciesidkey = taxasubset_species_identifier.apply(inputfile, **params)
    nobs_before = len(species_id_values)

    # Count the number of observations per species

    printv(f'* Count observations per species', verbose=verbose, indent=indent)

    count = species_id_values.value_counts()

    # Filter out or flag underrepresented species based on threshold

    isabovelimit = list(count[count >= limit].index)
    isabovelimit = species_id_values.isin(isabovelimit).astype('boolean')
    ismissing = pd.isnull(species_id_values)

    assert len(isabovelimit) == len(ismissing)

    nspecies = len(count)
    nspecies_below_limit = (count < limit).sum()
    pct = round((nspecies_below_limit / nspecies) * 100, 2)

    ismissing_indices = list(ismissing[ismissing].index)
    if flag:

        # Flag rows corresponding to taxa with more than `limit` occurrences in the dataset

        printv(f'* Flag species with more than {limit} occurrences', verbose=verbose, indent=indent)
        printv(f'INFO | {nspecies_below_limit} species below threshold ({pct}%)', verbose=verbose, indent=indent + '  ')

        isabovelimit_indices = isabovelimit[isabovelimit].index
        isabovelimit_indices = sorted(list(set(isabovelimit_indices) - set(ismissing_indices)))
        nobs_after = nobs_before

    else:

        # Drop rows:
        #   - corresponding to taxa with less than `limit` occurrences in the dataset
        #   - with missing values in `speciesidkey` if `dropna`

        printv(f'* Filter out species with fewer than {limit} occurrences', verbose=verbose, indent=indent)
        printv(f'INFO | {nspecies_below_limit} species below threshold ({pct}%)', verbose=verbose, indent=indent + '  ')

        isabovelimit[ismissing] = (not dropna)
        isabovelimit_indices = list(isabovelimit[isabovelimit].index)
        nobs_after = len(isabovelimit_indices)

    ismissing_indices = deque(ismissing_indices)
    isabovelimit_indices = deque(isabovelimit_indices)

    tempfile = os.path.join(outputdir, 'taxasubset_file.temp')
    check = 0 # debug
    with open(inputfile,'r') as inputdata:

        header = inputdata.readline().strip('\n').split(sep)
        if flag:
            header.append(f'flag_taxasubset_isabove_{limit}')
        header[-1] += '\n'
        with open(tempfile, 'w') as file:
            file.write(sep.join(header))

        lines = []
        populate_lines = populate_method(flag)
        for idx, line in enumerate(inputdata):

            stop = populate_lines(lines, idx, line, isabovelimit_indices, ismissing_indices, sep)

            if len(lines) == 100000:
                check += len(lines) # debug
                store_lines(lines, tempfile, verbose=verbose, indent=indent)
                lines.clear()

            if ((idx + 1) % 1000000) == 0:
                printv(f'Processing | {idx + 1} lines done', verbose=verbose, indent=indent)

            if stop:
                break

    if len(lines) != 0:
        check += len(lines) # debug
        store_lines(lines, tempfile, verbose=verbose, indent=indent)

    assert check == nobs_after #debug

    # Output file

    if (outputfile is None) or (len(outputfile) == 0):
        outputfile = getdefaultoutputfile.apply(inputfile, 'taxasubset', outputdir=outputdir)

    printv(f'* Renaming {os.path.basename(tempfile)} to {os.path.basename(outputfile)}', verbose=verbose, indent=indent)
    os.rename(tempfile, outputfile)

    printv(f'  taxasubset (lowerbound) | before: {nobs_before:,d}, after : {nobs_after:,d} ({nobs_after - nobs_before:,d})', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)
    printv(f'TIME | substep: {round(time.time() - start)}s', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    return outputfile, speciesidkey

@export
def apply(inputfile, sep='\t', limit=50, flag=False, dropna=False, force_distributed=False, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, dtypesfile=None, outputdir='./', outputfile=None, verbose=True, indent=''):
    """Flag sufficiently represented taxa or remove underrepresented taxa.

    Counts the number of records associated with each taxon and identifies
    taxa represented by fewer than a user-defined minimum number of
    occurrences. Taxa represented by at least `limit` records satisfy the
    minimum-occurrence criterion.

    Taxa are evaluated using a species identifier. This identifier may 
    be supplied through `speciesidkey` or constructed from the available 
    taxonomic classification columns when no identifier is provided. 
    
    Processing is performed in memory when sufficient memory is available 
    and otherwise uses a distributed implementation.

    !!! warning

        - When `flag=True`, records belonging to taxa represented by at least
        `limit` occurrences are flagged.

        - When `flag=False`, records belonging to taxa represented by fewer
        than `limit` occurrences are excluded.

    Args:
        inputfile (str):
            Path to the input tabular file.

        sep (str, optional):
            Field delimiter used in the input and output files.

        speciesidkey (str, optional):
            Name of the column containing the species identifier used to group
            records and count occurrences. When omitted, species identifiers 
            are generated from the available taxonomic classification columns. 
            
            When `taxasubset` is used after `isinworms` in the integrated 
            workflow, the species identifier is supplied automatically and 
            corresponds to the WoRMS `AphiaID`.

        specieskey (str, optional):
            Name of the species column used, together with the available
            higher-rank columns, to construct species identifiers when `speciesidkey` 
            is not provided. 

        genuskey (str, optional):
            Name of the genus column used to construct species identifiers
            when needed. 

        familykey (str, optional):
            Name of the family column used to construct species identifiers
            when needed. 

        orderkey (str, optional):
            Name of the order column used to construct species identifiers
            when needed. 

        classkey (str, optional):
            Name of the class column used to construct species identifiers
            when needed. 

        phylumkey (str, optional):
            Name of the phylum column used to construct species identifiers
            when needed. 

        kingdomkey (str, optional):
            Name of the kingdom column used to construct species identifiers
            when needed. 

        limit (int, optional):
            Minimum number of occurrences required for a taxon to be
            flagged or retained as sufficiently represented. Taxa with
            fewer occurrences are considered underrepresented. 

        flag (bool, optional):
            Whether to add a Boolean flag instead of excluding records.
            When `True`, all records are retained and
            `flag_taxasubset_isabove_<limit>` is `True` for records belonging
            to taxa represented by at least `limit` occurrences, `False` for
            underrepresented taxa, and missing when the taxon identifier is
            missing. When `False`, records belonging to underrepresented
            taxa are excluded. 

        dropna (bool, optional):
            Whether to also exclude records with a missing taxon identifier
            when `flag=False`. Missing identifiers are retained when
            `False`. This parameter has no effect when `flag=True`. Defaults
            to `False`.

        force_distributed (bool, optional):
            Whether to use distributed processing regardless of the
            available memory.            
            
        dtypesfile (str, optional):
            Path to a JSON file defining column data types. When a flag
            column is created, its Boolean type is added to this file.

        outputdir (str, optional):
            Directory in which to write the output file. 

        outputfile (str, optional):
            Path or name of the output file. In distributed mode, a default
            output filename is generated from the input filename when this
            argument is omitted. In in-memory mode, an output filename must be
            provided.

    Returns:
        (tuple[str, str]):
            Path to the processed output file and the name of the species
            identifier column used for occurrence counting.

    Raises:
        ValueError:
            If no output file is specified when in-memory processing is used.
        Exception:
            If distributed processing is required but the output directory
            does not provide enough free disk space.

    Notes:
        Occurrence counts are calculated from non-missing species
        identifiers. Records with missing identifiers are therefore not
        assigned to an occurrence-count category.

        When the output path differs from the input path, the input file is
        deleted after successful processing.
    """

    # Filter taxa with less than `limit` occurrences in the dataset

    if dtypesfile is not None:
        with open(dtypesfile,'r') as f:
            dtypes = json.load(f)

    params = {
              'speciesidkey': speciesidkey,
              'specieskey': specieskey,
              'genuskey': genuskey,
              'familykey': familykey,
              'orderkey': orderkey,
              'classkey': classkey,
              'phylumkey': phylumkey,
              'kingdomkey': kingdomkey,
              'limit': limit,
              'flag': flag,
              'dropna': dropna,
              'sep': sep,
              'verbose': verbose,
              'indent': indent,
              'outputdir': outputdir,
              'outputfile': outputfile,
             }

    available_memory = psutil.virtual_memory().available
    file_size = os.path.getsize(inputfile)
    required_space = 15 * file_size

    if (not force_distributed) and (available_memory >= required_space):

        # In memory

        printv(f'INFO | `taxasubset` will be executed in memory', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        if dtypesfile is not None:
            params['dtypes'] = dtypes

        outputfile, speciesidkey = lowerbound_subset_inmemory(inputfile, **params)

    else:

        # Distributed

        printv(f'INFO | `taxasubset` will be executed using distributed computation', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        outputfile, speciesidkey = lowerbound_subset_distributed(inputfile, **params)

    # Clean

    if inputfile !=  outputfile:
        printv(f'* Delete {inputfile}', verbose=verbose, indent=indent)
        os.remove(inputfile)

    if flag and (dtypesfile is not None):
        dtypes[f'flag_taxasubset_isabove_{limit}'] = 'boolean'
        with open(dtypesfile,'w') as f:
            json.dump(dtypes, f, indent=4)

    return outputfile, speciesidkey

