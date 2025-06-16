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
import glob
import inspect
import argparse
import pandas as pd
from itertools import groupby
from os.path import expanduser
from operator import itemgetter
from joblib import Parallel, delayed

# Internal import

import marinedb.tools as tools
from marinedb.tools import getcolumnname
from marinedb.tools import convertdatetype
from marinedb.tools.marineloc import marineloc
from marinedb.tools.taxonomic import taxasubset
from marinedb.tools.taxonomic import createwormsfilters as cwf

from marinedb.utils import readfile
from marinedb.utils import tqdmjoblib
from marinedb.utils import writedataframe
from marinedb.utils import standardizenan
from marinedb.utils import getdefaultargs
from marinedb.utils.printverbose import printv
from marinedb.utils import preprocessquotationmark

# Global variable

TYPE = {
        'int':'Int64',
        'float':'Float64',
        'str':'string', #preserve NaN
        'bool':'boolean',
        'datetime':'datetime64[ns]'
       }

SUPPORTED_PROCFUNCTIONS = ['marineloc',
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
                           'map_basisofrecord',
                           'parsedate',
                           'processdateinterval',
                           'splitdate',
                           'temporal']

SUPPORTED_POSTPROCFUNCTIONS = ['taxasubset']

BATCH_SIZE = 100000

# Parse the configuration file

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
            if isinstance(coldict[colname_old], dict):
                colname_new = get_key(coldict[colname_old])
                coltype = coldict[colname_old][colname_new]
                if (coltype in TYPE.keys()):
                    coltype = TYPE[coltype]
#                    print(colname_old, coltype) #debug
                dtypes_mapping[colname_old] = coltype

    return dtypes_mapping

def get_column_mapping(config):

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

# Update the configuration file

def get_procfunc(config, key):

    config_proc = config[key]

    procfuncs = set()
    for i, procstep in enumerate(config[key]):
        colname = get_key(procstep)
        for j, func in enumerate(procstep[colname]):
            procfuncs.update([get_key(func)])

    return list(procfuncs)

def overwrite_outputdir_stdnan_dropempty(config, inputdir, outputdir):

    isprint = False

    config_proc = list(zip(['processing']*len(config['processing']), config['processing']))
    config_proc = config_proc + list(zip(['postprocessing']*len(config['postprocessing']), config['postprocessing']))

    iprocessing = 0
    ipostprocessing = 0
    for proc in config_proc:

        proccat, procstep = proc
        i = (iprocessing if (proccat == 'processing') else ipostprocessing)
        colname = get_key(procstep)

        for j, func in enumerate(procstep[colname]):

            funcname = get_key(func)
            funcargs = list(inspect.signature(eval(f'tools.{funcname}.apply')).parameters.keys())

            # For all functions with an `outputdir` argument, substitute the argument
            # with the configuration file's `inputdir_path` or `outputdir_path value`

            if 'outputdir' in funcargs:
                if funcname in ['marineloc', 'createwormsfilters']:
                    print(f"INFO | '{colname}': override the `outputdir` argument in `{funcname}` with the `inputdir_path` value from the configuration file")
                    config[proccat][i][colname][j][funcname]['outputdir'] = inputdir
                    isprint = True
                else:
                    print(f"INFO | '{colname}': override the `outputdir` argument in `{funcname}` with the `outputdir_path` value from the configuration file")
                    config[proccat][i][colname][j][funcname]['outputdir'] = outputdir
                    isprint = True
            if 'outputdir_createwormsfilters' in funcargs:
                print(f"INFO | '{colname}': override the `outputdir_createwormsfilters` argument in `{funcname}` with the `inputdir_path` value from the configuration file")
                config[proccat][i][colname][j][funcname]['outputdir_createwormsfilters'] = inputdir
                isprint = True
            if 'outputdir_isinworms' in funcargs:
                print(f"INFO | '{colname}': override the `outputdir_isinworms` argument in `{funcname}` with the `outputdir_path` value from the configuration file")
                config[proccat][i][colname][j][funcname]['outputdir_isinworms'] = outputdir
                isprint = True

            # For all functions with an `stdnan` argument, set `stdnan` to False since all missing
            # values in the database will be standardized before any processing steps are applied

            if 'stdnan' in funcargs:
                print(f"INFO | '{colname}': set `stdnan` argument in `{funcname}` to False")
                config[proccat][i][colname][j][funcname]['stdnan'] = False
                isprint = True

            # For all functions with an `stdnan` argument, set `drop_empty` to False
            # to ensure that each batch has the same number of columns after processing

            if 'drop_empty' in funcargs:
                print(f"INFO | '{colname}': set `drop_empty` argument in `{funcname}` to False")
                config[proccat][i][colname][j][funcname]['drop_empty'] = False
                isprint = True

        if proccat == 'processing':
            iprocessing += 1
        else:
            ipostprocessing += 1

    if isprint:
        print()

    return config

def overwrite_cpu(config, cpu_subprocess):

    anyparallel = False

    for i, procstep in enumerate(config['processing']):
        colname = get_key(procstep)
        for j, func in enumerate(procstep[colname]):
            funcname = get_key(func)
            if funcname not in ['marineloc', 'createwormsfilters', 'isinworms']:
                funcparams = getdefaultargs.apply(eval(f'tools.{funcname}.apply'))
                if ('parallel' in funcparams.keys()):
                    params = config['processing'][i][colname][j][funcname]
                    if ('parallel' in params.keys()) and (params['parallel']):
                        config['processing'][i][colname][j][funcname]['cpu'] = cpu_subprocess
                        anyparallel = True
                    if ('parallel' not in params.keys()) and (funcparams['parallel']):
                        config['processing'][i][colname][j][funcname]['cpu'] = cpu_subprocess
                        anyparallel = True

    return config, anyparallel

def set_cpu(config, parallel, cpu_main=None, cpu_max=None):

    if cpu_max is None:
        cpu_max = len(os.sched_getaffinity(0))

    if (cpu_main == -1):
        cpu_main = cpu_max

    if ((cpu_main is not None) and (cpu_main > 1)) and (not parallel):
        raise ValueError(f'`clean.py` | cpu_main={cpu_main} > 1 but parallel={parallel}')

    if (cpu_main is None):
        if parallel:
            cpu_main = cpu_max
        else:
            cpu_main = 1

    if (cpu_main > 1):

        # Avoid nested parallelism when using joblib

        cpu_main = min(cpu_main, cpu_max)
        cpu_subprocess = 1
        config, anyparallel = overwrite_cpu(config, cpu_subprocess)
        if anyparallel:
            print(f'INFO | Since parallel={parallel} and cpu={cpu_main}, each subprocess is restricted to a single CPU to prevent nested parallelism')

    if (cpu_main == 1):
        if parallel:
            parallel = False
            cpu_subprocess = cpu_max
            config, anyparallel = overwrite_cpu(config, cpu_subprocess)
            if anyparallel:
                print(f'INFO | Since the main process is not parallelized (cpu={cpu_main}), {cpu_subprocess} CPUs are allocated for parallelized subprocesses')

    return parallel, cpu_main

def update_config(df, config, addcolumns=None):

    config_updated = copy.deepcopy(config)

    config_variables = []
    base_colmapping = {}
    for idx, coldict in enumerate(config['variables']):

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

        if add is not None:

            # Update the `variables` section in `config` to include
            # the settings for the post-processing column

            config_variables.append(add)

        if (colname_old != 'issue') and isinstance(coldict, dict):
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

    return config_updated

# Apply configuration settings

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

def curate_data(df, config, config_updated, init=False, verbose=True, indent='', partition=None): #debug i

    isvariable = ('variables' in config.keys())

    # Standardize the missing values

    printv(f'* dataframe', verbose=verbose, indent=indent)
    printv(f'** standardizenan', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    df = standardizenan.apply(df, key=None, additional_policy='contains_letters_or_digits')

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
            except (TypeError, ValueError):
                pass

    # Perform multiple processing steps to curate the dataset

    df = tools.apply(df, config['processing'], verbose=verbose, indent=indent, partition=partition, outputdir_marinedb=config['outputdir_path'])

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

        colnames_mapping = get_column_mapping(config_updated)
        df = df[list(colnames_mapping.keys())]

        # Apply dtype conversion

        printv(f'* dataframe', verbose=verbose, indent=indent)
        printv(f'** dtypeconversion', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        df = dtypeconversion(df, config_updated, verbose=verbose, indent=indent + '   ')

        # Rename the columns

        printv(f'* dataframe', verbose=verbose, indent=indent)
        printv(f'** columnrenaming', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        df = df.rename(columns=colnames_mapping)

    return df, config, config_updated

def process_one_dataframe(df, config, config_updated, outputfile, outputdir='', columns=None, cpu_idx=None, init_process=False, init_storage=False, verbose=True, indent=''):

    if cpu_idx is not None:
        if (cpu_idx!=0) and (len(outputdir) == 0): #debug
            raise Exception #debug
        temp = os.path.basename(outputfile).split('.')
        outputfile = temp[0] + '_temp%05d' % cpu_idx
        if len(temp) == 2:
            outputfile += f'.{temp[1]}'
        outputfile = os.path.join(outputdir,outputfile)

        init_storage = True
        verbose = False

    nlines = len(df)

    start = time.time()

    params = {
              'init': init_process,
              'verbose': verbose,
              'indent': indent,
              'partition': cpu_idx
             }

    df, config, config_updated = curate_data(df, config, config_updated, **params)

    # Store data

    if columns is None:
        columns = list(df.columns)

    if len(df) != 0:
        writedataframe.to_txt(df[columns], outputfile, init=init_storage, verbose=verbose, indent=indent)

    end = time.time()

    if cpu_idx is not None:
        printv(f'CPU n°{cpu_idx}: {len(df)} lines remaining | TIME : {round(end-start,0)}s', verbose=True, indent=indent)
        if len(df) != 0:
            printv(f'>>> save to {outputfile}', verbose=True, indent=indent)
        printv('', verbose=True)
    else:
        printv(f'>>>>>> {nlines} lines done | TIME : {round(end-start,0)}s', verbose=verbose)
        printv('', verbose=verbose)

    return config_updated, columns

def read_firstlastindex(inputfile):

    with open(inputfile,'rb') as f:

        header = f.readline().decode().strip('\n').split('\t')
        index_idx = header.index('index_marinedb')
        first_line = f.readline().decode()

        try:
            f.seek(-2,2)
            while f.read(1) != b'\n':
                f.seek(-2,1)
        except OSError:
           f.seek(0)

        last_line = f.readline().decode()

    first_index = int(first_line.strip('\n').split('\t')[index_idx])
    last_index = int(last_line.strip('\n').split('\t')[index_idx])

    return first_index, last_index

def minmax_consecutive(numbers):

    minmax_groups = []

    for k, g in groupby(enumerate(numbers), lambda ix: ix[0] - int(ix[1])):
        group = list(map(itemgetter(1), g))
        minmax_groups += [min(group), max(group)]

    return minmax_groups

def resume_parallel_processing(outputdir):

    fileslist = glob.glob(os.path.join(outputdir, '*'))
#    fileslist = sorted(glob.glob(os.path.join(outputdir, '*')))
#    basepath = fileslist[0].split('_temp')[0]
#    extension = fileslist[0].split('_temp')[1].split('.')
#    if len(extension) > 1:
#        extension = f'.{extension[1]}'
#    else:
#        extension = ''

    filesnumber = pd.Series(fileslist).str.findall(r'(?<=_temp)[0-9]+')
#    print('filesnumber:', filesnumber)
    if any(filesnumber.str.len() > 1):
        bad_filenames = pd.Series(fileslist)[filesnumber.str.len() > 1].tolist()
        raise Exception(f"`clean.py` | Unsupported file names: {','.join(bad_filenames)}. The file name must contain exactly one number.")
    filesnumber = sorted(filesnumber.str[0].tolist())
#    nonconsecutive_files = minmax_consecutive(filesnumber)
#    nonconsecutive_files = [basepath + f'_temp{number}' + extension for number in nonconsecutive_files]
#    print('nonconsecutive_files:',nonconsecutive_files)

#    nonconsecutive_indices = [read_firstlastindex(f) for f in nonconsecutive_files]
#    print('nonconsecutive_indices', nonconsecutive_indices)
#    nonconsecutive_indices = sorted(nonconsecutive_indices, key=lambda x: x[0]) #normalement inutile mais bug
#    print('nonconsecutive_indices', nonconsecutive_indices)
#    nonconsecutive_indices = [index[0] if (i % 2 == 0) else index[1] for i,index in enumerate(nonconsecutive_indices)]
#    print('nonconsecutive_indices', nonconsecutive_indices)
#    index_pairs = list(zip(nonconsecutive_indices[1::2], nonconsecutive_indices[2::2]))
#    print('index_pairs:',index_pairs)
    firstlast_pairs = [read_firstlastindex(f) for f in fileslist]
    firstlast_pairs = sorted(firstlast_pairs, key=lambda x: x[0])
#    print('firstlast_pairs:',firstlast_pairs)
    Npairs = len(firstlast_pairs)
    nonconsecutive_indices = [(firstlast_pairs[i][1], firstlast_pairs[i+1][0]) for i in range(Npairs - 1) if (firstlast_pairs[i][1] != (firstlast_pairs[i+1][0] - 1))]
#    print('nonconsecutive_indices', nonconsecutive_indices)

    find_missing_indices = []
    if firstlast_pairs[0][0] != 0:
        find_missing_indices += [f'(x < {firstlast_pairs[0][0]})']
    if len(nonconsecutive_indices) != 0:
        find_missing_indices += [' or '.join(f'((x > {i}) and (x < {j}))' for i,j in nonconsecutive_indices)]
    find_missing_indices += [f'(x > {firstlast_pairs[-1][1]})']
    find_missing_indices = ' or '.join(find_missing_indices)
##    if int(filesnumber[0]) != 0:
#    if nonconsecutive_indices[0] != 0:
#        find_missing_indices += [f'(x < {nonconsecutive_indices[0]})']
#    if len(index_pairs) != 0:
#        find_missing_indices += [' or '.join(f'((x > {i}) and (x < {j}))' for i,j in index_pairs)]
#    find_missing_indices += [f'(x > {nonconsecutive_indices[-1]})']
##        print('find_missing_indices:', find_missing_indices)
#    find_missing_indices = ' or '.join(find_missing_indices)
    print('find_missing_indices:', find_missing_indices)
    find_missing_indices = eval('lambda x: ' + find_missing_indices)

#    last_index = nonconsecutive_indices[-1]
    last_index = firstlast_pairs[-1][1]
    last_file = int(filesnumber[-1])
#    print(f'last_index: {last_index}, last_file: {last_file}')
    with open(fileslist[0],'r') as f:
        columns = f.readline().strip('\n').split('\t')

    return find_missing_indices, last_index, last_file, columns

def resume_noparallel_processing(outputfile):

    _, last_index = read_firstlastindex(outputfile)
    find_missing_indices = eval(f'lambda x: x > {last_index}')

    with open(outputfile,'r') as f:
        columns = f.readline().strip('\n').split('\t')

    return find_missing_indices, last_index, columns

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Curate marine data')
    parser.add_argument('config_file', type=str, help='path to the yaml configuration file')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='whether to parallelize on multiple CPUs', default=False)
    parser.add_argument('--cpu_max', type=int, help='maximum number of CPUs to be used', default=None)
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
             raise Exception("`clean.py` | `inputfile` contains dots ('.') outside of the file extension")
         config['outputfile_path'] = inputfile[0] + f'_processedby_marinedb'
         if len(inputfile) == 2:
             config['outputfile_path'] += f'.{inputfile[1]}'
         print(f"INFO | The processed file will be saved as {config['outputfile_path']}")
    if len(os.path.dirname(config['outputfile_path'])) == 0:
        config['outputfile_path'] = os.path.join(config['outputdir_path'], config['outputfile_path'])

    if ('processing' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'processing' section")

    outputdir = config['outputdir_path']
    outputfile = expanduser(config['outputfile_path'])

    isvariable = ('variables' in config.keys())
    if not isvariable:
        print('INFO | `variables` section not found: column filtering, type casting, and renaming will be skipped')

    # Verify that only supported functions are specified in the configuration files

    procfuncs = get_procfunc(config, 'processing')
    unsupported_funcs = set(procfuncs) - set(SUPPORTED_PROCFUNCTIONS)
    if len(unsupported_funcs) != 0:
        marineloc_funcs = unsupported_funcs.intersection(['createmask','createmarinefilter', 'filtermarinelocations', 'island', 'split_pandas_parquet'])
        unsupported_funcs = [f'`{func}`' for func in unsupported_funcs]
        error = f"`clean.py` | {','.join(list(unsupported_funcs))} are not supported functions."
        if len(marineloc_funcs) != 0:
            marineloc_funcs = [f'`{func}`' for func in marineloc_funcs]
            error += f" Use `marineloc` in place of {','.join(marineloc_funcs)}."
        raise ValueError(error)

    print()
    print(f"----- Start cleaning: {config['inputfile_path']} -----")
    print()

    start_cleaning = time.time()

#    # Set `stdnan` to False since all missing values in the database
#    # will be standardized before any processing steps are applied
#
#    config = re.sub(r"'stdnan': .*?(?=,|})", r"'stdnan': False", str(config))
#
#    # Set `drop_empty` to False to ensure that each batch has the same number of columns after processing
#
#    config = re.sub(r"'drop_empty': .*?(?=,|})", r"'drop_empty': False", config)

    # Parse 'True' and 'False' strings as Boolean True and False values

    config = re.sub(r"'True'", r"True", str(config))
    config = re.sub(r"'False'", r"False", config)

    # Convert the `config` string back into a dictionary

    config = config.encode('utf8').decode('unicode_escape')
    config = yaml.safe_load(config)

    # For all functions with an `outputdir` argument, substitute the argument
    # with the configuration file's inputdir_path or outputdir_path value

    config = overwrite_outputdir_stdnan_dropempty(config, config['inputdir_path'], config['outputdir_path'])

    ispreprocessing = False

    # If specified, apply the `marineloc` filter

    marineloc_filter = [(idx, filter) for idx,filter in enumerate(config['processing']) if 'marineloc' in str(filter)]

    if len(marineloc_filter) > 1:
        raise Exception(f"`clean.py` | `marineloc` should be specified only once in the `config` file")

    if len(marineloc_filter) == 1:

        marineloc_idx = marineloc_filter[0][0]
        marineloc_params = marineloc_filter[0][1]['tool'][0]['marineloc']
        marineloc_params['inputfile'] = config['inputfile_path']
        marineloc_params['indent'] = '   '
        if args.cpu_max is not None:
            marineloc_params['cpu'] = args.cpu_max

        if not ispreprocessing:
            print('Preprocessing')
            print('--------------')
            print()
            ispreprocessing = True
            start = time.time()

        if ('latkey' in marineloc_params) and ('lonkey' in marineloc_params):
            print(f"* {marineloc_params['latkey']}, {marineloc_params['lonkey']}")
        print('** marineloc')
        print()

        config['inputfile_path'] = marineloc.apply(**marineloc_params)

        print()

        del config['processing'][marineloc_idx]

        print(f'TIME: {round(time.time() - start,0)}s')
        print()


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
        default_createwormsfilters_params = getdefaultargs.apply(cwf.apply)
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
                    print()
                    createwormsfilters_params['wormscall'] = isinworms_createwormsfilters_params['wormscall']
                    createwormsfilters_args.append('wormscall')
            else:
                if 'wormscall' not in isinworms_createwormsfilters_args:
                    print(f'INFO | `wormscall` not found in `isinworms`, use value from `createwormsfilters`')
                    print()
                    isinworms_createwormsfilters_params['wormscall'] = createwormsfilters_params['wormscall']
                    isinworms_createwormsfilters_args.append('wormscall')

            ## Set unspecified parameters in `createwormsfilters` to their default values
            for arg, val in default_createwormsfilters_params.items():
                if arg not in createwormsfilters_args:
                    createwormsfilters_params[arg] = val

            ## Ensure that parameter values in `isinworms` do not conflict with those in `createwormsfilters`
            intersection_args = set(isinworms_createwormsfilters_params.keys()).intersection(set(createwormsfilters_params.keys()))
            exclude_args = set(['inputfile','identification_level','colname','store','store_parallel','max_attempt','verbose','indent'])
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

        else:

            createwormsfilters_params = isinworms_createwormsfilters_params

        createwormsfilters_params['inputfile'] = config['inputfile_path']
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

        start = time.time()

        worms_matchfilter, worms_acceptedfilter = cwf.apply(**createwormsfilters_params)

        ## Add the filters to `config`

        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['matchfilter'] = worms_matchfilter.copy(deep=True)
        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['acceptedfilter'] = worms_acceptedfilter.copy(deep=True)

        del worms_matchfilter
        del worms_acceptedfilter
        if is_createwormsfilters:
            del config['processing'][createwormsfilters_column_idx][createwormsfilters_column][createwormsfilters_idx]

        print(f'TIME: {round(time.time() - start,0)}s')
        print()

    # Read the gzip or uncompressed data file

    print('Processing')
    print('----------')
    print()

    parallel = args.parallel
    if not parallel:
        cpu_max = 1
    else:
        cpu_max = args.cpu_max

    parallel, cpu_main = set_cpu(config, parallel, cpu_main=None, cpu_max=cpu_max)
    if ('variables' in config.keys()):
        config['variables'].append('index_marinedb')

    if parallel:
        outputdir = os.path.join(outputdir,'marinedb_parallel')
        try:
            os.mkdir(outputdir)
        except FileExistsError:
            pass
    else:
        outputdir = ''

    nbatch = 0
    resume = False
    columns = None
    init_storage = True
    start = time.time()

    ## Resume processing

    if parallel:
#    outputfile_directory = os.path.dirname(outputfile)
        if len(os.listdir(outputdir)) != 0:
            print(f'* Restart processing from {outputdir}')
            resume = True
            indices2process, lastindex, nbatch, columns = resume_parallel_processing(outputdir)
    else:
        if os.path.isfile(outputfile):
            print(f'* Restart processing from {outputfile}')
            resume = True
            init_storage = False
            indices2process, lastindex, columns = resume_noparallel_processing(outputfile)

    open_file, decode_line = readfile.apply(config['inputfile_path'])
    skip = resume
    dtypes_mapping = get_dtypes(config)
    dtypes_mapping['index_marinedb'] = 'Int64'

    with open_file(config['inputfile_path'],'r') as data:

        header = decode_line(data.readline()).strip('\n').split('\t')
        header_length = len(header)

        batch = 0
        error = []
        data2clean = []
        init_process = True
        config_updated = None

        for idx, line in enumerate(data):

            if skip:
                if idx == lastindex:
                    skip = False
                if (not indices2process(idx)):
                    continue

            # Add observations

            obs = decode_line(line).strip('\n').split('\t')
            obs = [preprocessquotationmark.apply(value) for value in obs]

            if len(obs) == header_length:
                obs.insert(0, idx)
                data2clean.append(obs)
                batch += 1
            else:
                error.append(idx+2)
                print(f'SplittingError: splitting line n°{idx+2} yields a different number of fields ({len(obs)}) than the header ({header_length}).')
                print(f'line n°{idx+2} is skipped : {line}')
                print()

            if init_process and (batch == BATCH_SIZE):

                print(f'--- Processing | {batch} lines ---')
                print()
                print(f'INFO | Processing the initial batch separately to configure the environment')
                print()

                try:
                    print('SUCCESS loading with dtypes !') #debug
                    df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header, dtype=dtypes_mapping)
                except:
                    df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header)

                # Process data

                if parallel:
                    cpu_idx = ((nbatch + 1) if resume else nbatch)
                else:
                    cpu_idx = None

                config_updated, columns = process_one_dataframe(df2clean, config, config_updated, outputfile, outputdir=outputdir, columns=columns, cpu_idx=cpu_idx, verbose=True, init_process=init_process, init_storage=init_storage)

                init_process = False
                init_storage = False
                data2clean.clear()
                del df2clean
                batch = 0
                nbatch += 1

            if (not init_process) and (batch == cpu_main*BATCH_SIZE):

                print(f'--- Processing | {batch} lines on {cpu_main} CPUs ---')
                print()

                try:
                    print('SUCCESS loading with dtypes !') #debug
                    df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header, dtype=dtypes_mapping)
                except:
                    df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header)
                data2clean.clear()

                index_start = list(range(batch))[::BATCH_SIZE]
                index_end = list(range(BATCH_SIZE,batch))[::BATCH_SIZE] + [batch]
                index_slices = list(zip(index_start,index_end))
                assert len(index_slices) == cpu_main #debug

                if cpu_main != 1:

                    process = Parallel(n_jobs=cpu_main, backend='multiprocessing')
                    chunks = [df2clean.iloc[i:j,:].copy(deep=True) for i,j in index_slices]
                    del df2clean
#                    verbose_debug = [False]*cpu_main #debug
#                    verbose_debug[-1] = True #debug
                    params = {
                              'config': config,
                              'config_updated': config_updated,
                              'outputfile': outputfile,
                              'outputdir': outputdir,
                              'columns': columns,
                              'verbose': False,
                              'init_process': False,
                              'init_storage': True
                             }

                    _ = process(delayed(process_one_dataframe)(chunk, cpu_idx=(i+nbatch), **params) for i,chunk in enumerate(chunks)) #debug verbose
                    del chunks

                else:
                    _ = process_one_dataframe(df2clean, config, config_updated, outputfile, outputdir=outputdir, columns=columns, cpu_idx=None, verbose=True, init_process=False, init_storage=init_storage)
                    del df2clean

                batch = 0
                nbatch += cpu_main

    if batch != 0:

        cpu_main = math.ceil(batch/BATCH_SIZE)
        _, cpu_main = set_cpu(config, parallel, cpu_main=cpu_main, cpu_max=cpu_max)

        try:
            print('SUCCESS loading with dtypes !') #debug
            df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header, dtype=dtypes_mapping)
        except:
            df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header)

        index_start = list(range(batch))[::BATCH_SIZE]
        index_end = list(range(BATCH_SIZE,batch))[::BATCH_SIZE] + [batch]
        index_slices = list(zip(index_start,index_end))
        assert len(index_slices) == cpu_main
        print('nbatch',nbatch) #debug
        if parallel:
            cpu_idx = ((nbatch + 1) if (init_process and resume) else nbatch)
        else:
            cpu_idx = None
        print('cpu_idx:', cpu_idx)
        # Process data

        print(f'--- Processing | {batch} lines on {cpu_main} CPUs ---')
        print()

        if cpu_main != 1:

            process = Parallel(n_jobs=cpu_main, backend='multiprocessing')
            chunks = [df2clean.iloc[i:j,:].copy(deep=True) for i,j in index_slices]
            del df2clean

            params = {
                      'config': config,
                      'config_updated': config_updated,
                      'outputfile': outputfile,
                      'outputdir': outputdir,
                      'columns': columns,
                      'verbose': False,
                      'init_process': False,
                      'init_storage': True
                     }

            _ = process(delayed(process_one_dataframe)(chunk, cpu_idx=(i+nbatch), **params) for i,chunk in enumerate(chunks))
            del chunks

        else:
            _ = process_one_dataframe(df2clean, config, config_updated, outputfile, outputdir=outputdir, columns=columns, cpu_idx=cpu_idx, verbose=True, init_process=init_process, init_storage=init_storage)
            del df2clean

    print(f'TIME: {round(time.time() - start,0)}s')
    print()

    if parallel:

#        print('Finalization')
#        print('------------')
#        print()
        print(f'* Consolidate temporary files')
        print(f'  Storing in {outputfile}')

        # Concatenate

        files = sorted(glob.glob(os.path.join(outputdir, '*')))
        firstlast_pairs = [read_firstlastindex(f) for f in files]
        files_order = sorted(range(len(files)), key=lambda x: firstlast_pairs[x][0])
#        print('files:', files)
#        print('files_order:', files_order)

        if os.path.isfile(outputfile):
            print(f'INFO | {outputfile} already exists and will be modified')
            init = False
            with open(outputfile,'r') as f:
                header = f.readline().strip('\n').split('\t')
        else:
            init = True

        with open(outputfile, 'a+') as output:
            for i in files_order:
                file = files[i]
                print(f'  >>> {file}')
                with open(file, 'r') as input:
                    lines = input.readlines()
                    if init:
                        header = lines[0].strip('\n').split('\t')
                        init = False
                    else:
                        header_file = lines[0].strip('\n').split('\t')
                        diff = list(set(header).symmetric_difference(header_file))
                        if len(diff) != 0:
                            raise Exception(f'`clean.py` | Header mismatch detected either between temporary files or between a temporary file and the existing output file: {diff}')

                        lines = lines[1:]

                        if header_file != header:
                            sort_header_file = [header.index(col) for col in header_file]
                            lines = [line.split('\t') for line in lines]
                            lines = ['\t'.join([v for _,v in sorted(zip(sort_header_file, line), key=lambda pair: pair[0])]) for line in lines]

                    output.writelines(lines)
    print()

    print('Post-processing')
    print('---------------')
    print()

    start = time.time()

    if ('postprocessing' in config.keys()) and (len(config['postprocessing']) != 0):

        postprocfuncs = get_procfunc(config, 'postprocessing')
        unsupported_funcs = set(postprocfuncs) - set(SUPPORTED_POSTPROCFUNCTIONS)
        if len(unsupported_funcs) != 0:
            raise ValueError(f"`clean.py` | {','.join(list(unsupported_funcs))} are not supported functions.")

        for procstep in config['postprocessing']:

            colname = list(procstep.keys())[0]

            for proc in procstep[colname]:

                if isinstance(proc, dict):
                    proc_name = list(proc.keys())[0]
                    proc_params = proc[proc_name]
                else:
                    proc_name = proc
                    proc_params = {}

                proc_params['verbose'] = True
                proc_params['indent'] = '   '
                proc_params['inputfile'] = config['outputfile_path']

                if proc_name == 'taxasubset':

                    if is_isinworms:
                        proc_params['speciesidkey'] = 'valid_AphiaID'
                        print(f'* valid_AphiaID')
                    else:
                        columns = [keycol for keycol in proc_params.keys() if 'key' in keycol]
                        if len(columns) == 0:
                            raise Exception(f'`taxasubset.py` | Either the column containing species identifiers or the columns specifying taxonomic classification must be provided')
                        columns = ', '.join(columns)
                        print(f'* {columns}')
                    print('** taxasubset')
                    print()

                    _, outputfile = taxasubset.apply(**proc_params)

                else:
                    raise Exception('`clean.py` | [DEV] An exception should have been raised before this line of code')

                config['outputfile_path'] = outputfile
                print()

    else:
        print("INFO | No post-processing step specified")

    print(f'TIME: {round(time.time() - start,0)}s')
    print()

    print(f"----- End cleaning {config['inputfile_path']} -----")
    print()

    print(f'TIME: {round(time.time() - start_cleaning,0)}s')
    print()
    if len(error) != 0:
        print(indent + f'ERROR:')
        print(indent + f'SplittingError: {len(error)} observations produced a different number of fields upon splitting compared to the header, and were consequently ignored.')
        print(f'Refer to lines: {error}')


    # Clean

    if parallel:

        print('* Delete temporary files')

        for file in files:
            print(f'  >>> {file}')
            os.remove(file)

        if len(os.listdir(outputdir)) == 0:
            os.rmdir(outputdir)

    print()
