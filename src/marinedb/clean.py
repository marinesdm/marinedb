#!/usr/bin/python
# coding: utf-8

# External imports

import os
import re
import gzip
import yaml
import time
import copy
import math
import inspect
import argparse
import numpy as np
import pandas as pd
from os.path import expanduser

# Internal import

import tools
from marinedb.tools import getcolumnname
from marinedb.tools import convertdatetype
from marinedb.tools.marineloc import marineloc
from marinedb.tools.taxonomic import createwormsfilters as cwf

from marinedb.utils import readfile
from marinedb.utils import writedataframe
from marinedb.utils import standardizenan
from marinedb.utils import getdefaultargs
from marinedb.utils import preprocessquotationmark
from marinedb.utils.printverbose import printv

# Global variable

TYPE = {
        'int':'Int64',
        'float':'Float64',
        'str':'string', #preserve NaN
        'bool':'boolean',
        'datetime':'datetime64[ns]'
       }

SUPPORTED_FUNCTIONS = ['marineloc',
                       'createwormsfilters',
                       'isinworms',
                       'contains',
                       'doesnotcontain',
                       'dropvalues',
                       'isboundedby',
                       'isin',
                       'isna',
                       'notisin',
                       'doeslateqlon',
                       'isbelow_minlatlonprecision',
                       'iszero',
                       'lettersonly',
                       'taxasubset',
                       'parsedate',
                       'processdateinterval',
                       'splitdate',
                       'temporal']

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

def get_procfunc(config):

    config_proc = config['processing']

    procfuncs = set()
    for i, procstep in enumerate(config['processing']):
        colname = get_key(procstep)
        for j, func in enumerate(procstep[colname]):
            procfuncs.update([get_key(func)])

    return list(procfuncs)

def overwrite_outputdirarg(config, inputdir, outputdir):

    isprint = False

    config_proc = config['processing']

    for i, procstep in enumerate(config['processing']):
        colname = get_key(procstep)
        for j, func in enumerate(procstep[colname]):
            funcname = get_key(func)
            if funcname == 'createwormsfilters':
                funcargs = list(inspect.signature(eval(f'tools.{funcname}.create_WoRMSfilter')).parameters.keys())
            else:
                funcargs = list(inspect.signature(eval(f'tools.{funcname}.apply')).parameters.keys())
            if 'outputdir' in funcargs:
                if funcname in ['marineloc', 'createwormsfilters']:
                    print(f"INFO | '{colname}': override the `outputdir` argument in `{funcname}` with the `inputdir_path` value from the configuration file")
                    config['processing'][i][colname][j][funcname]['outputdir'] = inputdir
                    isprint = True
                else:
                    print(f"INFO | '{colname}': override the `outputdir` argument in `{funcname}` with the `outputdir_path` value from the configuration file")
                    config['processing'][i][colname][j][funcname]['outputdir'] = outputdir
                    isprint = True
            elif 'outputdir_createwormsfilters' in funcargs:
                print(f"INFO | '{colname}': override the `outputdir_createwormsfilters` argument in `{funcname}` with the `inputdir_path` value from the configuration file")
                config['processing'][i][colname][j][funcname]['outputdir_createwormsfilters'] = inputdir
                isprint = True
            elif 'outputdir_isinworms' in funcargs:
                print(f"INFO | '{colname}': override the `outputdir_isinworms` argument in `{funcname}` with the `outputdir_path` value from the configuration file")
                config['processing'][i][colname][j][funcname]['outputdir_isinworms'] = outputdir
                isprint = True

    if isprint:
        print()

    return config

def get_dtypes(config):

    config_variables = config['variables']
    dtypes_mapping = {}

    for coldict in config_variables:

        if isinstance(coldict,dict):
            colname_old = get_key(coldict)
            if isinstance(coldict[colname_old], dict):
                colname_new = get_key(coldict[colname_old])
                coltype = coldict[colname_old][colname_new]
                if (coltype in TYPE.keys()):
                    coltype = TYPE[coltype]
                dtypes_mapping[colname_old] = coltype

    return dtypes_mapping


def update_config(df, config, addcolumns=None):
#    print('config variables before:')
#    print(config['variables']) #debug

    config_updated = copy.deepcopy(config)

    config_variables = []
    base_colmapping = {}
    for idx, coldict in enumerate(config['variables']):
        print('coldict:', coldict)
        add = None
        colname_old = get_key(coldict)

        # Retrieve column names post-processing

        _, colname_proc, _ = getcolumnname.apply(df, colname_old, '', inplace=True)
        print(colname_proc)
        if ('processedby' in colname_proc):

            # The column has been modified, with modifications
            # either applied in place or stored in a new column

            add = colname_proc

            if isinstance(coldict, dict):

                # Map the derived column to its intended name after renaming

                colname_new = get_key(coldict[colname_old])
                colname_proc_new = re.sub(colname_old, colname_new, colname_proc)

                add = {colname_proc: colname_proc_new}

                if isinstance(coldict[colname_old], dict):

                    # Duplicate dtype conversion settings to the derived column

                    colname_proc_dtype = coldict[colname_old][colname_new]

                    add = {colname_proc: {colname_proc_new: colname_proc_dtype}}

        if (colname_old in list(df.columns)):

            # The column has not been modified in place during processing:
            # Update the `variables` section in `config` to include
            # the settings for the original column

            config_variables.append(coldict)

#           del config['variables'][idx]

        if add is not None:

            # Update the `variables`section in `config` to include
            # the settings for the post-processing column

            config_variables.append(add)

        if isinstance(coldict, dict):
            colname_new = get_key(coldict[colname_old])
            base_colmapping.update({colname_old: colname_new})

    if addcolumns is not None:

        # Add the columns generated during processing
        # to the list of columns to keep

        selected_columns = get_keys(config_variables)
        for col in addcolumns:
            if col not in selected_columns:
                dtype = str(df[col].dtype)
                dtype = (dtype if (dtype != 'object') else 'string')
                add = {col:{col:dtype}}
                for colname_old, colname_new in base_colmapping.items():
                    if colname_old in col:
                        col_new = re.sub(colname_old, colname_new, col)
                        add = {col:{col_new:dtype}}
                        break
                config_variables.append(add)

    config_updated['variables'] = config_variables
#    print('config variables after:')
#    print(config_updated['variables']) #debug
    return config_updated


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


def dtypeconversion(df, config, verbose=True, indent=''):

    isprint = False

    config_variables = config['variables']

    for column in config_variables:

        colname_old = get_key(column)
        if isinstance(column, dict):
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
                        printv(f"WARNING | When converting '{colname_old}' to datetime, missing days and months will default to the 1st and January", verbose=verbose, indent=indent)
                        isprint = True
                        df = convertdatetype.apply(df, datekey=colname_old, format='ISO8601')
                    if known_key:
                        df[colname_old] = df[colname_old].astype(TYPE[coltype])
                    else:
                        df[colname_old] = df[colname_old].astype(coltype)
                except (TypeError, ValueError):
                    printv(f"WARNING | Failed to convert '{colname_old}' to `{coltype}`", verbose=verbose, indent=indent)
                    coltype = ''
                    isprint = True
#                    df[colname_old] = df[colname_old].astype(TYPE[coltype]) #debug

            else:

                printv(f"INFO | '{colname_old}': `{coltype}` is not a recognized type", verbose=verbose, indent=indent)
                isprint = True
                try:
                    df[colname_old] = df[colname_old].astype(coltype)
                except (TypeError, ValueError):
                    printv(f"WARNING | Failed to convert '{colname_old}' to `{coltype}`", verbose=verbose, indent=indent)
                    isprint = True
                    coltype = ''

        if (coltype == ''):

            printv(f"INFO | Convert '{colname_old}' to `str` by default", verbose=verbose, indent=indent)
            isprint = True
            df[colname_old] = df[colname_old].astype('string')

    if isprint:
        printv('', verbose=verbose)

    return df


def curate_data(df, config, config_updated, init=False, verbose=True, indent=''):

    isvariable = ('variables' in config.keys())

    # Standardize the missing values

    printv(f'* dataframe', verbose=verbose, indent=indent)
    printv(f'** standardizenan', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)
    df = standardizenan.apply(df, key=None, letters_only=False)

    columns_before = set(df.columns)

    # Convert dtypes, if possible

    if isvariable:

        dtypes_mapping = get_dtypes(config)

        for key,value in dtypes_mapping.items():
            try:
                if value == 'Int64':
                    df[key] = df[key].astype('Float64').astype('Int64')
                else:
                    df[key] = df[key].astype(value)
            except ValueError:
                pass

    # Perform multiple processing steps to curate the dataset

    df = tools.apply(df, config['processing'], verbose=verbose, indent=indent)

    # Update `variables` section in `config`

    if isvariable and init:
        columns_after = set(df.columns)
        generated_columns = list(columns_after - columns_before)
        config_updated = update_config(df, config, addcolumns=generated_columns)

    if isvariable:

        # Select the columns

        printv(f'* dataframe', verbose=verbose, indent=indent)
        printv(f'** columnselection', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        colnames_mapping = rename_columns(config_updated)
        df = df[list(colnames_mapping.keys())]

        # Apply dtype conversion

        printv(f'* dataframe', verbose=verbose, indent=indent)
        printv(f'** dtypeconversion', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        df = dtypeconversion(df, config_updated, indent=indent + '   ')

        # Rename the columns

        printv(f'* dataframe', verbose=verbose, indent=indent)
        printv(f'** columnrenaming', verbose=verbose, indent=indent)
        printv('', verbose=verbose)

        df = df.rename(columns=colnames_mapping)

    if init:
        colnames = list(df.columns)
        Nlines = math.ceil(len(colnames)/4)
        for line in range(Nlines):
            string = indent + '   ' + ' '.join(colnames[line*4:line*4+4])
            printv(string, verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

    return df, config, config_updated

def process_one_dataframe(df, columns, config, config_updated, outputfile, cpu_idx=None, verbose=True, init=False, indent=''):

    start = time.time()

    df, config, config_updated = curate_data(df, config, config_updated, init=init, verbose=verbose, indent=indent)

    # Store data

    if cpu_idx is not None:
        temp = outputfile.split('.')
        outputfile = temp[0] + '%02d' % cpu_idx
        if len(temp) == 2:
            outputfile += temp[1]

    writedataframe.to_txt(df[columns], outputfile, init=init, verbose=verbose, indent=indent)

    end = time.time()
    if cpu_idx is not None:
        printv(f'CPU n°{cpu_idx}: {len(df)} lines done | TIME : {np.round(end-start,0)}s', verbose=verbose, indent=indent)
    else:
        printv(f'>>>>>> {len(df)} lines done | TIME : {np.round(end-start,0)}s', verbose=verbose)
        printv('', verbose=verbose)

    return config

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Curate marine data')
    parser.add_argument('config_file', type=str, help='path to the yaml configuration file')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='whether to parallelize on multiple CPUs', default=False)
    parser.add_argument('--cpu', type=int, help='number of CPUs to be used', default=None)
    args = parser.parse_args()

    config = yaml.safe_load(open(args.config_file,'r'))

    if ('data' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'data' section")

    config = config['data']

    if ('inputfile_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'inputfile_path' section")
    config['inputfile_path'] = expanduser(config['inputfile_path'])
    if (not os.path.isfile(config['inputfile_path'])):
        raise FileNotFoundError(f"`clean.py` | No such file: '{config['inputfile_path']}'")

    if ('inputdir_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'inputdir_path' section")
    config['inputdir_path'] = expanduser(config['inputdir_path'])
    if (not os.path.isdir(config['inputdir_path'])):
        raise FileNotFoundError(f"`clean.py` | No such directory: '{config['inputdir_path']}'")

    if ('outputdir_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'outputdir_path' section")
    config['outputdir_path'] = expanduser(config['outputdir_path'])
    if (not os.path.isdir(config['outputdir_path'])):
        try:
            os.mkdir(config['outputdir_path'])
        except FileExistsError:
            pass

    if ('outputfile_path' not in config.keys()):
         inputfile = os.path.basename(config['inputfile_path']).split('.')
         if len(inputfile) > 2:
             raise Exception("`clean.py` | `filepath` contains dots ('.') outside of the file extension")
         config['outputfile_path'] = inputfile[0] + f'_processedby_marinedb'
         if len(inputfile) == 2:
             config['outputfile_path'] += f'.{inputfile[1]}'
         print(f"INFO | The processed file will be stored at {config['outputfile_path']}")
    if len(os.path.dirname(config['outputfile_path'])) == 0:
        config['outputfile_path'] = os.path.join(config['outputdir_path'], config['outputfile_path'])
    print(config['outputfile_path'])
    if ('processing' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'processing' section")

    outputfile = expanduser(config['outputfile_path'])

    isvariable = ('variables' in config.keys())
    if not isvariable:
        print('INFO | `variables` section not found: column filtering, type casting, and renaming will be skipped')

    # Verify that only supported functions are specified in the configuration files

    procfuncs = get_procfunc(config)
    unsupported_funcs = set(procfuncs) - set(SUPPORTED_FUNCTIONS)
    if len(unsupported_funcs) != 0:
        marineloc_funcs = unsupported_funcs.intersection(['createmask','createmarinefilter', 'filtermarinelocations', 'island', 'split_pandas_parquet'])
        unsupported_funcs = [f'`{func}`' for func in unsupported_funcs]
        error = f"`clean.py` | {','.join(list(unsupported_funcs))} are not supported functions."
        if len(marineloc_funcs) != 0:
            marineloc_funcs = [f'`{func}`' for func in marineloc_funcs]
            error += f" Use `marineloc` in place of {','.join(marineloc_funcs)}."
        raise Exception(error)

    print()
    print(f"----- Start cleaning: {config['inputfile_path']} -----")
    print()

    start_cleaning = time.time()

    # Set `stdnan` to False since all missing values in the database
    # will be standardized before any processing steps are applied

    config = re.sub(r"'stdnan': .*?(?=,|})", r"'stdnan': False", str(config))

    # Set `drop_empty` to False to ensure that each batch has the same number of columns after processing

    config = re.sub(r"'drop_empty': .*?(?=,|})", r"'drop_empty': False", config)

    # Parse 'True' and 'False' strings as Boolean True and False values

    config = re.sub(r"'True'", r"True", config)
    config = re.sub(r"'False'", r"False", config)

    # Convert the `config` string back into a dictionary

    config = config.encode('utf8').decode('unicode_escape')
    config = yaml.safe_load(config)

    # For all functions with an `outputdir` argument, substitute the argument
    # with the configuration file's inputdir_path or outputdir_path value

    config = overwrite_outputdirarg(config, config['inputdir_path'], config['outputdir_path'])

    ispreprocessing = False

    # If specified, apply the `marineloc` filter

    marineloc_filter = [(idx, filter) for idx,filter in enumerate(config['processing']) if 'marineloc' in str(filter)]

    if len(marineloc_filter) > 1:
        raise Exception(f"`clean.py` | `marineloc` should be specified only once in the `config` file")

    if len(marineloc_filter) == 1:

        marineloc_idx = marineloc_filter[0][0]
        marineloc_params = marineloc_filter[0][1]['tool'][0]['marineloc']
        marineloc_params['indent'] = '   '

        if not ispreprocessing:
            print('Preprocessing')
            print('--------------')
            print()
            ispreprocessing = True

        if ('latkey' in marineloc_params) and ('lonkey' in marineloc_params):
            print(f"* {marineloc_params['latkey']}, {marineloc_params['lonkey']}")
        print('** marineloc')
        print()

        config['inputfile_path'] = marineloc.apply(**marineloc_params)

        print()

        del config['processing'][marineloc_idx]

    # If `createwormsfilters` or `isinworms` is specified,
    # generate the necessary filters using `createwormsfilters`

    ## Verify if `createwormsfilters` is specified
    createwormsfilters_filter = [(idx, filter) for idx,filter in enumerate(config['processing']) if "'createwormsfilters'" in str(filter)]
    createwormsfilters_column = get_keys([filter[1] for filter in createwormsfilters_filter])
    if len(createwormsfilters_filter) > 1:
        raise Exception(f"`clean.py` | `createwormsfilters.py` must be applied to a single column. Select either {','.join(createwormsfilters_column[:-1])} or {isinworms_column[-1]}")

    ## Verify if `isinworms` is specified
    isinworms_filter = [(idx, filter) for idx,filter in enumerate(config['processing']) if "'isinworms'" in str(filter)]
    isinworms_column = get_keys([filter[1] for filter in isinworms_filter])
    if len(isinworms_filter) > 1:
        raise Exception(f"`clean.py` | `isinworms.py` must be applied to a single column. Select either {','.join(isinworms_column[:-1])} or {isinworms_column[-1]}")

    is_createwormsfilters = (len(createwormsfilters_filter) == 1)
    is_isinworms = (len(isinworms_filter) == 1)

    ## Ensure that if `createworms` is specified, `isinworms` is specified as well
    if is_createwormsfilters and not is_isinworms:
        raise Exception(f'`clean.py` | `isinworms` must be specified when using `createwormsfilter`')

    if is_createwormsfilters or is_isinworms:

        # Set up the required components to apply the `isinworms` filter

        ## Default `createwormsfilters` parameters
        default_createwormsfilters_params = getdefaultargs.apply(cwf.create_WoRMSfilter)
        default_createwormsfilters_args = list(default_createwormsfilters_params.keys())

        ## Extract `createwormsfilters` parameters from the `isinworms` configuration
        isinworms_column_idx = isinworms_filter[0][0]
        isinworms_column = isinworms_column[0]
        isinworms_idx = get_keys(config['processing'][isinworms_column_idx][isinworms_column]).index('isinworms')
        isinworms_params = config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']
        isinworms_args = list(isinworms_params.keys())

        isinworms_createwormsfilters_params = {arg : isinworms_params[arg] for arg in isinworms_args if arg in default_createwormsfilters_args}
        isinworms_createwormsfilters_params['colname'] = isinworms_column
        isinworms_createwormsfilters_params['outputdir'] = isinworms_params['outputdir_createwormsfilters']
        if 'overwrite_createwormsfilters' in isinworms_args:
            isinworms_createwormsfilters_params['overwrite'] = isinworms_params['overwrite_createwormsfilters']
        if 'overwrite_parallel_createwormsfilters' in isinworms_args:
            isinworms_createwormsfilters_params['overwrite_parallel'] = isinworms_params['overwrite_parallel_createwormsfilters']
        isinworms_createwormsfilters_args = list(isinworms_createwormsfilters_params.keys())

        if is_createwormsfilters:

            ## Retrieve `createwormsfilters` parameters
            createwormsfilters_column_idx = createwormsfilters_filter[0][0]
            createwormsfilters_column = createwormsfilters_column[0]
            createwormsfilters_idx = get_keys(config['processing'][createwormsfilters_column_idx][createwormsfilters_column]).index('createwormsfilters')
            createwormsfilters_params = config['processing'][createwormsfilters_column_idx][createwormsfilters_column][createwormsfilters_idx]['createwormsfilters']
            createwormsfilters_params['colname'] = createwormsfilters_column
            createwormsfilters_args = list(createwormsfilters_params.keys())

            ## Extend the wormscall value to both `isinworms` and `createwormsfilters` if specified in either
            if 'wormscall' not in createwormsfilters_args:
                if 'wormscall' in isinworms_createwormsfilters_args:
                    print(f'INFO | `wormscall` not found in `createwormsfilters`, use value from `isinworms`')
                    createwormsfilters_params['wormscall'] = isinworms_createwormsfilters_params['wormscall']
                    createwormsfilters_args.append('wormscall')
            else:
                if 'wormscall' not in isinworms_createwormsfilters_args:
                    print(f'INFO | `wormscall` not found in `isinworms`, use value from `createwormsfilters`')
                    isinworms_createwormsfilters_params['wormscall'] = createwormsfilters_params['wormscall']
                    isinworms_createwormsfilters_args.append('wormscall')

            ## Set unspecified parameters in `createwormsfilters` to their default values
            for arg, val in default_createwormsfilters_params.items():
                if arg not in createwormsfilters_args:
                    createwormsfilters_params[arg] = val

            ## Ensure that parameter values in `isinworms` do not conflict with those in `createwormsfilters`
            intersection_args = set(isinworms_createwormsfilters_params.keys()).intersection(set(createwormsfilters_params.keys()))
            exclude_args = set(['filepath','identification_level','colname','store','store_parallel','max_attempt','verbose','indent'])
            intersection_args -= exclude_args
            conflicting_args = [f'`{arg}`' for arg in intersection_args if createwormsfilters_params[arg] != isinworms_createwormsfilters_params[arg]]
            if len(conflicting_args) != 0:
                raise Exception(f"`clean.py` | Conflicting {','.join(conflicting_args)} values between `createwormsfilters` and `isinworms`")

            ## Use parameters from `createwormsfilters` to complete the `isinworms` configuration
            for arg, val in createwormsfilters_params.items():
                if arg not in exclude_args:
                    if arg in ['overwrite', 'overwrite_parallel', 'outputdir']:
                        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms'][f'{arg}_createwormsfilters'] = createwormsfilters_params[arg]
                    else:
                        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms'][arg] = createwormsfilters_params[arg]
            print(config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms'])

        else:

            createwormsfilters_params = isinworms_createwormsfilters_params

        createwormsfilters_params['filepath'] = config['inputfile_path']
        createwormsfilters_params['indent'] = '   '
        createwormsfilters_params['store'] = True
        createwormsfilters_params['store_parallel'] = True

        ## Load existing filters or generate new ones if none are found

        print('Initialization')
        print('--------------')
        print()
        print(f"* {createwormsfilters_params['colname']}")
        print('** createwormsfilters')
        print()

        worms_matchfilter, worms_acceptedfilter = cwf.create_WoRMSfilter(**createwormsfilters_params)

        ## Add the filters to `config`

        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['matchfilter'] = worms_matchfilter.copy(deep=True)
        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['acceptedfilter'] = worms_acceptedfilter.copy(deep=True)

        del worms_matchfilter
        del worms_acceptedfilter
        if is_createwormsfilters:
            del config['processing'][createwormsfilters_column_idx][createwormsfilters_column][createwormsfilters_idx]

    # Read the gzip or uncompressed data file

    print('Processing')
    print('----------')
    print()

    parallel = ars.parallel
    cpu = args.cpu
    if not parallel:
        cpu = 1
    if (cpu is None) or (cpu == -1):
        cpu = len(os.sched_getaffinity(0))
    if cpu == 1:
        parallel = False

    open_file, decode_line = readfile.apply(config['inputfile_path'])

    with open_file(config['inputfile_path'],'r') as data:

        header = decode_line(data.readline()).strip('\n').split('\t')
        header_length = len(header)

        init = True
        batch = 0
        data2clean = []
        error = []
        config_updated = None

        start = time.time()
        for idx, line in enumerate(data):

            # Add observations

            obs = decode_line(line).strip('\n').split('\t')
            obs = [preprocessquotationmark.apply(value) for value in obs]

            if len(obs) == header_length:
                data2clean.append(obs)
                batch += 1
            else:
                error.append(idx+2)
                print()
                print(f'SplittingError: splitting line n°{idx+2} yields a different number of fields ({len(obs)}) than the header ({header_length}).')
                print(f'line n°{idx+2} is skipped : {line}')

            if batch == BATCH_SIZE:

                df2clean = pd.DataFrame(data2clean, columns=header)

                # Process data

                print(f'--- Processing | {batch} lines ---')
                print()
                df2clean, config, config_updated = curate_data(df2clean, config, config_updated, init=init, verbose=True, indent='')

                # Store data

                if init:
                    columns = list(df2clean.columns)

                writedataframe.to_txt(df2clean[columns], outputfile, init=init, verbose=True, indent='')

                end = time.time()
                print(f'TIME : {np.round(end-start,0)}s')
                print()

                init = False
                data2clean.clear()
                batch = 0
                start = time.time()

    if batch != 0:

        df2clean = pd.DataFrame(data2clean, columns=header)

        # Process data

        print(f'--- Processing | {batch} lines ---')
        print()

        df2clean, config, config_updated = curate_data(df2clean, config, config_updated, init=init, verbose=True, indent='')

        # Store data

        writedataframe.to_txt(df2clean[columns], outputfile, init=init, verbose=True, indent='')

        end = time.time()
        print(f'TIME : {np.round(end-start,0)}s')

    print()
    print(f"----- End cleaning {config['inputfile_path']} -----")
    print()

    print(f'TIME: {np.round(time.time() - start_cleaning,0)}s')

    if len(error) != 0:
        print(indent + f'ERROR:')
        print(indent + f'SplittingError: {len(error)} observations produced a different number of fields upon splitting compared to the header, and were consequently ignored.')
        print(f'Refer to lines: {error}')
