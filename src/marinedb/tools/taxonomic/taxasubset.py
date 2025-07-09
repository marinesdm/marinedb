#!/usr/bin/python
# coding: utf-8

# External import

import os
import shutil
import psutil
import subprocess
import pandas as pd
import dask.dataframe as dd
from collections import deque
from importlib.resources import files

# Internal import

from marinedb.utils import convertbytes
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv
from marinedb.utils import getdefaultoutputfile

from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator

@export
def lowerbound_subset_inmemory(df, sep='\t', speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, limit=50, flag=False, dropna=False, verbose=True, indent='', outputdir='./', outputfile='', store=True):

    if store and (len(outputfile) == 0):
        raise ValueError(f'`taxasubset.py` | `outputfile` is required when store=True')

    ispartialclassification = (specieskey is None) or (genuskey is None) or (familykey is None) or (orderkey is None) or (classkey is None) or (phylumkey is None) or (kingdomkey is None)
    isspeciesidkey = (speciesidkey is not None)

    if (not isspeciesidkey) and ispartialclassification:
        raise Exception(f'`taxasubset.py` | Either the column containing species identifiers or the columns specifying taxonomic classification must be provided')

    if isspeciesidkey and (not ispartialclassification):
        printv(f"INFO | Since `speciesidkey` is provided ('{speciesidkey}'), classification keys will be ignored", verbose=verbose, indent=indent)

    if (not isspeciesidkey):

        printv(f'* Identify unique species based on classification', verbose=verbose, indent=indent)

        speciesidkey = 'speciesidkey_taxasubset'
        columns = [specieskey, genuskey, familykey, orderkey, classkey, phylumkey, kingdomkey]
        for i,key in enumerate(columns):
            df, columns[i], _ = getcolumnname.apply(df, key, '', inplace=True)

        df[speciesidkey] = 0
        df[columns] = df[columns].astype('string')

        dfg = df.fillna('_MISSING_').groupby(columns)[speciesidkey]
        ngroup = iter(range(0, dfg.ngroups))
        df[speciesidkey] = dfg.transform(lambda x: next(ngroup)).astype('Int64')
        df.loc[pd.isnull(df[specieskey]) | df[columns[1:]].isnull().all(axis=1), speciesidkey] = pd.NA

    else:

        generatedkey = [col for col in df.columns if (f'{speciesidkey}_generatedby' in col)]
        if len(generatedkey) > 1:
            raise Exception(f"`taxasubset.py` | Multiple generated columns found for '{speciesidkey}': {generatedkey}. An issue may have occurred during execution.")
        if len(generatedkey) == 1:
            speciesidkey = generatedkey[0]
        df, speciesidkey, _ = getcolumnname.apply(df, speciesidkey, '', inplace=True)

    printv(f'* Count observations per species', verbose=verbose, indent=indent)
    count = df[speciesidkey].value_counts()
    isabovelimit = list(count[count >= limit].index)
    isabovelimit = df[speciesidkey].isin(isabovelimit).astype('boolean')
    ismissing = pd.isnull(df[speciesidkey])
    isabovelimit[ismissing] = pd.NA

    if (not isspeciesidkey):
        df.drop(columns=speciesidkey, inplace=True)

    if flag:

        # Flag rows corresponding to taxa with more than `limit` occurrences in the dataset

        df[f'flag_taxasubset_isabove_{limit}'] = isabovelimit

    else:

        # Drop rows:
        #   - corresponding to taxa with less than `limit` occurrences in the dataset
        #   - with missing values in `speciesidkey` if `dropna`

        isabovelimit[ismissing] = (not dropna)
        df = df[isabovelimit]

    if store:
        printv(f'* Save to {outputfile}', verbose=verbose, indent=indent)
        if len(os.path.dirname(outputfile)) == 0:
            outputfile = os.path.join(outputdir, outputfile)
        df.to_csv(outputfile, sep=sep, index=False)

    return df, outputfile

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
def lowerbound_subset_distributed(inputfile, sep='\t', speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, limit=50, flag=False, dropna=False, verbose=True, indent='', outputdir='./', outputfile=None):

    _, _, available_disk_space = shutil.disk_usage(outputdir)
    inputfile_size = os.stat(inputfile).st_size
    if inputfile_size >= available_disk_space:
        raise Exception(f'`taxasubset.py` | The available disk space at {outputdir} (i.e. {convertbytes.apply(available_disk_space)}) should be at least equal to the size of {inputfile} (i.e {convertbytes.apply(inputfile_size)})')

    ispartialclassification = (specieskey is None) or (genuskey is None) or (familykey is None) or (orderkey is None) or (classkey is None) or (phylumkey is None) or (kingdomkey is None)
    isspeciesidkey = (speciesidkey is not None)

    if (not isspeciesidkey) and ispartialclassification:
        raise Exception(f'`taxasubset.py` | Either the column containing species identifiers or the columns specifying the taxonomic classification must be provided')

    if isspeciesidkey and (not ispartialclassification):
        printv(f"INFO | Since `speciesidkey` is provided ('{speciesidkey}'), classification keys will be ignored", verbose=verbose, indent=indent)

    if not isspeciesidkey:
        speciesidkey = 'taxon_id_taxasubset'
        columns = [specieskey, genuskey, familykey, orderkey, classkey, phylumkey, kingdomkey]
    else:
        columns = [speciesidkey]

    with open(inputfile,'r') as data:
        header = data.readline().strip('\n').split(sep)

    header_mapping = pd.DataFrame([], columns=header)
    if not isspeciesidkey:
        for i,key in enumerate(columns):
            _, columns[i], _ = getcolumnname.apply(header_mapping, key, '', inplace=True)
    else:
        generatedkey = [col for col in header_mapping.columns if (f'{speciesidkey}_generatedby' in col)]
        if len(generatedkey) > 1:
            raise Exception(f"`taxasubset.py` | Multiple generated columns found for '{speciesidkey}': {generatedkey}. An issue may have occurred during execution.")
        if len(generatedkey) == 1:
            speciesidkey = generatedkey[0]
        _, columns[0], _ = getcolumnname.apply(header_mapping, speciesidkey, '', inplace=True)

    columns_print = [f"'{col}'" for col in columns]
    columns_idx = [str(header.index(col) + 1) for col in columns]
    if not isspeciesidkey:
        other_column_idx = list(set(range(len(header))) - set(columns_idx))[0]
        other_column = header[other_column_idx]
        columns_print.append(f"'{other_column}'")
        columns_idx.append(str(other_column_idx + 1))
    columns_idx = ','.join(columns_idx)
    column_subset_algorithm = files('marinedb.utils').joinpath('column_subset.sh')
    tempfile = os.path.join(outputdir, 'taxasubset_file.temp')
    try:
        os.remove(tempfile)
    except:
        pass
    printv(f"* Generate {tempfile} with only the {','.join(columns_print)} column(s)", verbose=verbose, indent=indent)
    cmd = ['bash', column_subset_algorithm, '-f', inputfile, '-c', columns_idx, '-o', tempfile,'-d', sep]
    p = subprocess.run(cmd)

#    if not isspeciesidkey:
#        other_column = list(set(header) - set(columns))[0]
#        print('other_column', other_column)
#        columns.append(other_column)
#        print(columns)

    printv(f'* Loading data from {tempfile}', verbose=verbose, indent=indent)
    df = dd.read_csv(tempfile, sep=sep, dtype='string', skip_blank_lines=False)
#    df = dd.read_csv(inputfile, sep=sep, dtype='string', skip_blank_lines=False, usecols=columns)
    df = df.assign(idx=1)
    df = df.set_index(df.idx.cumsum() - 1, sorted=True)
    df = df.rename_axis(index=None)

    if isspeciesidkey:

        species_id_values = df[speciesidkey].compute()

    else:

        printv(f'* Identify unique species based on classification', verbose=verbose, indent=indent)
        dfg = df.fillna('_MISSING_')
        ngroup = len(dfg[columns].drop_duplicates(split_out=True))
        ngroup_iter = iter(range(0, ngroup))
        dfg = dfg.groupby(columns)[other_column]
        species_id_values = dfg.transform(lambda x: next(ngroup_iter), meta=(speciesidkey,'int64')).persist()
        df = df.assign(taxon_id_taxasubset = species_id_values)
        species_id_values = df[speciesidkey].compute().sort_index()
        ismissing1 = df[specieskey].isna().compute()
        ismissing2 = df[columns[1:]].isna().all(axis=1).compute()
        species_id_values[ismissing1 | ismissing2] = pd.NA

    printv(f'* Count observations per species', verbose=verbose, indent=indent)
    count = species_id_values.value_counts()
    isabovelimit = list(count[count >= limit].index)
    isabovelimit = species_id_values.isin(isabovelimit).astype('boolean')
    ismissing = pd.isnull(species_id_values)

    assert len(isabovelimit) == len(ismissing)
    assert len(isabovelimit) == len(df)

    ismissing_indices = list(ismissing[ismissing].index)
    if flag:
        isabovelimit_indices = isabovelimit[isabovelimit].index
        isabovelimit_indices = sorted(list(set(isabovelimit_indices) - set(ismissing_indices)))
    else:
        isabovelimit[ismissing] = (not dropna)
        isabovelimit_indices = list(isabovelimit[isabovelimit].index)

    ismissing_indices = deque(ismissing_indices)
    isabovelimit_indices = deque(isabovelimit_indices)

    os.remove(tempfile)

    printv(f'* Filter or flag species with more than {limit} observations', verbose=verbose, indent=indent)
    printv(f'INFO | {tempfile} will be overwritten', verbose=verbose, indent=indent)
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
                store_lines(lines, tempfile, verbose=verbose, indent=indent)
                lines.clear()

            if ((idx + 1) % 1000000) == 0:
                printv(f'Processing | {idx + 1} lines done', verbose=verbose, indent=indent)

            if stop:
                break

    if len(lines) != 0:
        store_lines(lines, tempfile, verbose=verbose, indent=indent)
        printv(f'Processing | {idx + 1} lines done', verbose=verbose, indent=indent)

    if (outputfile is None) or (len(outputfile) == 0):
        outputfile = getdefaultoutputfile.apply(inputfile, 'taxasubset', outputdir=outputdir)

    printv(f'* Renaming {tempfile} to {outputfile}', verbose=verbose, indent=indent)
    os.rename(tempfile, outputfile)

    return outputfile

def upperbound_subset(df, limit=-1, flag=False): #TODO
    print('`taxasubset.py` | `upperbound_subset` has not been implemented yet')
    return None

@export
def apply(inputfile, sep='\t', lowerbound=-1, upperbound=-1, flag=False, dropna=False, seed=None, force_distributed=False, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, store=True, outputdir='./', outputfile=None, verbose=True, indent=''):

    if (upperbound == -1) and (lowerbound == -1):
        # Do not filter taxa based on their number of occurrences in the dataset
        return None

    if (outputfile is None) or (len(outputfile) == 0):
        outputfile = getdefaultoutputfile.apply(inputfile, 'taxasubset', outputdir=outputdir)

    if lowerbound > 0:

        # Filter taxa with less than `lowerbound` occurrences in the dataset

        params = {
                  'speciesidkey': speciesidkey,
                  'specieskey': specieskey,
                  'genuskey': genuskey,
                  'familykey': familykey,
                  'orderkey': orderkey,
                  'classkey': classkey,
                  'phylumkey': phylumkey,
                  'kingdomkey': kingdomkey,
                  'limit': lowerbound,
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

        if (not force_distributed) and ((15 * file_size) <= available_memory):

            # In memory

            printv(f'INFO | `taxasubset` will be executed in memory', verbose=verbose, indent=indent)

            params['store'] = store
#            columns = [specieskey, genuskey, familykey, orderkey, classkey, phylumkey, kingdomkey, speciesidkey]
#            columns = [col for col in columns if col is not None]
            printv(f'* Loading data from {inputfile}', verbose=verbose, indent=indent)
            df = pd.read_csv(inputfile, sep=sep)
#            df = pd.read_csv(inputfile, sep=sep, usecols=columns, dtype='string')
#            print(df.memory_usage(deep=True))
#            print(df.memory_usage(deep=True).sum())
            df, outputfile = lowerbound_subset_inmemory(df, **params)

        else:

            # Distributed

            printv(f'INFO | `taxasubset` will be executed using distributed computation', verbose=verbose, indent=indent)

            df = None
            outputfile = lowerbound_subset_distributed(inputfile, **params)

    if upperbound > 0:

        # Limit the number of observations per taxon to `upperbound`

        df = upperbound_subset(df, limit=upperbound, flag=flag)

    return df, outputfile

