#!/usr/bin/python
# coding: utf-8

# External import

import os
import json
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

from marinedb.tools import getcolumnname
from marinedb.tools.taxonomic import taxasubset_lowerbound

# Global variable

__all__ = [] # populated using the @export decorator

def generate_species_id_distributed(inputfile, is_species_id, columns, sep='\t', verbose=True, indent=''):

    with open(inputfile,'r') as data:
        input_columns = data.readline().strip('\n').split(sep)

    columns_template = pd.DataFrame([], columns=input_columns)

    # Check that the provided columns exist in the input file

    if not is_species_id:

        for idx, key in enumerate(columns):
            _, columns[idx], _ = getcolumnname.apply(columns_template, key, '', inplace=True)

        missing_columns = set(columns) - set(input_columns)
        if missing_columns:
            raise KeyError(f"`taxasubset.py` | Columns {', '.join(missing_columns)} not found in {inputfile}.")

    else:

        _, columns[0], _ = getcolumnname.apply(columns_template, columns[0], '', inplace=True)

        speciesidkey = columns[0]

        if speciesidkey not in input_columns:
            raise KeyError(f"`taxasubset.py` | Column {speciesidkey} not found in {inputfile}.")

    # Select only the required columns from the file

    columns_print = [f"'{col}'" for col in columns]

    columns_idx = [str(input_columns.index(col) + 1) for col in columns]

    if not is_species_id:

        other_column_idx = list(set(map(str,range(1, len(input_columns) + 1))) - set(columns_idx))[0]
        other_column = input_columns[int(other_column_idx) - 1]

        columns_print.append(f"'{other_column}'")
        columns_idx.append(other_column_idx)

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

    printv(f'* Loading data from {tempfile}', verbose=verbose, indent=indent)

    df = dd.read_csv(tempfile, sep=sep, dtype='string', skip_blank_lines=False)
    df = df.assign(idx=1)
    df = df.set_index(df.idx.cumsum() - 1, sorted=True)
    df = df.rename_axis(index=None)

    # Generate species identifiers from taxonomic classification if no `speciesidkey` is provided

    if is_species_id:

        species_id_values = df[speciesidkey].compute()

    else:

        printv(f'* Generate species identifiers from taxonomic classification', verbose=verbose, indent=indent)

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

    os.remove(tempfile)

    return species_id_values

def generate_species_id_inmemory(df, is_species_id, columns, verbose=True, indent=''):

    if (not is_species_id):

        printv(f'* Generate species identifiers from taxonomic classification', verbose=verbose, indent=indent)

        speciesidkey = 'taxon_id_taxasubset'

        for idx, key in enumerate(columns):
            _, columns[idx], _ = getcolumnname.apply(df, key, '', inplace=True)

        missing_columns = set(columns) - set(df.columns)
        if missing_columns:
            raise KeyError(f"`taxasubset.py` | Columns {', '.join(missing_columns)} not found.")


        df[speciesidkey] = 0
        df[columns] = df[columns].astype('string')
        dfg = df.fillna('_MISSING_').groupby(columns)[speciesidkey]
        ngroup = iter(range(0, dfg.ngroups))
        df[speciesidkey] = dfg.transform(lambda x: next(ngroup)).astype('Int64')
        df.loc[pd.isnull(df[specieskey]) | df[columns[1:]].isnull().all(axis=1), speciesidkey] = pd.NA

    else:

        speciesidkey = columns[0]

        _, speciesidkey, _ = getcolumnname.apply(df, speciesidkey, '', inplace=True)

        if speciesidkey not in df.columns:
            raise KeyError(f"`taxasubset.py` | Column {speciesidkey} not found.")

    return df, speciesidkey, is_species_id


def generate_species_id(input, distributed, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, sep=None, verbose=True, indent=''):

    is_partial_classification = (specieskey is None) or (genuskey is None) or (familykey is None) or (orderkey is None) or (classkey is None) or (phylumkey is None) or (kingdomkey is None)
    is_species_id = (speciesidkey is not None)

    if (not is_species_id) and is_partial_classification:
        raise ValueError(f'`taxasubset.py` | Either the column containing species identifiers or the columns specifying the taxonomic classification must be provided')

    if is_species_id and (not is_partial_classification):
        printv(f"INFO | Since `speciesidkey` is provided ('{speciesidkey}'), classification keys will be ignored", verbose=verbose, indent=indent)

    if not is_species_id:
        columns = [specieskey, genuskey, familykey, orderkey, classkey, phylumkey, kingdomkey]
    else:
        columns = [speciesidkey]

    if distributed:
        output = generate_species_id_distributed(input, is_species_id, columns, sep=sep, verbose=verbose, indent=indent)
    else:
        output = generate_species_id_inmemory(input, is_species_id, columns, verbose=verbose, indent=indent)

    return output

@export
def lowerbound_subset_inmemory(inputfile, sep='\t', dtypes=None, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, limit=50, flag=False, dropna=False, verbose=True, indent='', outputdir='./', outputfile='', store=True):

    if store and (len(outputfile) == 0):
        raise ValueError(f'`taxasubset.py` | `outputfile` is required when store=True')

    if dtypesfile is not None:
        df = pd.read_csv(inputfile, sep=sep, dtype=dtypes)
    else:
        df = pd.read_csv(inputfile, sep=sep, low_memory=False)

#    ispartialclassification = (specieskey is None) or (genuskey is None) or (familykey is None) or (orderkey is None) or (classkey is None) or (phylumkey is None) or (kingdomkey is None)
#    isspeciesidkey = (speciesidkey is not None)
#
#    if (not isspeciesidkey) and ispartialclassification:
#        raise Exception(f'`taxasubset.py` | Either the column containing species identifiers or the columns specifying taxonomic classification must be provided')
#
#    if isspeciesidkey and (not ispartialclassification):
#        printv(f"INFO | Since `speciesidkey` is provided ('{speciesidkey}'), classification keys will be ignored", verbose=verbose, indent=indent)
#
#    if (not isspeciesidkey):
#
#        printv(f'* Identify unique species based on classification', verbose=verbose, indent=indent)
#
#        speciesidkey = 'speciesidkey_taxasubset'
#        columns = [specieskey, genuskey, familykey, orderkey, classkey, phylumkey, kingdomkey]
#        for i,key in enumerate(columns):
#            df, columns[i], _ = getcolumnname.apply(df, key, '', inplace=True)
#
#        df[speciesidkey] = 0
#        df[columns] = df[columns].astype('string')
#
#        dfg = df.fillna('_MISSING_').groupby(columns)[speciesidkey]
#        ngroup = iter(range(0, dfg.ngroups))
#        df[speciesidkey] = dfg.transform(lambda x: next(ngroup)).astype('Int64')
#        df.loc[pd.isnull(df[specieskey]) | df[columns[1:]].isnull().all(axis=1), speciesidkey] = pd.NA
#
#    else:
#
#        generatedkey = [col for col in df.columns if (f'{speciesidkey}_generatedby' in col)]
#        if len(generatedkey) > 1:
#            raise Exception(f"`taxasubset.py` | Multiple generated columns found for '{speciesidkey}': {generatedkey}. An issue may have occurred during execution.")
#        if len(generatedkey) == 1:
#            speciesidkey = generatedkey[0]
#        df, speciesidkey, _ = getcolumnname.apply(df, speciesidkey, '', inplace=True)

    # Generate species identifiers from taxonomic classification if no `speciesidkey` is provided

    columns = {
               'speciesidkey':speciesidkey,
               'specieskey':specieskey,
               'genuskey':genuskey,
               'familykey':familykey,
               'orderkey':orderkey,
               'classkey':classkey,
               'phylumkey':phylumkey,
               'kingdomkey':kingdomkey
              }

    df, speciesidkey, is_species_id = generate_species_id(df, **columns, distributed=False, verbose=verbose, indent=indent)

    # Count the number of observations per species

    printv(f'* Count observations per species', verbose=verbose, indent=indent)

    count = df[speciesidkey].value_counts()
    isabovelimit_speciesidkey = list(count[count >= limit].index)
    isabovelimit = df[speciesidkey].isin(isabovelimit_speciesidkey).astype('boolean')
    ismissing = pd.isnull(df[speciesidkey])
    isabovelimit[ismissing] = pd.NA

    if (not is_species_id):

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
    required_space = inputfile_size + inputfile_size // 10

    if available_disk_space < required_space:
        raise Exception(
                f"`taxasubset.py` | Not enough disk space in {outputdir}: "
                f"{convertbytes.apply(available_disk_space)} available, "
                f"at least {convertbytes.apply(required_space)} required."
             )

#    ispartialclassification = (specieskey is None) or (genuskey is None) or (familykey is None) or (orderkey is None) or (classkey is None) or (phylumkey is None) or (kingdomkey is None)
#    isspeciesidkey = (speciesidkey is not None)
#
#    if (not isspeciesidkey) and ispartialclassification:
#        raise ValueError(f'`taxasubset.py` | Either the column containing species identifiers or the columns specifying the taxonomic classification must be provided')
#
#    if isspeciesidkey and (not ispartialclassification):
#        printv(f"INFO | Since `speciesidkey` is provided ('{speciesidkey}'), classification keys will be ignored", verbose=verbose, indent=indent)
#
#    if not isspeciesidkey:
#        speciesidkey = 'taxon_id_taxasubset'
#        columns = [specieskey, genuskey, familykey, orderkey, classkey, phylumkey, kingdomkey]
#    else:
#        columns = [speciesidkey]

#    with open(inputfile,'r') as data:
#        header = data.readline().strip('\n').split(sep)
#
#    header_mapping = pd.DataFrame([], columns=header)
#    if not isspeciesidkey:
#        for i,key in enumerate(columns):
#            _, columns[i], _ = getcolumnname.apply(header_mapping, key, '', inplace=True)
#    else:
#        generatedkey = [col for col in header_mapping.columns if (f'{speciesidkey}_generatedby' in col)]
#        if len(generatedkey) > 1:
#            raise Exception(f"`taxasubset.py` | Multiple generated columns found for '{speciesidkey}': {generatedkey}. An issue may have occurred during execution.")
#        if len(generatedkey) == 1:
#            speciesidkey = generatedkey[0]
#        _, columns[0], _ = getcolumnname.apply(header_mapping, speciesidkey, '', inplace=True)
#
#    columns_print = [f"'{col}'" for col in columns]
#    columns_idx = [str(header.index(col) + 1) for col in columns]
#    if not isspeciesidkey:
#        other_column_idx = list(set(range(len(header))) - set(columns_idx))[0]
#        other_column = header[other_column_idx]
#        columns_print.append(f"'{other_column}'")
#        columns_idx.append(str(other_column_idx + 1))
#    columns_idx = ','.join(columns_idx)
#    column_subset_algorithm = files('marinedb.utils').joinpath('column_subset.sh')
#    tempfile = os.path.join(outputdir, 'taxasubset_file.temp')
#    try:
#        os.remove(tempfile)
#    except:
#        pass
#    printv(f"* Generate {tempfile} with only the {','.join(columns_print)} column(s)", verbose=verbose, indent=indent)
#    cmd = ['bash', column_subset_algorithm, '-f', inputfile, '-c', columns_idx, '-o', tempfile,'-d', sep]
#    p = subprocess.run(cmd)
#
#    printv(f'* Loading data from {tempfile}', verbose=verbose, indent=indent)
#    df = dd.read_csv(tempfile, sep=sep, dtype='string', skip_blank_lines=False)
#    df = df.assign(idx=1)
#    df = df.set_index(df.idx.cumsum() - 1, sorted=True)
#    df = df.rename_axis(index=None)
#
#    if isspeciesidkey:
#
#        species_id_values = df[speciesidkey].compute()
#
#    else:
#
#        printv(f'* Identify unique species based on classification', verbose=verbose, indent=indent)
#        dfg = df.fillna('_MISSING_')
#        ngroup = len(dfg[columns].drop_duplicates(split_out=True))
#        ngroup_iter = iter(range(0, ngroup))
#        dfg = dfg.groupby(columns)[other_column]
#        species_id_values = dfg.transform(lambda x: next(ngroup_iter), meta=(speciesidkey,'int64')).persist()
#        df = df.assign(taxon_id_taxasubset = species_id_values)
#        species_id_values = df[speciesidkey].compute().sort_index()
#        ismissing1 = df[specieskey].isna().compute()
#        ismissing2 = df[columns[1:]].isna().all(axis=1).compute()
#        species_id_values[ismissing1 | ismissing2] = pd.NA

    # Generate species identifiers from taxonomic classification if no `speciesidkey` is provided

    columns = {
               'speciesidkey':speciesidkey,
               'specieskey':specieskey,
               'genuskey':genuskey,
               'familykey':familykey,
               'orderkey':orderkey,
               'classkey':classkey,
               'phylumkey':phylumkey,
               'kingdomkey':kingdomkey,
              }

    species_id_values = generate_species_id(inputfile, **columns, distributed=True, sep=sep, verbose=verbose, indent=indent)

    # Count the number of observations per species

    printv(f'* Count observations per species', verbose=verbose, indent=indent)

    count = species_id_values.value_counts()
    isabovelimit = list(count[count >= limit].index)
    isabovelimit = species_id_values.isin(isabovelimit).astype('boolean')
    ismissing = pd.isnull(species_id_values)

    assert len(isabovelimit) == len(ismissing)
#    assert len(isabovelimit) == len(df)

    ismissing_indices = list(ismissing[ismissing].index)
    if flag:
        # Flag rows corresponding to taxa with more than `limit` occurrences in the dataset
        isabovelimit_indices = isabovelimit[isabovelimit].index
        isabovelimit_indices = sorted(list(set(isabovelimit_indices) - set(ismissing_indices)))
    else:
        # Drop rows:
        #   - corresponding to taxa with less than `limit` occurrences in the dataset
        #   - with missing values in `speciesidkey` if `dropna`
        isabovelimit[ismissing] = (not dropna)
        isabovelimit_indices = list(isabovelimit[isabovelimit].index)

    ismissing_indices = deque(ismissing_indices)
    isabovelimit_indices = deque(isabovelimit_indices)

#    os.remove(tempfile)

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
def apply(inputfile, sep='\t', lowerbound=-1, upperbound=-1, flag=False, dropna=False, seed=None, force_distributed=False, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, dtypesfile=None, store=True, outputdir='./', outputfile=None, verbose=True, indent=''):

    if (upperbound < 0) and (lowerbound < 0):
        # Do not filter taxa based on their number of occurrences in the dataset
        outputfile = inputfile
        return outputfile

    outputdir = resolvepath.apply(outputdir)
    if (outputfile is None) or (len(outputfile) == 0) or (inputfile == outputfile):
        outputfile = getdefaultoutputfile.apply(inputfile, 'taxasubset', outputdir=outputdir, verbose=verbose, indent=indent)

    if lowerbound > 0:

        params = {
                  'inputfile': inputfile,
                  'sep': sep,
                  'limit': lowerbound,
                  'flag': flag,
                  'dropna': dropna,
                  'force_distributed': force_distributed,
                  'speciesidkey': speciesidkey,
                  'specieskey': specieskey,
                  'genuskey': genuskey,
                  'familykey': familykey,
                  'orderkey': orderkey,
                  'classkey': classkey,
                  'phylumkey': phylumkey,
                  'kingdomkey': kingdomkey,
                  'dtypesfile': dtypesfile,
                  'store': store,
                  'outputdir': outputdir,
                  'outputfile': outputfile,
                  'verbose': verbose,
                  'indent': indent
                 }

        outputfile = taxasubset_lowerbound.apply(**params)

        # Filter taxa with less than `lowerbound` occurrences in the dataset

#        if dtypesfile is not None:
#            with open(dtypesfile,'r') as f:
#                dtypes = json.load(f)
#
#        params = {
#                  'inputfile': inputfile,
#                  'speciesidkey': speciesidkey,
#                  'specieskey': specieskey,
#                  'genuskey': genuskey,
#                  'familykey': familykey,
#                  'orderkey': orderkey,
#                  'classkey': classkey,
#                  'phylumkey': phylumkey,
#                  'kingdomkey': kingdomkey,
#                  'limit': lowerbound,
#                  'flag': flag,
#                  'dropna': dropna,
#                  'sep': sep,
#                  'verbose': verbose,
#                  'indent': indent,
#                  'outputdir': outputdir,
#                  'outputfile': outputfile,
#                 }
#
#        available_memory = psutil.virtual_memory().available
#        file_size = os.path.getsize(inputfile)
#
#        if (not force_distributed) and ((15 * file_size) <= available_memory):
#
#            # In memory
#
#            printv(f'INFO | `taxasubset` will be executed in memory', verbose=verbose, indent=indent)
#
#            params['store'] = store
#            params['dtypesfile'] = dtypesfile
#
#            printv(f'* Loading data from {inputfile}', verbose=verbose, indent=indent)
#
#            outputfile = lowerbound_subset_inmemory(**params)
#
#        else:
#
#            # Distributed
#
#            printv(f'INFO | `taxasubset` will be executed using distributed computation', verbose=verbose, indent=indent)
#
#            outputfile = lowerbound_subset_distributed(inputfile, **params)
#
#        # Clean
#
#        if inputfile !=  outputfile:
#            printv(f'* Delete {inputfile}', verbose=verbose, indent=indent)
#            os.remove(inputfile) #debug
#
#        if flag and (dtypesfile is not None):
#            dtypes[f'flag_taxasubset_isabove_{lowerbound}'] = 'boolean'
#            with open(dtypesfile,'w') as f:
#                json.dump(dtypes, f, indent=4)

    if upperbound > 0:

        # Limit the number of observations per taxon to `upperbound`

        df = upperbound_subset(df, limit=upperbound, flag=flag)

    return outputfile

