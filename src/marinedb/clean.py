#!/usr/bin/python
# coding: utf-8

# External imports

import re
import gzip
import yaml
import time
import copy
import argparse
import numpy as np
import pandas as pd

# Internal import

import tools
from marinedb.tools import getcolumnname
from marinedb.tools import convertdatetype
from marinedb.tools import createwormsfilters as cwf

from marinedb.utils import readfile
from marinedb.utils import writedataframe
from marinedb.utils import standardizenan

# Global variable

TYPE = {
        'int':'Int64',
        'float':'Float64',
        'str':'string', #preserve NaN
        'bool':'boolean',
        'datetime':'datetime64[ns]'
       }


BATCH_SIZE = 100000 #issues if too big


def get_key(onekeydict):
    if isinstance(onekeydict, str):
        return onekeydict
    elif isinstance(onekeydict, dict):
        keys = list(onekeydict.keys())
        if len(keys) == 1:
            return keys[0]
        else:
            raise Exception(f'`clean.py` | The dictionary must contain exactly one key, found {len(keys)}')
    else:
        raise TypeError(f'`clean.py` | {type(onekeydict).__name__} is not a supported type')


def get_keys(list_onekeydict):
    return [get_key(onekeydict) for onekeydict in list_onekeydict]


def get_dtypes(config):

    config_variables = config['variables']
    dtypes_mapping = {}

    for coldict in config_variables:

        if isinstance(coldict,dict):
            colname_old = get_key(coldict)
            if isinstance(column[colname_old], dict):
                colname_new = get_key(column[colname_old])
                coltype = column[colname_old][colname_new]
                if (coltype in TYPE.keys()):
                    coltype = TYPE[coltype]
                dtypes_mapping[colname_old] = coltype

    return dtypes_mapping


def update_config(config, columns, addcolumns=None):

    config_variables = copy.deepcopy(config['variables'])

    for idx, coldict in enumerate(config_variables):

        add = None

        colname_old = get_key(coldict)

        # Retrieve column names post-processing

        _, colname_proc, _ = getcolumnname.apply(df, colname_old, '', inplace=True)

        if ('processedby' in colname_proc):

            # The column has been modified, with modifications
            # either applied in place or stored in a new column

            add = colname_proc

            if isinstance(coldict, dict):

                # Map the derived column to its intended name after renaming

                colname_new = get_key(column[colname_old])
                colname_proc_new = re.sub(colname_old, colname_new, colname_proc)

                add = {colname_proc: colname_proc_new}

                if isinstance(coldict[colname_old], dict):

                    # Duplicate dtype conversion settings to the derived column

                    colname_proc_dtype = coldict[colname_old][colname_new]

                    add = {colname_proc: {colname_proc_new: colname_proc_dtype}}

            if (colname_old not in columns):

                # The column has been modified in place during processing:
                # Update the `variables` section in `config` to remove
                # the settings for the original column

                del config['variables'][idx]

        if add is not None:

            # Update the `variables`section in `config` to include
            # the settings for the post-processing column

            config['variables'].append(add)

    if addcolumns is not None:

        # Add the columns generated during processing
        # to the list of columns to keep

        selected_columns = get_keys(config['variables'])
        for col in addcolumns:
            if col not in selected_columns:
                config['variables'].append(col)

    return config


def rename_columns(config):

    config_variables = config['variables']
    colnames_mapping = {}

    for coldict in config_variables:

        if isinstance(coldict, str):
            colnames_mapping[coldict] = coldict

        else:
            colname_old = get_key(coldict)
            colname_new = get_key(coldict[colname_old])
            colnames_mapping[colname_old] = colname_new

    return colnames_mapping


def dtypeconversion(df, config, indent=''):

    config_variables = config['variables']

    for column in config_variables:

        if isinstance(column, dict):
            colname_old = get_key(column)
            if isinstance(column[colname_old], dict):
                colname_new = get_key(column[colname_old])
                coltype = column[colname_old][colname_new]
            else:
                coltype = ''
        else:
            coltype = ''

        known_key = (coltype in TYPE.keys())
        known_value = (coltype in TYPE.values())

        if (coltype != ''):

            if (known_key or known_value):

                try:
                    if 'datetime' in coltype:
                        df = convertdatetype.apply(df, datekey=colname_old, format='ISO8601')

                    if known_key:
                        df[colname_old] = df[colname_old].astype(TYPE[coltype])
                    else:
                        df[colname_old] = df[colname_old].astype(coltype)
                except (TypeError, ValueError):
                    print(indent + f"WARNING | Failed to convert '{colname_old}' to `{coltype}`")
                    coltype = ''

            else:

                print(indent + f"INFO | '{colname_old}': `{coltype}` is not a recognized type")
                try:
                    df[colname_old] = df[colname_old].astype(coltype)
                except (TypeError, ValueError):
                    print(indent + f"WARNING | Failed to convert '{colname_old}' to `{coltype}`")
                    coltype = ''

        if (coltype == ''):

            print(indent + f"INFO | Convert '{colname_old}' to `str` by default")
            df[colname_old] = df[colname_old].astype('string')

    return df


def processing_data(df, config, init=False, indent=''):

    # Standardize the missing values

    print(indent + f'* dataframe')
    print(indent + f'** standardizenan')
    print()
    df = standardizenan.apply(df, key=None, letters_only=False)

    columns_before = set(df.columns)

    # Perform multiple processing steps to curate the dataset

    df = tools.apply(df, config['processing'], indent=indent)

    isvariable = ('variables' in config.keys())

    # Update `variables` section in `config`

    if isvariable and init:
        columns_after = set(df.columns)
        generated_columns = list(columns_after - columns_before)
        config = update_config(config, list(df.columns), addcolumns=generated_columns)

    if isvariable:

        # Select the columns

        print(indent + f'* dataframe')
        print(indent + f'** columnselection')
        print()

        colnames_mapping = rename_columns(config)
        df = df[list(colnames_mapping.keys())]

        # Apply dtype conversion

        print(indent + f'* dataframe')
        print(indent + f'** dtypeconversion')
        print()

        df = dtypeconversion(df, config, indent=indent)

        # Rename the columns

        print(indent + f'* dataframe')
        print(indent + f'** columnrenaming')
        if not init:
            print()

        df = df.rename(columns=colnames_mapping)

    if init:
        colnames = list(df.columns)
        Nlines = math.ceil(len(colnames)/2)
        for line in range(Nlines):
            string = indent + ' '.join(colnames[line*2:line*2+2])
            print(string)
        print()

    return df, config


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Curate marine data')
    parser.add_argument('config_file', type=str, help='path to the yaml configuration file')
    args = parser.parse_args()

    config = yaml.safe_load(open(args.config_file,'r'))

    if ('data' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'data' section")

    config = config['data']

    if ('inputfile_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'inputfile_path' section")
    if ('inputdir_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'inputdir_path' section")
    if ('outputdir_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'outputdir_path' section")
    if ('outputfile_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'outputfile_path' section")
    if ('processing' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'processing' section")

    if len(os.path.dirname(config['outputfile_path'])) == 0:
        outputfile = os.path.join(config['outputdir_path'],config['outputfile_path'])
     else:
        outputfile = config['outputfile_path']

    isvariable = ('variables' in config.keys())
    if not isvariable:
        print(indent + "INFO | `variables` section not found: column filtering, type casting, and renaming will be skipped")

    print(f"----- Start cleaning: {config['inputfile_path']} -----")
    print()

    start_cleaning = time.time()

    # Set `stdnan` to False since all missing values in the database
    # will be standardized before any processing steps are applied

    config = yaml.safe_load(re.sub("'stdnan': .*?,","'stdnan': False,",config))

    # If specified, apply the `marineloc` filter

    marineloc_filter = [(idx, filter) for idx,filter in enumerate(config['processing']) if 'marineloc' in str(filter)]

    if len(marineloc_filter) > 1:
        raise Exception(f"`clean.py` | `marineloc` should be specified only once in the `config` file")

    if len(isinworms_filter) == 1:

        marineloc_idx = marineloc_filter[0][0]
        marineloc_params = marineloc_filter[0][1]['tool'][0]['marineloc']
        marineloc_params['indent'] = '   '

        print('Pre-processing')
        print('--------------')
        print()
        print(f"* {marineloc_params['latkey']}, {marineloc_params['lonkey']}")
        print('** marineloc')
        print()

        config['inputfile_path'] = marineloc.apply(**marineloc_params)

        print()

        del config['processing'][marineloc_idx]

    # If `isinworms` is specified, generate the necessary filters using `createwormsfilters`

    isinworms_filter = [filter for filter in config['processing'] if 'isinworms' in str(filter)]
    isinworms_column = get_keys(isinworms_filter)

    if len(isinworms_filter) > 1:
        raise Exception(f"`clean.py` | `isinworms.py` must be applied to a single column. Select either {','.join(isinworms_column[:-1])} or {isinworms_column[-1]}")

    if len(isinworms_filter) == 1:

        # Set up the required components to apply the `isinworms` filter

        isinworms_column = isinworms_column[0]
        isinworms_column_idx = get_keys(config['processing']).index(isinworms_column)
        isinworms_idx = get_keys(config['processing'][isinworms_column_idx][isinworms_column]).index('isinworms')
        isinworms_params = config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']
        isinworms_args = list(isinworms_params.keys())

        if 'outputpath' not in isinworms_args:
            config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['outputpath'] = config['inputdir_path']
            isinworms_params = config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']
            isinworms_args = list(isinworms_params.keys())

        createwormsfilters_args = list(inspect.signature(cwf.create_WoRMSfilter).parameters.keys())
        createwormsfilters_params = {arg : isinworms_params[arg] for arg in isinworms_args if arg in createwormsfilters_args}
        createwormsfilters_params['store'] = True
        createwormsfilters_params['indent'] = '   '
        createwormsfilters_params['store_parallel'] = True
        createwormsfilters_params['colname'] = isinworms_column
        createwormsfilters_params['filepath'] = config['inputfile_path']

        ## Load existing filters or generate new ones if none are found

        print('Initialization')
        print('--------------')
        print()
        print(f'* {isinworms_column}')
        print('** createwormsfilters')
        print()

        worms_matchfilter, worms_acceptedfilter = cwf.create_WoRMSfilter(**createwormsfilters_params)

        print()

        ## Add the filters to `config`

        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['matchfilter'] = worms_matchfilter.copy(deep=True)
        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['acceptedfilter'] = worms_acceptedfilter.copy(deep=True)

        del worms_matchfilter
        del worms_acceptedfilter

    # Load specified dtypes

    dtypes_mapping = get_dtypes(config)

    # Read the gzip text data file

    print('Processing')
    print('----------')
    print()

    open_file, decode_line = readfile.apply(config['inputfile_path'])

    with open_file(config['inputfile_path'],'r') as data:

        header = decode_line(data.readline()).strip('\n').split('\t')
        header_length = len(header)

        colnames_mapping = rename_columns(config)

        init = True
        batch = 0
        data2clean = []
        error = []

        start = time.time()
        for idx, line in enumerate(data):

            # Add observations

            obs = decode_line(line).strip('\n').split('\t')
            obs = [preprocessquotationmark(value) for value in obs]

            if len(obs) == header_length:
                data2clean.append(obs)
                batch += 1
            else:
                error.append(idx+2)
                print()
                print(f'    SplittingError: splitting line n°{idx+2} yields a different number of fields ({len(obs)}) than the header ({header_length}).')
                print(f'                    line n°{idx+2} is skipped : {line}')

            if batch == BATCH_SIZE:

                df2clean = pd.DataFrame(data2clean, columns=header)
                df2clean = df2clean.astype(dtypes_mapping)

                # Process data

                print(f'Processing | {idx+1} lines')
                df2clean, config = processing_data(df2clean, config, init=init, indent='')
                print()

                # Store data

                writedataframe.to_txt(df2clean, outputfile, init=init, verbose=True, indent='')

                end = time.time()
                print(f'TIME : {np.round(end-start,0)}s')
                print()

                init = False
                data2clean.clear()
                batch = 0
                start = time.time()

    if batch != 0:

        df2clean = pd.DataFrame(data2clean, columns=header)
        df2clean = df2clean.astype(dtypes_mapping)

        # Process data

        print()
        print(f'Processing | {idx+1} lines done (end of file)')
        df2clean, config = processing_data(df2clean, config, init=init, indent='')

        # Store data

        writedataframe.to_txt(df2clean, outputfile, init=init, verbose=True, indent='')

        end = time.time()
        print(f'TIME : {np.round(end-start,0)}s')
        print()

    print()
    print(f"----- End cleaning {config['inputfile_path']} -----")
    print()

    print(f'TIME: {np.round(time.time() - start_cleaning,0)}s')

    if len(error) != 0:
        print(indent + f'ERROR:')
        print(indent + f'SplittingError: {len(error)} observations produced a different number of fields upon splitting compared to the header, and were consequently ignored.')
        print(f'Refer to lines: {error}')
