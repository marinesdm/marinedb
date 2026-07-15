#!/usr/bin/python
# coding: utf-8

# External import

import os
import subprocess
import pandas as pd
import dask.dataframe as dd
from collections import deque
from importlib.resources import files

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator

def generate_species_id_distributed(inputfile, is_species_id, columns, sep='\t', outputdir='./', verbose=True, indent=''):

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

        speciesidkey = 'taxon_id_generatedby_taxasubset'
        specieskey = columns[0]

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
    extract_columns_algorithm = files('marinedb.utils').joinpath('extractcolumns.sh')

    tempfile = os.path.join(outputdir, 'taxasubset_file.temp')
    try:
        os.remove(tempfile)
    except:
        pass

    printv(f"* Generate {tempfile} with only the {','.join(columns_print)} column(s)", verbose=verbose, indent=indent)

    cmd = ['bash', extract_columns_algorithm, '-f', inputfile, '-c', columns_idx, '-o', tempfile,'-d', sep]
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

        df = df.assign(taxon_id_generatedby_taxasubset = species_id_values)
        species_id_values = df[speciesidkey].compute().sort_index()
        ismissing1 = df[specieskey].isna().compute()
        ismissing2 = df[columns[1:]].isna().all(axis=1).compute()
        species_id_values[ismissing1 | ismissing2] = pd.NA

    printv(f"* Delete {tempfile}", verbose=verbose, indent=indent)
    os.remove(tempfile)

    return species_id_values, speciesidkey

def generate_species_id_inmemory(df, is_species_id, columns, verbose=True, indent=''):

    if (not is_species_id):

        printv(f'* Generate species identifiers from taxonomic classification', verbose=verbose, indent=indent)

        speciesidkey = 'taxon_id_generatedby_taxasubset'
        specieskey = columns[0]

        for idx, key in enumerate(columns):
            _, columns[idx], _ = getcolumnname.apply(df, key, '', inplace=True)

        missing_columns = set(columns) - set(df.columns)
        if missing_columns:
            raise KeyError(f"`taxasubset.py` | Columns {', '.join(missing_columns)} not found.")


        df[speciesidkey] = 0
        df[columns] = df[columns].astype('string')
        dfg = df.copy()
        dfg[columns] = dfg[columns].fillna('_MISSING_')
        dfg = dfg.groupby(columns)[speciesidkey]
#        dfg = df.fillna('_MISSING_').groupby(columns)[speciesidkey]
        ngroup = iter(range(0, dfg.ngroups))
        df[speciesidkey] = dfg.transform(lambda x: next(ngroup)).astype('Int64')
        df.loc[pd.isnull(df[specieskey]) | df[columns[1:]].isnull().all(axis=1), speciesidkey] = pd.NA

    else:

        speciesidkey = columns[0]

        _, speciesidkey, _ = getcolumnname.apply(df, speciesidkey, '', inplace=True)

        if speciesidkey not in df.columns:
            raise KeyError(f"`taxasubset.py` | Column {speciesidkey} not found.")

    return df, speciesidkey, is_species_id


@export
def apply(input, distributed, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, sep='\t', outputdir='./', verbose=True, indent=''):

    # Ensure either a species ID column or classification columns are specified

    is_partial_classification = (specieskey is None) or (genuskey is None) or (familykey is None) or (orderkey is None) or (classkey is None) or (phylumkey is None) or (kingdomkey is None)
    is_species_id = (speciesidkey is not None)

    if (not is_species_id) and is_partial_classification:
        raise ValueError(f'`taxasubset.py` | Either the column containing species identifiers or the columns specifying the taxonomic classification must be provided')

    if is_species_id and (not is_partial_classification):
        printv(f"INFO | Since `speciesidkey` is provided ('{speciesidkey}'), classification keys will be ignored", verbose=verbose, indent=indent)

    # Generate species identifiers if needed

    if not is_species_id:
        columns = [specieskey, genuskey, familykey, orderkey, classkey, phylumkey, kingdomkey]
    else:
        columns = [speciesidkey]

    if distributed:
        output = generate_species_id_distributed(input, is_species_id, columns, sep=sep, outputdir=outputdir, verbose=verbose, indent=indent)
    else:
        output = generate_species_id_inmemory(input, is_species_id, columns, verbose=verbose, indent=indent)

    return output
