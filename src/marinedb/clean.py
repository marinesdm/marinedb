#!/usr/bin/python
# coding: utf-8

# External imports

import traceback #debug

import os
import re
import json
import gzip
import yaml
import time
import copy
import math
import glob
import shutil
import inspect
import argparse
import pandas as pd
from copy import deepcopy
from itertools import groupby
from operator import itemgetter
from joblib import Parallel, delayed

# Internal import

import marinedb.tools as tools
from marinedb.tools import format
from marinedb.tools import getcolumnname
from marinedb.tools import convertdatetype
from marinedb.tools.marineloc import marineloc
from marinedb.tools.taxonomic import taxasubset
from marinedb.tools.taxonomic import resolvetaxamatch
from marinedb.tools.taxonomic import createwormsfilters as cwf

from marinedb.utils import readfile
from marinedb.utils import tqdmjoblib
from marinedb.utils import resolvepath
from marinedb.utils import convertbytes
from marinedb.utils import writedataframe
from marinedb.utils import standardizenan
from marinedb.utils import getdefaultargs
from marinedb.utils.printverbose import printv
from marinedb.utils import getdefaultoutputfile
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
                           'format',
                           'createwormsfilters',
                           'isinworms',
                           'mapbasisofrecord',
                           'basisofrecordisin',
                           'contains',
                           'doesnotcontain',
                           'dropvalues',
                           'isboundedby',
                           'isin',
                           'isna',
                           'notisin',
                           'islatloninvalid',
                           'islatlonzero',
                           'doeslateqlon',
                           'belowminlatlonprecision',
                           'iszero',
                           'lettersonly',
                           'taxasubset',
                           'parsedate',
                           'processdateinterval',
                           'splitdate',
                           'temporal',
                           'isdateinvalid',
                           'isdateunlikely'
                           ]

SUPPORTED_POSTPROCFUNCTIONS = [
                               'taxasubset',
                               'resolvetaxamatch'
                              ]

BATCH_SIZE = 100000

class MyDumper(yaml.Dumper):

    def increase_indent(self, flow=False, indentless=False):
        return super(MyDumper, self).increase_indent(flow, False)

class SplittingError(Exception):

    def __init__(self, line_number, field_count, header_count, line):
        message = (
            f"Line {line_number} has {field_count} fields but the header has "
            f"{header_count}.\nLine: {line}"
        )
        super().__init__(message)

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

def get_config_schema(config, key):
    schema = []
    for idx_step in range(len(config[key])):
        step_name = get_key(config[key][idx_step])
        proc_names = get_keys(config[key][idx_step][step_name])
        combination = list(zip([idx_step]*len(proc_names), [step_name]*len(proc_names), range(len(proc_names)), proc_names))
        schema += combination
    return schema

def get_dtypes(config, key_type):

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
                if key_type == 'old':
                    dtypes_mapping[colname_old] = coltype
                else:
                    dtypes_mapping[colname_new] = coltype

    return dtypes_mapping

def get_column_mapping(config):

    colnames_mapping = {}

    if 'variables' in config:

        config_variables = config['variables']

        for coldict in config_variables:

            if isinstance(coldict, str):
                colnames_mapping[coldict] = coldict

            else:
                colname_old = get_key(coldict)
                colname_new = get_key(coldict[colname_old])
                colnames_mapping[colname_old] = colname_new

    return colnames_mapping

def get_procfunc(config, key):

    config_proc = config[key]
    if (config_proc is None) or (len(config_proc) == 0):
        return []

    procfuncs = set()
    for i, procstep in enumerate(config_proc):
        colname = get_key(procstep)
        for j, func in enumerate(procstep[colname]):
            procfuncs.update([get_key(func)])

    return list(procfuncs)

def order_postprocfunc(config):

    config_postproc = config['postprocessing']

    # Split combined post-processing steps into separate steps
    config_postproc_normalized = []
    funcs = []
    for i, procstep in enumerate(config_postproc):
        colname = get_key(procstep)
        for func in procstep[colname]:
            config_postproc_normalized.append({colname : [func]})
            funcs.append(func)

    # Move 'resolvetaxamatch' to the beginning if present
    if 'resolvetaxamatch' in funcs:
        resolvetaxamatch_idx = funcs.index('resolvetaxamatch')
        config_postproc_normalized.insert(0,config_postproc_normalized.pop(resolvetaxamatch_idx))

    config['postprocessing'] = config_postproc_normalized

    return config

# Update the configuration file

def overwrite_outputdir_stdnan_dropempty_cleanup(config, inputfile, inputdir, outputdir, cleanup):

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
            funcargs_signature = list(inspect.signature(eval(f'tools.{funcname}.apply')).parameters.keys())
            funcargs_provided = config[proccat][i][colname][j][funcname].keys()

            # For all functions with an `outputdir` argument, substitute the argument
            # with the configuration file's `inputdir_path` or `outputdir_path value`

            if 'outputdir' in funcargs_signature:
                if funcname in ['format', 'createwormsfilters']:
                    print(f"INFO | '{colname}': override the `outputdir` argument in `{funcname}` with the `inputdir_path` value from the configuration file")
                    config[proccat][i][colname][j][funcname]['outputdir'] = inputdir
                    isprint = True
                elif funcname == 'marineloc':
                    if ('outputdir' not in funcargs_provided):
                        print(f"INFO | '{colname}': override the `outputdir` argument in `{funcname}` with the `inputdir_path` value from the configuration file")
                        config[proccat][i][colname][j][funcname]['outputdir'] = inputdir
                        isprint = True
                else:
                    print(f"INFO | '{colname}': override the `outputdir` argument in `{funcname}` with the `outputdir_path` value from the configuration file")
                    config[proccat][i][colname][j][funcname]['outputdir'] = outputdir
                    isprint = True
            if 'outputdir_createwormsfilters' in funcargs_signature:
                print(f"INFO | '{colname}': override the `outputdir_createwormsfilters` argument in `{funcname}` with the `inputdir_path` value from the configuration file")
                config[proccat][i][colname][j][funcname]['outputdir_createwormsfilters'] = inputdir
                isprint = True
            if 'outputdir_isinworms' in funcargs_signature:
                print(f"INFO | '{colname}': override the `outputdir_isinworms` argument in `{funcname}` with the `outputdir_path` value from the configuration file")
                config[proccat][i][colname][j][funcname]['outputdir_isinworms'] = outputdir
                isprint = True

            if funcname == 'marineloc':
                if 'splitdir' not in funcargs_provided:
                    config[proccat][i][colname][j][funcname]['splitdir'] = os.path.join(inputdir, 'marineloc', 'split')

#                default_outputfile = getdefaultoutputfile.apply(inputfile, 'marineloc', outputdir=outputdir, add_processedby=False, verbose=False)
#                if ('outputfile' not in funcargs_provided):
#                    config[proccat][i][colname][j][funcname]['outputfile'] = default_outputfile
#                else:
#                    provided_outputfile = config[proccat][i][colname][j][funcname]['outputfile']
#                    if (provided_outputfile is None) or (len(provided_outputfile) == 0):
#                        config[proccat][i][colname][j][funcname]['outputfile'] = default_outputfile
#                    else:
#                        config[proccat][i][colname][j][funcname]['outputfile'] = os.path.join(outputdir,os.path.basename(provided_outputfile))

            # For all functions with a `stdnan` argument, set `stdnan` to False
            # All missing values are normalized upstream before processing
            # Exception:
            # - `isinworms.py`, which applies a different `additional_policy`
            # - `isnan.py` with a different `additional_policy`

            overwrite_stdnan = False

            if ('stdnan' in funcargs_signature) and (funcname not in ['isinworms','isna']):
                overwrite_stdnan = True

            if (funcname == 'isna'):
                overwrite_stdnan = True
                if ('stdnan_additional_policy' in funcargs_provided):
                    stdnan_additional_policy = config[proccat][i][colname][j][funcname]['stdnan_additional_policy']
                    if (len(stdnan_additional_policy) != 0) and (stdnan_additional_policy != 'contains_letters_or_digits'):
                        overwrite_stdnan = False

            if overwrite_stdnan:
                print(f"INFO | '{colname}': set `stdnan` argument in `{funcname}` to False")
                config[proccat][i][colname][j][funcname]['stdnan'] = False
                isprint = True

            # For all functions with an `drop_empty` argument, set `drop_empty` to False
            # to ensure that each batch has the same number of columns after processing

            if 'drop_empty' in funcargs_signature:
                print(f"INFO | '{colname}': set `drop_empty` argument in `{funcname}` to False")
                config[proccat][i][colname][j][funcname]['drop_empty'] = False
                isprint = True

            # For all functions with a `cleanup` argument, replace it with the value provided when calling the script

            if 'cleanup' in funcargs_signature:
                print(f"INFO | '{colname}': set `cleanup` argument in `{funcname}` to {cleanup}")
                config[proccat][i][colname][j][funcname]['cleanup'] = cleanup
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

def update_config_variables(df, config, addcolumns=None):

    config_variables_updated = {}

    config_variables = []
    base_colmapping = {}

    df = df.convert_dtypes()

    for idx, coldict in enumerate(config['variables']):

        colname_old = get_key(coldict)

        default_dtype = 'string'
        try:
            default_dtype = str(df[colname_old].dtypes)
            default_dtype = (default_dtype if (default_dtype != 'object') else 'string')
        except KeyError:
            pass

        keep = {colname_old: {colname_old: default_dtype}}

        # Retrieve column names post-processing

        add = None
        _, colname_proc, _ = getcolumnname.apply(df, colname_old, '', inplace=True, minimize_columns=False)
        isprocessedby = ('processedby' in colname_proc)

        if isprocessedby:

            # The column has been modified, with modifications
            # either applied in place or stored in a new column

            default_dtype = str(df[colname_proc].dtype)
            default_dtype = (default_dtype if (default_dtype != 'object') else 'string')

            add = {colname_proc: {colname_proc: default_dtype}}

        if isinstance(coldict, dict):

            colname_new = get_key(coldict[colname_old])
            keep = {colname_old: {colname_new: default_dtype}}

            if isprocessedby:

                # Map the derived column to its intended name after renaming

                colname_proc_new = re.sub(colname_old, colname_new, colname_proc)
                add = {colname_proc: {colname_proc_new: default_dtype}}

            if isinstance(coldict[colname_old], dict):

                colname_dtype = coldict[colname_old][colname_new]
                keep = {colname_old: {colname_new: colname_dtype}}

                if isprocessedby:

                    # Duplicate dtype conversion settings to the derived column

                    add = {colname_proc: {colname_proc_new: colname_dtype}}

        if (colname_old in list(df.columns)):

            # The column has not been modified in place during processing:
            # Update the `variables` section in `config` to include
            # the settings for the original column

            config_variables.append(keep)

        if add is not None:

            # Update the `variables` section in `config` to include
            # the settings for the post-processing columns

            config_variables.append(add)

        if (colname_old != 'issue') and isinstance(coldict, dict):
            base_colmapping.update({colname_old: colname_new})

    if addcolumns is not None:

        # Add the columns generated during processing
        # to the list of columns to keep

        selected_columns = get_keys(config_variables)
        addcolumns = list(set(addcolumns) - set(selected_columns))

        colnames_pattern = sorted(base_colmapping.items(), key=lambda x: len(x[0]), reverse=True)
        colnames_pattern = "|".join(re.escape(colname_old) for colname_old, _ in colnames_pattern)

        pattern = re.compile(
            rf'^(?P<prefix>flag_)?'
            rf'(?P<col1>{colnames_pattern})'
            rf'(?:_(?P<col2>{colnames_pattern}))?'
            rf'(?:_(?P<col3>{colnames_pattern}))?'
            rf'(?=_|$)'
        )

        for col in addcolumns:

            dtype = str(df[col].dtype)
            dtype = (dtype if (dtype != 'object') else 'string')
            if col[:5] == 'flag_':
                dtype = 'boolean'
            add = {col:{col:dtype}}

            m = pattern.match(col)
            if m:
                prefix = m.group("prefix") or ""
                cols = [m.group("col1"), m.group("col2"), m.group("col3")]
                cols = [base_colmapping[c] for c in cols if c is not None]
                add = {col:{prefix + "_".join(cols) + col[m.end():]:dtype}}

            config_variables.append(add)

    config_variables_updated['variables'] = config_variables

    return config_variables_updated

def update_config_postprocessing(config, inputfile, isvariable, is_isinworms, is_isinworms_verbatim=False, dtypes=None):

    # Update to reflect the final column names after processing and renaming
    # original column -> renamed column -> processed column

    with open(inputfile,'rt') as f:
        header = f.readline().strip('\n').split('\t')
    processed_colnames = pd.DataFrame([], columns=header)

    if isvariable:

        colnames_mapping = get_column_mapping(config)
        mapping_values = set(colnames_mapping.values())
        mapping_keys = set(colnames_mapping.keys())

    for idx_step, procstep in enumerate(config['postprocessing']):

        step_name = list(procstep.keys())[0]

        for idx_proc, proc in enumerate(procstep[step_name]):

            if isinstance(proc, dict):
                proc_name = list(proc.keys())[0]
            else:
                proc_name = proc
                config['postprocessing'][idx_step][step_name][idx_proc][proc_name] = {}

            config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['verbose'] = True
            config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['indent'] = '   '
            config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['inputfile'] = inputfile

            # `resolvetaxamatch`

            if proc_name == 'resolvetaxamatch':

                ## `rank_mapping`

                rank_mapping = config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['isinworms_params']['rank_mapping'].items()

                for rank, original_colname in rank_mapping:

                    if isvariable:
                        if (original_colname not in mapping_keys) and (original_colname not in mapping_values):
                            raise ValueError(f"`resolvetaxamatch.py` | '{original_colname}' column is not defined in the `variables` section and was therefore dropped. Please add it to the `variables` section.")
                        if (original_colname in mapping_keys):
                            renamed_colname = colnames_mapping[original_colname]
                        else:
                            renamed_colname = original_colname
                    else:
                        renamed_colname = original_colname

                    _, processed_colname, _ = getcolumnname.apply(processed_colnames, renamed_colname, '', inplace=True)
                    if processed_colname not in header:
                        raise ValueError(f"`resolvetaxamatch.py` | Column '{processed_colname}' specified in `rank_mapping` (`isinworms_params`) was not found in '{os.path.basename(inputfile)}'")

                    config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['isinworms_params']['rank_mapping'][rank] = processed_colname

                ## `verbatimcolumn`

                if is_isinworms_verbatim:

                    verbatim_columns = config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['isinworms_params']['verbatimcolumn']

                    for idx, original_colname in enumerate(verbatim_columns):

                        if isvariable:
                            if (original_colname not in mapping_keys) and (original_colname not in mapping_values):
                                raise ValueError(f"`resolvetaxamatch.py` | '{original_colname}' column is not defined in the `variables` section and was therefore dropped. Please add it to the `variables` section.")
                            if (original_colname in mapping_keys):
                                renamed_colname = colnames_mapping[original_colname]
                            else:
                                renamed_colname = original_colname
                        else:
                            renamed_colname = original_colname

                        _, processed_colname, _ = getcolumnname.apply(processed_colnames, renamed_colname, '', inplace=True)
                        if processed_colname not in header:
                            raise ValueError(f"`resolvetaxamatch.py` | Column '{processed_colname}' specified in `verbatimcolumn` (`isinworms_params`) was not found in '{os.path.basename(inputfile)}'")

                        config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['isinworms_params']['verbatimcolumn'][idx] = processed_colname

            # `taxasubset`

            if proc_name == 'taxasubset':

                if is_isinworms:

                    original_colname = 'AphiaID'

                    if isvariable:
                        if original_colname in mapping_keys:
                            renamed_colname = colnames_mapping[original_colname]
                        else:
                            renamed_colname = original_colname
                    else:
                        renamed_colname = original_colname

                    renamed_colname = renamed_colname + '_generatedby_isinworms'
                    _, processed_colname, _ = getcolumnname.apply(processed_colnames, renamed_colname, '', inplace=True)

                    config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['speciesidkey'] = processed_colname

                else:

                    params = config['postprocessing'][idx_step][step_name][idx_proc][proc_name]
                    ranks = [keycol for keycol in params.keys() if 'key' in keycol]

                    if len(ranks) == 0:
                        raise Exception(f'`taxasubset.py` | Either the column containing species identifiers or the columns specifying taxonomic classification must be provided')

                    for rank in ranks:

                        if isvariable:
                            if (params[rank] not in mapping_keys) and (params[rank] not in mapping_values):
                                raise ValueError(f"`taxasubset.py` | '{proc_params[rank]}' column is not defined in the `variables` section and was therefore dropped. Please add it to the `variables` section.")
                            if (params[rank] in mapping_keys):
                                renamed_colname = colnames_mapping[params[rank]]
                            else:
                                renamed_colname = params[rank]
                        else:
                            renamed_colname = params[rank]

                        _, processed_colname, _ = getcolumnname.apply(processed_colnames, renamed_colname, '', inplace=True)
                        if processed_colname not in header:
                            raise ValueError(f"`taxasubset.py` | Column '{processed_colname}' specified for `{rank}` was not found in '{os.path.basename(inputfile)}'")

                        config['postprocessing'][idx_step][step_name][idx_proc][proc_name][rank] = processed_colname

                if dtypes is not None:
                     config['postprocessing'][idx_step][step_name][idx_proc][proc_name]['dtypesfile'] = dtypes

    return config

# Apply configuration settings

def dtypeconversion(df, config, verbose=True, indent=''):

    isprint = False
    config_variables = config['variables']

    for column in config_variables:

        colnames = []

        colname_old = get_key(column)
        colnames.append(colname_old)

        if isinstance(column, dict):
            if isinstance(column[colname_old], dict):
                colname_new = get_key(column[colname_old])
                colnames.append(colname_new)
                coltype = column[colname_old][colname_new]
            else:
                coltype = ''
        else:
            coltype = ''

        colnames = list(set(colnames))
        known_key = (coltype in TYPE.keys())
        known_value = (coltype in TYPE.values())

        for colname in colnames:

            if colname not in df.keys():
                continue

            if (coltype != ''):

                if (known_key or known_value):

                    try:

                        if 'datetime' in coltype:
                            printv(f"WARNING | When converting '{colname}' to datetime, missing days and months will default to the 1st and January", verbose=verbose, indent=indent)
                            isprint = True
                            df = convertdatetype.apply(df, datekey=colname, format='ISO8601')

                        else:

                            if known_key:
                                coltype = TYPE[coltype]

                            if coltype == 'Int64':
                                df[colname] = df[colname].astype('Float64').astype(coltype)

                            elif coltype == 'boolean':
                                try:
                                    df[colname] = df[colname].astype(coltype)
                                except (TypeError, ValueError):
                                    df[colname] = df[colname].astype('string').str.lower().map({'true': True, 'false': False}).astype('boolean')

                            else:
                                df[colname] = df[colname].astype(coltype)

                    except (TypeError, ValueError) as err:

                        printv(f"WARNING | Failed to convert '{colname}' to `{coltype}`", verbose=verbose, indent=indent)
                        coltype = ''
                        isprint = True
                        if verbose:
                            print('Exception details') # debug
                            print('-----------------')
                            traceback.print_exc() # debug
                            print()

                else:

                    printv(f"INFO | '{colname}': `{coltype}` is not a recognized type", verbose=verbose, indent=indent)
                    isprint = True
                    try:
                        df[colname] = df[colname].astype(coltype)
                    except (TypeError, ValueError):
                        printv(f"WARNING | Failed to convert '{colname}' to `{coltype}`", verbose=verbose, indent=indent)
                        isprint = True
                        coltype = ''
                        if verbose:
                            print('Exception details') # debug
                            print('-----------------')
                            traceback.print_exc() # debug
                            print()

            if (coltype == ''):

                printv(f"INFO | Convert '{colname}' to `string` by default", verbose=verbose, indent=indent)
                isprint = True
                try:
                    df[colname] = df[colname].astype('string')
                except KeyError:
                    printv(f"WARNING | Failed to convert '{colname}' to `string`", verbose=verbose, indent=indent)
                    if verbose:
                        print('Exception details') # debug
                        print('-----------------')
                        traceback.print_exc() # debug
                        print()

    if isprint:
        printv('', verbose=verbose)

    return df

def curate_data(df, config, config_variables_updated, isvariable, init=False, verbose=True, indent='', partition=None):

    # Standardize the missing values

    printv(f'* dataframe', verbose=verbose, indent=indent)
    printv(f'** standardizenan', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    df = standardizenan.apply(df, key=None, additional_policy='contains_letters_or_digits')

    columns_before = set(df.columns)

    # Convert dtypes, if possible

    if isvariable:

        dtypes_mapping = get_dtypes(config, key_type='old')

        for key,value in dtypes_mapping.items():
            try:
                if value == 'Int64':
                    df[key] = df[key].astype('Float64').astype('Int64')
                else:
                    df[key] = df[key].astype(value)
            except (TypeError, ValueError, KeyError):
                pass

    # Perform multiple processing steps to curate the dataset

    df = tools.apply(df, config['processing'], verbose=verbose, indent=indent, partition=partition, outputdir_marinedb=config['outputdir_path'])

    # Update `variables` section in `config`

    if init:

        columns_after = set(df.columns)
        generated_columns = list(columns_after - columns_before)
        config_variables_updated = update_config_variables(df, config, addcolumns=generated_columns)

    if isvariable:

        # Select the columns

        printv(f'* dataframe', verbose=verbose, indent=indent)
        printv(f'** columnselection', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        colnames_mapping = get_column_mapping(config_variables_updated)
        df = df[list(colnames_mapping.keys())]

        # Apply dtype conversion

        printv(f'* dataframe', verbose=verbose, indent=indent)
        printv(f'** dtypeconversion', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        df = dtypeconversion(df, config_variables_updated, verbose=verbose, indent=indent + '   ')

        # Rename the columns

        printv(f'* dataframe', verbose=verbose, indent=indent)
        printv(f'** columnrenaming', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        df = df.rename(columns=colnames_mapping)

    return df, config, config_variables_updated

def process_one_dataframe(df, config, config_variables_updated, isvariable, outputfile, outputdir='', columns=None, cpu_idx=None, init_process=False, init_storage=False, verbose=True, indent=''):

    if cpu_idx is not None:

        temp = os.path.basename(outputfile).split('.')
        outputfile = temp[0] + '_temp%05d' % cpu_idx
        if len(temp) == 2:
            outputfile += f'.{temp[1]}'
        outputfile = os.path.join(outputdir,outputfile)

        init_storage = True
        if cpu_idx != 0:
            verbose = False

    nlines = len(df)

    start = time.time()

    params = {
              'init': init_process,
              'verbose': verbose,
              'indent': indent,
              'partition': cpu_idx
             }

    df, config, config_variables_updated = curate_data(df, config, config_variables_updated, isvariable, **params)

    # Store data

    if columns is None:
        columns = list(df.columns)

    if len(df) != 0:
        writedataframe.to_txt(df[columns], outputfile, init=init_storage, verbose=False, indent=indent)

    end = time.time()

    if cpu_idx is not None:
        printv(f'CPU n°{cpu_idx}: {len(df)} lines remaining | TIME : {round(end-start)}s', verbose=True, indent=indent)
        if len(df) != 0:
            printv(f'>>> save to {outputfile}', verbose=True, indent=indent)
        printv('', verbose=True)
    else:
        printv(f'>>>>>> {nlines} lines done | TIME : {round(end-start)}s', verbose=verbose)
        printv('', verbose=verbose)

    if cpu_idx is not None: # NEW
        span = round((end - start))
        outputdir = os.path.join(outputdir, 'time')
        if not os.path.isdir(outputdir):
            os.makedirs(outputdir)
        timefilepath = os.path.join(outputdir, f'time_' + 'temp%05d' % cpu_idx)
        with open(timefilepath, 'w', encoding='utf-8') as f:
            f.write('\t'.join([str(cpu_idx), str(span), str(nlines), str(len(df))]) + '\n')

    return config_variables_updated, columns

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

def resume_parallel_processing(outputdir, configfile, config, verbose=True, indent=''):

    fileslist = [entry.path for entry in os.scandir(outputdir) if entry.is_file()]

    filesnumber = pd.Series(fileslist).str.findall(r'(?<=_temp)[0-9]+')
    if any(filesnumber.str.len() > 1):
        bad_filenames = pd.Series(fileslist)[filesnumber.str.len() > 1].tolist()
        raise Exception(f"`clean.py` | Unsupported file names: {','.join(bad_filenames)}. The file name must contain exactly one number.")
    filesnumber = sorted(filesnumber.str[0].tolist())

    firstlast_pairs = [read_firstlastindex(f) for f in fileslist]
    firstlast_pairs = sorted(firstlast_pairs, key=lambda x: x[0])
    Npairs = len(firstlast_pairs)
    nonconsecutive_indices = [(firstlast_pairs[i][1], firstlast_pairs[i+1][0]) for i in range(Npairs - 1) if (firstlast_pairs[i][1] != (firstlast_pairs[i+1][0] - 1))]

    find_missing_indices = []
    if firstlast_pairs[0][0] != 0:
        find_missing_indices += [f'(x < {firstlast_pairs[0][0]})']
    if len(nonconsecutive_indices) != 0:
        find_missing_indices += [' or '.join(f'((x > {i}) and (x < {j}))' for i,j in nonconsecutive_indices)]
    find_missing_indices += [f'(x > {firstlast_pairs[-1][1]})']
    find_missing_indices = ' or '.join(find_missing_indices)
    find_missing_indices = eval('lambda x: ' + find_missing_indices)

    last_index = firstlast_pairs[-1][1]
    last_file = int(filesnumber[-1])
    with open(fileslist[0],'r') as f:
        columns = f.readline().strip('\n').split('\t')

    configfile = os.path.basename(configfile).split('.')[0]
    configfile_updated = os.path.join(config['outputdir_path'], f'{configfile}_updated.yaml')
    if os.path.isfile(configfile_updated):
        with open(configfile_updated,'r') as f:
            config_variables_updated = yaml.safe_load(f)
    else:
        config_variables_updated = None
        configfile_updated =  None

    return find_missing_indices, last_index, last_file, columns, config_variables_updated, configfile_updated

def resume_noparallel_processing(outputfile, configfile, config, verbose=True, indent=''):

    _, last_index = read_firstlastindex(outputfile)
    find_missing_indices = eval(f'lambda x: x > {last_index}')

    with open(outputfile,'r') as f:
        columns = f.readline().strip('\n').split('\t')

    configfile = os.path.basename(configfile).split('.')[0]
    configfile_updated = os.path.join(config['outputdir_path'], f'{configfile}_updated.yaml')
    if os.path.isfile(configfile_updated):
        with open(configfile_updated,'r') as f:
            config_variables_updated = yaml.safe_load(f)
    else:
        config_variables_updated = None
        configfile_updated =  None

    return find_missing_indices, last_index, columns, config_variables_updated, configfile_updated

def assemble_outputfile(outputdir, outputfile, columns, cleanup=True):

    assert os.path.isdir(outputdir)

    print(f'* Consolidate marinedb output files')
    print(f'  Storing in {outputfile}')
    print()

    # Concatenate

    files = [entry.path for entry in os.scandir(outputdir) if entry.is_file()]
    firstlast_pairs = [read_firstlastindex(f) for f in files]
    files_order = sorted(range(len(files)), key=lambda x: firstlast_pairs[x][0])

    if os.path.isfile(outputfile):
        print(f'  INFO | {outputfile} already exists and will be modified')
        init = False
        with open(outputfile,'r') as f:
            header = f.readline().strip('\n').split('\t')
    else:
        init = True

    if (len(files) == 0) and init:
        with open(outputfile, 'a+') as output:
            output.write('\t'.join(columns))

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

    if cleanup:

        print()
        print('  * Cleaning up intermediate files')
        print()

        for file in files:
            print(f'    >>> {file}')
            os.remove(file)

        if len(os.listdir(outputdir)) == 0:
            print(f'    >>> {outputdir}')
            os.rmdir(outputdir)

    return None

def concat_times(inputdir, outputdir, cleanup=True):

    outputfile = os.path.join(outputdir, 'marinedb_times.txt')

    print(f'* Consolidate marinedb processing time files')

    if not os.path.isdir(inputdir):
        print(f'  Directory "{inputdir}" not found')
        print()
        return None

    files = [os.path.join(inputdir,file) for file in os.listdir(inputdir) if 'time_' in file]

    if len(files) == 0:
        print(f'  No files found in {inputdir}')
        print()
        return None
    else:
        print(f'  Storing in {outputfile}')
        print()

    colnames = ['batch','time','n_lines_before','n_lines_after']
    init=True

    for filepath in files:
        content = pd.read_csv(filepath, sep='\t', names=colnames)
        if init:
            times = content[colnames].copy()
            init = False
        else:
            times = pd.concat([times[colnames],content[colnames]], ignore_index=True, axis=0)

    times.to_csv(outputfile, sep='\t', index=False)

    if cleanup:

        print('  * Cleaning up intermediate files')
        print()

        for file in files:
            print(f'    >>> {file}')
            os.remove(file)

        if len(os.listdir(inputdir)) == 0:
            print(f'    >>> {inputdir}')
            os.rmdir(inputdir)

        print()

    return None

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Curate marine data')
    parser.add_argument('config_file', type=str, help='path to the yaml configuration file')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='whether to parallelize on multiple CPUs', default=False)
    parser.add_argument('--cpu-max', type=int, help='maximum number of CPUs to be used', default=None)
    parser.add_argument('--cleanup', action=argparse.BooleanOptionalAction, help='delete all intermediate files generated during processing', default=True)
    args = parser.parse_args()

    cleanup = args.cleanup

    with open(args.config_file,'r') as f:
        config = yaml.safe_load(f)

    #############################################
    ############### Configuration ###############
    #############################################

    if ('data' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'data' section")

    config = config['data']

    # Input file

    if ('inputfile_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'inputfile_path' section")
    config['inputfile_path'] = resolvepath.apply(config['inputfile_path'])

    if (not os.path.isfile(config['inputfile_path'])):
        raise FileNotFoundError(f"`clean.py` | No such file: '{config['inputfile_path']}'")

    # Input directory

    if ('inputdir_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'inputdir_path' section")
    config['inputdir_path'] = resolvepath.apply(config['inputdir_path'])

    if (not os.path.isdir(config['inputdir_path'])):
#        raise FileNotFoundError(f"`clean.py` | No such directory: '{config['inputdir_path']}'")
        print(f"INFO | Input directory '{config['inputdir_path']}' does not exist")
        os.mkdir(config['inputdir_path'])

    initial_files = os.listdir(config['inputdir_path'])

    # Output directory

    if ('outputdir_path' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'outputdir_path' section")
    config['outputdir_path'] = resolvepath.apply(config['outputdir_path'])

    if (not os.path.isdir(config['outputdir_path'])):
        print(f"INFO | Output directory '{config['outputdir_path']}' does not exist")
        try:
            os.mkdir(config['outputdir_path'])
        except FileExistsError:
            pass

    # Output file

    outputfile_path = config.get('outputfile_path')

    is_outputfile = (outputfile_path is not None) and (len(outputfile_path) > 0)
    outputfile_equals_inputfile = is_outputfile and (os.path.basename(config['inputfile_path']) == os.path.basename(outputfile_path))

    if (not is_outputfile) or (len(outputfile_path) == 0) or outputfile_equals_inputfile:

         filename = os.path.basename(config['inputfile_path'])
         name, ext = os.path.splitext(filename)

         if '.' in name:
             raise Exception(f"`clean.py` | {filename}: multi-part extensions are not supported (e.g. '.tar.gz')")

         config['outputfile_path'] = name + f'_processedby_marinedb' + ext

    if len(os.path.dirname(config['outputfile_path'])) == 0:
        config['outputfile_path'] = os.path.join(config['outputdir_path'], config['outputfile_path'])

    config['outputfile_path'] = resolvepath.apply(config['outputfile_path'])

    print()
    print(f"INFO | The processed file will be saved as {config['outputfile_path']}")

    outputdir = config['outputdir_path']
    outputfile = config['outputfile_path']

    # Processing section

    if ('processing' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a 'processing' section")

    if config['processing'] is None:
        # No processing step
        config['processing'] = []

    # Post-processing section

    if ('postprocessing' not in config.keys()):
        raise KeyError("`clean.py` | The configuration file must include a `postprocessing` section")

    if config['postprocessing'] is None:
        # No post-processing step
        config['postprocessing'] = []

    # Variables section

    if 'variables' not in config.keys():
        print('INFO | `variables` section not found: column filtering, type casting, and renaming will be skipped')
        config['variables'] = []

    if config['variables'] is None:
        config['variables'] = []

    isvariable = (len(config['variables']) != 0)

    # Verify that only supported functions are specified in the configuration file

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

    # Parse 'True' and 'False' strings as Boolean True and False values

    config = re.sub(r"'True'", r"True", str(config))
    config = re.sub(r"'False'", r"False", config)

    # Convert the `config` string back into a dictionary

    config = config.encode('utf8').decode('unicode_escape')
    config = yaml.safe_load(config)

    # For all functions with an `outputdir` argument, substitute the argument
    # with the configuration file's `inputdir_path` or `outputdir_path` value

    config = overwrite_outputdir_stdnan_dropempty_cleanup(config, config['inputfile_path'], config['inputdir_path'], config['outputdir_path'], cleanup)

    # Get the structure of the `config` processing section

    processing_schema = get_config_schema(config, key="processing")
    postprocessing_schema = get_config_schema(config, key="postprocessing")

    print(f"----- Start cleaning: {config['inputfile_path']} -----")
    print()

    start_cleaning = time.time()

    ##############################################
    ############### Pre-Processing ###############
    ##############################################

    print('Preprocessing')
    print('-------------')
    print()

    start_preprocessing = time.time()
    ispreprocessing = False

    # If specified, apply the `format` function

    format_call = [comb for comb in processing_schema if 'format' in comb]
    n_format_call = len(format_call)

    if n_format_call > 1:
        raise Exception(f"`clean.py` | `format` should be specified only once in the `config` file")

    if n_format_call == 1:

        ispreprocessing = True
        start = time.time()

        format_call = format_call[0]
        format_column_idx, format_column, format_idx = format_call[0], format_call[1], format_call[2]
        format_params = config['processing'][format_column_idx][format_column][format_idx]["format"]
        format_params["inputfile"] = config["inputfile_path"]

        print('* dataframe')
        print('** format')
        print()

        config['inputfile_path'] = format.apply(**format_params)
        temp_file = config['inputfile_path']

        del config['processing'][format_column_idx][format_column][format_idx]
        if len(config['processing'][format_column_idx][format_column]) == 0:
            del config['processing'][format_column_idx]

        processing_schema = get_config_schema(config, key="processing")

        end = time.time()
        print(f'TIME | step: {round(end - start)}s [total: {round(end - start_cleaning)}s]')
        print()

    # If specified, apply the `marineloc` filter

    marineloc_call = [comb for comb in processing_schema if 'marineloc' in comb]
    n_marineloc_call = len(marineloc_call)

    if n_marineloc_call > 1:
        raise Exception(f"`clean.py` | `marineloc` should be specified only once in the `config` file")

    if n_marineloc_call == 1:

        ispreprocessing = True
        start = time.time()

        marineloc_call = marineloc_call[0]
        marineloc_column_idx, marineloc_column, marineloc_idx = marineloc_call[0], marineloc_call[1], marineloc_call[2]
        marineloc_params = config['processing'][marineloc_column_idx][marineloc_column][marineloc_idx]["marineloc"]
        marineloc_params['inputfile'] = config['inputfile_path']
        marineloc_params['indent'] = '   '
        if args.cpu_max is not None:
            marineloc_params['cpu'] = args.cpu_max
        marineloc_params['outputfile'] = getdefaultoutputfile.apply(marineloc_params['inputfile'], 'marineloc', outputdir=outputdir, add_processedby=False, verbose=False)

        if ('latkey' in marineloc_params) and ('lonkey' in marineloc_params):
            print(f"* {marineloc_params['latkey']}, {marineloc_params['lonkey']}")
        print('** marineloc')
        print()

        config['inputfile_path'] = marineloc.apply(**marineloc_params)
        if ('temp_file' in locals()) and cleanup:
            os.remove(temp_file)
            temp_file = config['inputfile_path']

        print()

        del config['processing'][marineloc_column_idx][marineloc_column][marineloc_idx]
        if len(config['processing'][marineloc_column_idx][marineloc_column]) == 0:
            del config['processing'][marineloc_column_idx]

        processing_schema = get_config_schema(config, key="processing")

        end = time.time()
        print(f'TIME | step: {round(end - start)}s [total: {round(end - start_cleaning)}s]')
        print()

    if not ispreprocessing:
        print("INFO | No preprocessing steps specified (format, marineloc)")
        print()

    end = time.time()
    print(f'TIME | preprocessing: {round(end - start_preprocessing)}s [total: {round(end - start_cleaning)}s]')
    print()

    # If `createwormsfilters` or `isinworms` is specified,
    # generate the necessary filters using `createwormsfilters`

    ## Verify if `createwormsfilters` is specified
#    createwormsfilters_filter = [(idx, filter) for idx,filter in enumerate(config['processing']) if "'createwormsfilters'" in str(filter)]
#    createwormsfilters_column = get_keys([filter[1] for filter in createwormsfilters_filter])
    createwormsfilters_filter = [comb for comb in processing_schema if 'createwormsfilters' in comb] # NEW

    if len(createwormsfilters_filter) > 1:
        createwormsfilters_column = [comb[1] for comb in createwormsfilters_filter] # NEW
        raise Exception(f"`clean.py` | `createwormsfilters.py` must be applied to a single column. Select either {','.join(createwormsfilters_column[:-1])} or {createwormsfilters_column[-1]}")

    is_createwormsfilters = (len(createwormsfilters_filter) == 1)
    if is_createwormsfilters:
        createwormsfilters_filter = createwormsfilters_filter[0]

    ## Verify if `isinworms` is specified
#    isinworms_filter = [(idx, filter) for idx,filter in enumerate(config['processing']) if "'isinworms'" in str(filter)]
#    isinworms_column = get_keys([filter[1] for filter in isinworms_filter])
    isinworms_filter = [comb for comb in processing_schema if 'isinworms' in comb] # NEW

    if len(isinworms_filter) > 1:
        isinworms_column = [comb[1] for comb in isinworms_filter] # NEW
        raise Exception(f"`clean.py` | `isinworms.py` must be applied to a single column. Select either {','.join(isinworms_column[:-1])} or {isinworms_column[-1]}")

    is_isinworms = (len(isinworms_filter) == 1)
    if is_isinworms:
        isinworms_filter = isinworms_filter[0]

    is_isinworms_verbatim = False

    ## Verify if `resolvetaxamatch` is specified
#    resolvetaxamatch_filter = [(idx, filter) for idx,filter in enumerate(config['postprocessing']) if "'resolvetaxamatch'" in str(filter)]
#    resolvetaxamatch_column = get_keys([filter[1] for filter in resolvetaxamatch_filter])
    resolvetaxamatch_filter = [comb for comb in postprocessing_schema if 'resolvetaxamatch' in comb]

    if len(resolvetaxamatch_filter) > 1:
        resolvetaxamatch_column = [comb[1] for comb in resolvetaxamatch_filter] # NEW
        raise Exception(f"`clean.py` | `resolvetaxamatch.py` must be applied to a single column. Select either {','.join(resolvetaxamatch_column[:-1])} or {resolvetaxamatch_column[-1]}")

    is_resolvetaxamatch = (len(resolvetaxamatch_filter) == 1)
    if is_resolvetaxamatch:
        resolvetaxamatch_filter = resolvetaxamatch_filter[0]

    ## Ensure that if `createworms` is specified, `isinworms` is specified as well
    if is_createwormsfilters and not is_isinworms:
        raise Exception(f'`clean.py` | `isinworms` must be specified when using `createwormsfilter`')

    ## Ensure that `isinworms_params` is specified if `resolvetaxamatch` is used but `isinworms` is not

    if is_resolvetaxamatch:

        resolvetaxamatch_column_idx, resolvetaxamatch_column, resolvetaxamatch_idx = resolvetaxamatch_filter[0], resolvetaxamatch_filter[1], resolvetaxamatch_filter[2]
#        resolvetaxamatch_column_idx = resolvetaxamatch_filter[0][0]
#        resolvetaxamatch_column = resolvetaxamatch_column[0]
#        resolvetaxamatch_idx = get_keys(config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column]).index('resolvetaxamatch')
        resolvetaxamatch_params = deepcopy(config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column][resolvetaxamatch_idx])
        if isinstance(resolvetaxamatch_params, str):
            config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column][resolvetaxamatch_idx] = {'resolvetaxamatch':{}}
            resolvetaxamatch_params = deepcopy(config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column][resolvetaxamatch_idx])
        resolvetaxamatch_params = resolvetaxamatch_params['resolvetaxamatch']

        if (not is_isinworms):

            if 'isinworms_params' not in resolvetaxamatch_params.keys():
                raise Exception(f'`clean.py` | `isinworms_params` must be specified for `resolvetaxamatch` if `isinworms` is not defined in the configuration file')

            if 'rank_mapping' not in resolvetaxamatch_params['isinworms_params'].keys():
                config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column][resolvetaxamatch_idx]['resolvetaxamatch']['isinworms_params']['rank_mapping'] = getdefaultargs.apply(eval(f'tools.isinworms.apply'))['rank_mapping']

    if is_isinworms:

        # Set up the required components to apply the `isinworms` filter

        ## Default `createwormsfilters` parameters
        default_createwormsfilters_params = getdefaultargs.apply(cwf.apply)
        default_createwormsfilters_args = list(default_createwormsfilters_params.keys())

        ## Retrieve `isinworms` parameters
        isinworms_column_idx, isinworms_column, isinworms_idx = isinworms_filter[0], isinworms_filter[1], isinworms_filter[2]
#        isinworms_column_idx = isinworms_filter[0][0]
#        isinworms_column = isinworms_column[0]
#        isinworms_idx = get_keys(config['processing'][isinworms_column_idx][isinworms_column]).index('isinworms')
        isinworms_params = deepcopy(config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms'])
        isinworms_args = list(isinworms_params.keys())

        if 'interactive_mode' not in isinworms_args:
            isinworms_interactive_mode = getdefaultargs.apply(eval(f'tools.isinworms.apply'))['interactive_mode']
        else:
            isinworms_interactive_mode = isinworms_params['interactive_mode']
        if args.parallel and isinworms_interactive_mode:
            raise Exception(f"`clean.py` | interactive_mode=True is incompatible with parallel execution of `clean.py`. Run it sequentially, or delegate interactive matching to `resolvetaxamatch.py` in the `postprocessing` section of the configuration file")

        ## Extract `createwormsfilters` parameters from the `isinworms` configuration
        isinworms_createwormsfilters_params = {arg : isinworms_params[arg] for arg in isinworms_args if arg in default_createwormsfilters_args}
        isinworms_createwormsfilters_params['colname'] = isinworms_column
        isinworms_createwormsfilters_params['outputdir'] = isinworms_params['outputdir_createwormsfilters']
        if 'overwrite_createwormsfilters' in isinworms_args:
            isinworms_createwormsfilters_params['overwrite'] = isinworms_params['overwrite_createwormsfilters']
#        if 'overwrite_parallel_createwormsfilters' in isinworms_args:
#            isinworms_createwormsfilters_params['overwrite_parallel'] = isinworms_params['overwrite_parallel_createwormsfilters']
        if 'store_createwormsfilters' in isinworms_args:
            isinworms_createwormsfilters_params['store'] = isinworms_params['store_createwormsfilters']
#        if 'store_parallel_createwormsfilters' in isinworms_args:
#            isinworms_createwormsfilters_params['store_parallel'] = isinworms_params['store_parallel_createwormsfilters']
        isinworms_createwormsfilters_args = list(isinworms_createwormsfilters_params.keys())

        if is_createwormsfilters:

            ## Retrieve `createwormsfilters` parameters
            createwormsfilters_column_idx, createwormsfilters_column, createwormsfilters_idx = createwormsfilters_filter[0], createwormsfilters_filter[1], createwormsfilters_filter[2]
#            createwormsfilters_column_idx = createwormsfilters_filter[0][0]
#            createwormsfilters_column = createwormsfilters_column[0]
#            createwormsfilters_idx = get_keys(config['processing'][createwormsfilters_column_idx][createwormsfilters_column]).index('createwormsfilters')
            createwormsfilters_params = deepcopy(config['processing'][createwormsfilters_column_idx][createwormsfilters_column][createwormsfilters_idx]['createwormsfilters'])
            createwormsfilters_params['colname'] = createwormsfilters_column
            createwormsfilters_params['store'] = True
#            createwormsfilters_params['store_parallel'] = True
            createwormsfilters_params['inputfile'] = config['inputfile_path']
            createwormsfilters_params['indent'] = '   '
            createwormsfilters_args = list(createwormsfilters_params.keys())

            ## Extend the wormscall value to both `isinworms` and `createwormsfilters` if specified in either
            if 'wormscall' not in createwormsfilters_args:
                if 'wormscall' in isinworms_createwormsfilters_args:
                    print(f'INFO | `wormscall` not found in `createwormsfilters`, use value from `isinworms`')
                    print()
                    createwormsfilters_params['wormscall'] = isinworms_createwormsfilters_params['wormscall'].copy()
                    createwormsfilters_args.append('wormscall')
            else:
                if 'wormscall' not in isinworms_createwormsfilters_args:
                    print(f'INFO | `wormscall` not found in `isinworms`, use value from `createwormsfilters`')
                    print()
                    isinworms_createwormsfilters_params['wormscall'] = createwormsfilters_params['wormscall'].copy()
                    isinworms_createwormsfilters_args.append('wormscall')

            ## Set unspecified parameters in `createwormsfilters` to their default values
            for arg, val in default_createwormsfilters_params.items():
                if arg not in createwormsfilters_args:
                    createwormsfilters_params[arg] = val

            ## Ensure that parameter values in `isinworms` do not conflict with those in `createwormsfilters`
            if createwormsfilters_column != isinworms_column:
                raise ValueError(f"`clean.py` | `createwormsfilters` and `isinworms` must operate on the same column containing scientific names, but received '{createwormsfilters_column}' and '{isinworms_column}' respectively.")
            intersection_args = set(isinworms_createwormsfilters_params.keys()).intersection(set(createwormsfilters_params.keys()))
            exclude_args = set(['inputfile','colname','verbose','indent','skip_uniques_rebuild'])
            intersection_args -= exclude_args
            conflicting_args = [f'`{arg}`' for arg in intersection_args if createwormsfilters_params[arg] != isinworms_createwormsfilters_params[arg]]
            if len(conflicting_args) != 0:
                raise ValueError(f"`clean.py` | Conflicting {','.join(conflicting_args)} values between `createwormsfilters` and `isinworms`")

            ## Use parameters from `createwormsfilters` to complete the `isinworms` configuration
            for arg, val in createwormsfilters_params.items():
                if arg not in exclude_args:
                    if arg in ['overwrite', 'outputdir', 'store']: # 'store_parallel' 'overwrite_parallel'
                         isinworms_params[f'{arg}_createwormsfilters'] = createwormsfilters_params[arg]
                    else:
                        try:
                            isinworms_params[arg] = createwormsfilters_params[arg].copy()
                        except AttributeError:
                            isinworms_params[arg] = createwormsfilters_params[arg]

        else:

            createwormsfilters_params = deepcopy(isinworms_createwormsfilters_params)
            createwormsfilters_params['verbose'] = True
            createwormsfilters_params['indent'] = '   '

        if 'rank_mapping' not in isinworms_args:
            isinworms_params['rank_mapping'] = getdefaultargs.apply(eval(f'tools.isinworms.apply'))['rank_mapping']

        if isinworms_params['rank_mapping']['scientificname'] != isinworms_column:
            raise ValueError(f"`clean.py` | The value associated with the 'scientificname' key in the 'rank_mapping' argument of the `isinworms` function (i.e., '{isinworms_params['rank_mapping']['scientificname']}') must match the name of the column the filter is applied to (i.e., '{isinworms_column}')")

        if 'verbatimcolumn' in isinworms_args:
            if (isinworms_params['verbatimcolumn'] is not None) and (len(isinworms_params['verbatimcolumn']) != 0): # None, empty string, empty list
                is_isinworms_verbatim = True
                if isinstance(isinworms_params['verbatimcolumn'], str):
                    isinworms_params['verbatimcolumn'] = [isinworms_params['verbatimcolumn']]
                if isinstance(isinworms_params['verbatimauthorshiponly'], str):
                    isinworms_params['verbatimauthorshiponly'] = [isinworms_params['verbatimauthorshiponly']]

        mandatory_keys = ['AphiaID','match_type','status']
        if not isinworms_params['keep_fossil']:
            mandatory_keys.append('isExtinct')
        missing_keys = set(mandatory_keys) - set(createwormsfilters_params['wormscall'])
        for key in missing_keys:
            createwormsfilters_params['wormscall'].append(key)
            isinworms_params['wormscall'].append(key)
        auxiliary_columns = list(missing_keys)

        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms'] = isinworms_params
        config['processing'][createwormsfilters_column_idx][createwormsfilters_column][createwormsfilters_idx]['createwormsfilters'] = createwormsfilters_params

        if is_resolvetaxamatch:

            # Ensure that auxiliary columns required during processing but
            # not requested by the user are removed from the final dataset

            config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column][resolvetaxamatch_idx]['resolvetaxamatch']['auxiliary_columns'] = auxiliary_columns

            ## Ensure that uncertain mismatches are retained in `isinworms`
            ## so they can later be resolved through manual review

            print("INFO | `flag_uncertain` temporarily set to True in `isinworms` because `resolvetaxamatch` requires uncertain mismatches to be retained for manual review")
            flag_uncertain = config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['flag_uncertain']
            config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['flag_uncertain'] = True
            config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column][resolvetaxamatch_idx]['resolvetaxamatch']['flag_uncertain'] = flag_uncertain

            ## Ensure consistency between `uncertainty_level` in `isinworms` and `review_level` in `resolvetaxamatch`
            ## If needed, increase `uncertainty_level` to prevent reviewable uncertain mismatches
            ## from being prematurely categorized as "nomatch"

            if 'review_level' in resolvetaxamatch_params.keys():
                review_level = resolvetaxamatch_params['review_level']
            else:
                review_level = getdefaultargs.apply(resolvetaxamatch.apply)['review_level']

            if 'uncertainty_level' in isinworms_params.keys():
                uncertainty_level = isinworms_params['uncertainty_level']
            else:
                uncertainty_level = getdefaultargs.apply(eval(f'tools.isinworms.apply'))['uncertainty_level']

            if review_level > uncertainty_level:
                print(f"INFO | `uncertainty_level` increased to {review_level} in `isinworms` to ensure that records eligible for manual review in `resolvetaxamatch` are not categorized as 'nomatch'")
                config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['uncertainty_level'] = review_level

            isinworms_params = config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']

            ## Use the main `isinworms` configuration for `resolvetaxamatch` `isinworms_params`
            config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column][resolvetaxamatch_idx]['resolvetaxamatch']['isinworms_params'] = isinworms_params
            print("INFO | `resolvetaxamatch` `isinworms_params` overwritten with the main `isinworms` parameters")
            print()

        # Load existing taxonomic filters or generate new ones if none are found

        print('Initialization')
        print('--------------')
        print()
        print(f"* {createwormsfilters_params['colname']}")
        print('** createwormsfilters')
        print()

        start = time.time()

        worms_matchfilter, worms_acceptedfilter = cwf.apply(**createwormsfilters_params)

        # Add the filters to `config`

        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['matchfilter'] = worms_matchfilter.copy(deep=True)
        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['acceptedfilter'] = worms_acceptedfilter.copy(deep=True)

        del worms_matchfilter
        del worms_acceptedfilter
        if is_createwormsfilters:
            del config['processing'][createwormsfilters_column_idx][createwormsfilters_column][createwormsfilters_idx]

        end = time.time()
        print(f'TIME | step: {round(end - start)}s [total: {round(end - start_cleaning)}s]')
        print()

    ##########################################
    ############### Processing ###############
    ##########################################

    # Read the gzip or uncompressed data file

    print('Processing')
    print('----------')
    print()

    start_processing = time.time()

    parallel = args.parallel
    if not parallel:
        cpu_max = 1
    else:
        cpu_max = args.cpu_max
    parallel, cpu_main = set_cpu(config, parallel, cpu_main=None, cpu_max=cpu_max)

    # TODO: open the file with 'rt' instead of 'r' to avoid using `decode_line`
    open_file, decode_line = readfile.apply(config['inputfile_path'])

    # `Variables` section

    ## Default to all columns if no variables are selected
    if not isvariable:
        with open_file(config['inputfile_path'],'r') as data:
            header = decode_line(data.readline()).strip('\n').split('\t')
        config['variables'] = header

    ## Add 'index_marinedb' column to support process resumption
    config['variables'].append({'index_marinedb': {'index_marinedb': 'int'}})

    ## If `resolvetaxamatch` and verbatim columns are specified,
    ## include verbatim and authorship columns in the `variables` section

    if is_isinworms and is_isinworms_verbatim and is_resolvetaxamatch:
        variables = get_keys(config['variables'])
        for col in isinworms_params['verbatimcolumn']:
            if col not in variables:
                config['variables'].append({col: {col: 'string'}})
                auxiliary_columns.append(col)
        config['postprocessing'][resolvetaxamatch_column_idx][resolvetaxamatch_column][resolvetaxamatch_idx]['resolvetaxamatch']['auxiliary_columns'] = auxiliary_columns

    ## If `taxasubset` is used with `isinworms`, include 'AphiaID' in the `variables` section
    if is_isinworms and ('taxasubset' in str(config['postprocessing'])):
        variables = get_keys(config['variables'])
        if 'AphiaID' not in variables:
            config['variables'].append({'AphiaID': {'AphiaID': 'Int64'}})

    if parallel:
        if 'marinedb_parallel' not in outputdir.split('/'):
            outputdir = os.path.join(outputdir,'marinedb_parallel')
            try:
                os.mkdir(outputdir)
            except FileExistsError:
                pass
    else:
        outputdir = ''

    if (len(config['processing']) != 0):

        nbatch = 0
        resume = False
        columns = None
        init_storage = True
        config_variables_updated = None
        start = time.time()

        # Resume processing

        if parallel:
            files = [entry.path for entry in os.scandir(outputdir) if entry.is_file() and ('time_' not in entry.name)]
            if len(files) != 0:
                print(f'* Restart processing from {outputdir}')
                resume = True
                indices2process, lastindex, nbatch, columns, config_variables_updated, config_variables_updated_outputfile = resume_parallel_processing(outputdir, args.config_file, config, verbose=True)
                if indices2process is None:
                    resume = False
                print()
            elif os.path.isfile(outputfile):
                print(f'* Restart processing from {outputfile}')
                resume = True
                indices2process, lastindex, columns, config_variables_updated, config_variables_updated_outputfile = resume_noparallel_processing(outputfile, args.config_file, config, verbose=True)
                if indices2process is None:
                    resume = False
                print()
        else:
            if os.path.isfile(outputfile):
                print(f'* Restart processing from {outputfile}')
                resume = True
                init_storage = False
                indices2process, lastindex, columns, config_variables_updated, config_variables_updated_outputfile = resume_noparallel_processing(outputfile, args.config_file, config, verbose=True)
                if indices2process is None:
                    resume = False
                    init_storage = True
                print()

        skip = resume
        dtypes_mapping = get_dtypes(config, key_type='old')
        dtypes_mapping['index_marinedb'] = 'Int64'

        with open_file(config['inputfile_path'],'r') as data:

            header = decode_line(data.readline()).strip('\n').split('\t')
            header_length = len(header)

            batch = 0
            error = []
            data2clean = []
            init_process = True

            for idx, line in enumerate(data, start=2):

                # Resume processing

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
                    raise SplittingError(idx, len(obs), header_length, line)

                if init_process and (batch == BATCH_SIZE):

                    # Process initialization

                    print(f'--- Processing | {batch} lines ---')
                    print()
                    print(f'INFO | Processing the initial batch separately to configure the environment')
                    print()

                    try:
                        df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header, dtype=dtypes_mapping)
                    except:
                        df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header)

                    if parallel:
                        cpu_idx = ((nbatch + 1) if resume else nbatch)
                    else:
                        cpu_idx = None

                    config_variables_updated, columns = process_one_dataframe(df2clean, config, config_variables_updated, isvariable, outputfile, outputdir=outputdir, columns=columns, cpu_idx=cpu_idx, verbose=True, init_process=init_process, init_storage=init_storage)

                    config_variables_updated_outputfile = os.path.basename(args.config_file).split('.')[0]
                    config_variables_updated_outputfile = os.path.join(config['outputdir_path'], f'{config_variables_updated_outputfile}_updated.yaml')
                    with open(config_variables_updated_outputfile, 'w') as f:
                        yaml.dump(config_variables_updated, f, Dumper=MyDumper, default_flow_style=False)

                    init_process = False
                    init_storage = False
                    data2clean.clear()
                    del df2clean
                    batch = 0
                    nbatch += 1

                if (not init_process) and (batch == cpu_main*BATCH_SIZE):

                    # Process data

                    print(f'--- Processing | {batch} lines on {cpu_main} CPUs ---')
                    print()

                    try:
                        df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header, dtype=dtypes_mapping)
                    except:
                        df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header)
                    data2clean.clear()

                    index_start = list(range(batch))[::BATCH_SIZE]
                    index_end = list(range(BATCH_SIZE,batch))[::BATCH_SIZE] + [batch]
                    index_slices = list(zip(index_start,index_end))

                    params = {
                              'config': config,
                              'config_variables_updated': config_variables_updated,
                              'isvariable': isvariable,
                              'outputfile': outputfile,
                              'outputdir': outputdir,
                              'columns': columns,
                              'init_process': False,
                             }

                    if cpu_main != 1:

                        # parallel processing

                        process = Parallel(n_jobs=cpu_main, backend='multiprocessing')
                        chunks = [df2clean.iloc[i:j,:].copy(deep=True) for i,j in index_slices]
                        del df2clean

                        params['verbose'] = False
                        params['init_storage'] = True

                        _ = process(delayed(process_one_dataframe)(chunk, cpu_idx=(i+nbatch), **params) for i,chunk in enumerate(chunks))
                        del chunks

                    else:

                        # sequential processing

                        params['cpu_idx'] = None
                        params['verbose'] = True
                        params['init_storage'] = init_storage

                        _ = process_one_dataframe(df2clean, **params)
                        del df2clean

                    batch = 0
                    nbatch += cpu_main
                    print(f'TIME | processing: {round(time.time() - start_processing)}s [total: {round(time.time() - start_cleaning)}s]')
                    print()

        if batch != 0:

            # Process the final incomplete batch

            # adjust the number of CPUs
            cpu_main = math.ceil(batch/BATCH_SIZE)
            _, cpu_main = set_cpu(config, parallel, cpu_main=cpu_main, cpu_max=cpu_max)

            try:
                df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header, dtype=dtypes_mapping)
            except:
                df2clean = pd.DataFrame(data2clean, columns = ['index_marinedb'] + header)

            index_start = list(range(batch))[::BATCH_SIZE]
            index_end = list(range(BATCH_SIZE,batch))[::BATCH_SIZE] + [batch]
            index_slices = list(zip(index_start,index_end))
            assert len(index_slices) == cpu_main

            if parallel:
                cpu_idx = ((nbatch + 1) if (init_process and resume) else nbatch)
            else:
                cpu_idx = None

            print(f'--- Processing | {batch} lines on {cpu_main} CPUs ---')
            print()

            params = {
                      'config': config,
                      'config_variables_updated': config_variables_updated,
                      'isvariable': isvariable,
                      'outputfile': outputfile,
                      'outputdir': outputdir,
                      'columns': columns,
                      'init_process': False,
                     }

            if cpu_main != 1:

                # parallel processing

                process = Parallel(n_jobs=cpu_main, backend='multiprocessing')
                chunks = [df2clean.iloc[i:j,:].copy(deep=True) for i,j in index_slices]
                del df2clean

                params['verbose'] = False
                params['init_storage'] = True

                results = process(delayed(process_one_dataframe)(chunk, cpu_idx=(i+nbatch), **params) for i,chunk in enumerate(chunks))
                del chunks

            else:

                # sequential processing

                params['cpu_idx'] = cpu_idx
                params['verbose'] = True
                params['init_process'] = init_process
                params['init_storage'] = init_storage

                _ = process_one_dataframe(df2clean, **params)
                del df2clean

        if parallel:

            # Merge files generated during parallel processing

            concat_times(os.path.join(outputdir, 'time'), os.path.dirname(outputfile))
            assemble_outputfile(outputdir, outputfile, columns, cleanup)

        # Store dtypes

        if config_variables_updated is not None:
            dtypes_mapping = get_dtypes(config_variables_updated, key_type='new')
            dtypes_outputfile = os.path.join(config['outputdir_path'], 'marinedb_dtypes.json')
            with open(dtypes_outputfile, 'w') as f:
                json.dump(dtypes_mapping, f, indent=4)

        # Set up for post-processing

        inputfile = outputfile

    elif isvariable:

        # No processing apart from column selection and renaming

        ## Ensure enough disk space is available for the output file

        outputfile_dir = os.path.dirname(outputfile)
        _, _, available_disk_space = shutil.disk_usage(outputfile_dir)
        inputfile_size = os.stat(config['inputfile_path']).st_size

        if readfile.isgzip.apply(config['inputfile_path']):
            required_space = inputfile_size * 6 # 8 to be sure
        else:
            required_space = inputfile_size + inputfile_size // 10

        if available_disk_space < required_space:
            raise Exception(
                f"`clean.py` | Not enough disk space in {outputfile_dir}: "
                f"{convertbytes.apply(available_disk_space)} available, "
                f"at least {convertbytes.apply(required_space)} required."
             )

        ## Select and rename columns

        # AJOUTER UN PRINT !

        print(f'--- Selecting and renaming columns ---')
        print()

        with open_file(config['inputfile_path'],'rt', encoding='utf-8') as src:

            header_old = src.readline().rstrip('\n').split('\t')
            header_length = len(header_old)
            colnames_mapping = get_column_mapping(config)

            indices = [idx for idx, col in enumerate(header_old) if col in colnames_mapping]
            if len(indices) == 0:
                raise Exception("`clean.py` | The `variables` section does not contain any columns from the input file.")
            header_new = [colnames_mapping[col] for col in header_old if col in colnames_mapping]

            with open(outputfile, 'wt', encoding='utf-8') as dst:

                dst.write('\t'.join(header_new) + '\n')

                for i, line in enumerate(src, start=2):

                    fields = line.rstrip('\n').split('\t')

                    if len(fields) != header_length :
                        raise SplittingError(i, len(fields), header_length, line)

                    selected = [fields[idx] for idx in indices]
                    dst.write('\t'.join(selected) + '\n')

                    if ((i+1)%1000000 == 0):
                        print(f'Progress | {(i+1):,d} lines done')

        # Set up for post-processing

        inputfile = outputfile

        dtypes_mapping = get_dtypes(config, key_type='new')
        dtypes_outputfile = os.path.join(config['outputdir_path'], 'marinedb_dtypes.json')
        with open(dtypes_outputfile, 'w') as f:
            json.dump(dtypes_mapping, f, indent=4)

    else:

        # No processing

        print("INFO | No processing step specified")

        inputfile = config['inputfile_path']

    end = time.time()
    print()
    print(f'TIME | processing: {round(end - start_processing)}s [total: {round(end - start_cleaning)}s]')
    print()

    ###############################################
    ############### Post-processing ###############
    ###############################################

    print('Post-processing')
    print('---------------')
    print()

    start_postprocessing = time.time()

    if len(config['postprocessing']) != 0:

        # Verify that only supported functions are specified in the configuration file

        postprocfuncs = get_procfunc(config, 'postprocessing')
        unsupported_funcs = set(postprocfuncs) - set(SUPPORTED_POSTPROCFUNCTIONS)
        if len(unsupported_funcs) != 0:
            raise ValueError(f"`clean.py` | {','.join(list(unsupported_funcs))} are not supported functions.")

        if 'dtypes_outputfile' not in locals():
	        dtypes_outputfile = None

        # order post-processing steps
        config = order_postprocfunc(config)
        # update column names in parameters to reflect renaming during processing
        config = update_config_postprocessing(config, inputfile, isvariable, is_isinworms, is_isinworms_verbatim, dtypes_outputfile)

        for procstep in config['postprocessing']:

            # Iterate over post-processing steps

            colname = list(procstep.keys())[0]

            for proc in procstep[colname]:

                if isinstance(proc, dict):
                    proc_name = list(proc.keys())[0]
                    proc_params = proc[proc_name]
                else:
                    proc_name = proc
                    proc_params = {}

                proc_params['inputfile'] = inputfile

                if proc_name == 'resolvetaxamatch':

                    # `resolvetaxamatch`

                    start = time.time()

                    print('* dataframe')
                    print('** resolvetaxamatch')
                    print()

                    outputfile = resolvetaxamatch.apply(**proc_params)
                    inputfile = outputfile

                    end = time.time()
                    print(f'TIME | step: {round(end - start)}s [total: {round(end - start_cleaning)}s]')
                    print()

                elif proc_name == 'taxasubset':

                    # `taxasubset`

                    start = time.time()

                    isspeciesidkey = ('speciesidkey' in proc_params.keys()) and proc_params['speciesidkey'] and (len(proc_params['speciesidkey']) != 0)
                    if is_isinworms or isspeciesidkey:
                        columns = [proc_params['speciesidkey']]
                    else:
                        columns = [proc_params[key] for key in ['specieskey', 'genuskey', 'familykey', 'orderkey', 'classkey', 'phylumkey', 'kingdomkey']]

                    columns = ', '.join(columns)
                    print(f'* {columns}')
                    print('** taxasubset')
                    print()

                    with open(inputfile,'r') as data: # debug ?
                        header_before = data.readline().strip('\n').split('\t')

                    outputfile = taxasubset.apply(**proc_params)
                    inputfile = outputfile

                    with open(outputfile,'r') as data: # debug ?
                        header_after = data.readline().strip('\n').split('\t')

                    header_diff = list(set(header_after) - set(header_before)) # debug ?
                    assert len(header_diff) <= 1
                    if ('dtypes_mapping' in locals()) and (len(header_diff) == 1):
                        dtypes_mapping[header_diff[0]] = 'boolean'

                    end = time.time()
                    print(f'TIME | step: {round(end - start)}s [total: {round(end - start_cleaning)}s]')
                    print()

                else:
                    raise Exception('`clean.py` | [DEV] An exception should have been raised before this line of code')

                config['outputfile_path'] = outputfile

    else:

        # No post-processing

        print("INFO | No post-processing step specified")

    end = time.time()
    print(f'TIME | post-processing: {round(end - start_postprocessing)}s [total: {round(end - start_cleaning)}s]')
    print()

    print(f"----- End cleaning {config['inputfile_path']} -----")
    print()

    # Store dtypes

    if ('dtypes_outputfile' in locals()) and (dtypes_outputfile is not None):
        with open(dtypes_outputfile, 'w') as f:
            json.dump(dtypes_mapping, f, indent=4)

    # Clean

    if cleanup:

        print('* Cleaning up intermediate files')
        print()

        if ('temp_file' in locals()):
            print(f'  >>> {temp_file}')
            os.remove(temp_file)

        files = os.listdir(config['inputdir_path'])
        generated_files = list(set(files) - set(initial_files))
        generated_files = [os.path.join(config['inputdir_path'],f) for f in generated_files]
        for file in generated_files:
            print(f'  >>> {file}')
            if os.path.isdir(file):
                if not os.listdir(file):
                    os.rmdir(file)
            else:
                os.remove(file)

        if len(os.listdir(config['inputdir_path'])) == 0:
            print(f"  >>> {config['inputdir_path']}")
            os.rmdir(config['inputdir_path'])

        if ('config_variables_updated_outputfile' in locals()) and (config_variables_updated_outputfile is not None):
            print(f'  >>> {config_variables_updated_outputfile}')
            os.remove(config_variables_updated_outputfile)

    print()

    print(f'TIME: {round(time.time() - start_cleaning)}s')
    print()
