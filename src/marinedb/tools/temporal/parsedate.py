#!/usr/bin/python
# coding: utf-8

# External import

import re
import os
import copy
import itertools
import subprocess
import pandas as pd
from tqdm import tqdm
from joblib import Parallel, delayed
from importlib.resources import files

# Internal import

from marinedb.utils import tqdmjoblib
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname
from marinedb.tools import modifyissuecolumn
from marinedb.tools.temporal import isdatemismatch
from marinedb.tools.temporal import convertdatetype

# Global variables

__all__ = [] # populated using the @export decorator

JAR_PATH = files('marinedb.tools.temporal').joinpath('gbif-date-parser-20250604.jar')

TIMEOUT = 3600 #seconds

def execute_java(multiple_datestr, verbose=True, indent=''): #verbose indent deug

    Ndates = multiple_datestr.count(';') + 1

    # Execute the java command

    cmd = ['java', '-XX:+PerfDisableSharedMem', '-jar', JAR_PATH, multiple_datestr]

    p = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    keys = []
    stdout = []
    stderr = []
    i = -1
    for line in p.stdout:
        line = line.decode('utf-8').strip()
        nsep = line.count('=')
        if nsep == 1:
            if 'SUCCESS' in line:
                stdout.append(line)
            elif ('ERROR' in line) or ('JAVAEXCEPTION' in line):
                stderr.append(line)
            else:
                raise Exception(f'`parsedate.py` | [DEV] Unexpected output : {line}')
        elif nsep == 2:
            single_datestr = re.search(r'DATE=(.*)\s',line).group(1)
            single_ordering = re.search(r'ORDERING=(.*)$',line).group(1)
            keys.append((single_datestr,single_ordering))
            i += 1
        else:
            raise Exception(f'`parsedate.py` | Unexpected output: more than two equality signs in {line}')

    return_code = p.wait()
    if return_code != 0:
        raise Exception(f"`parsedate.py` | Java process failed with code {return_code}")

    assert len(stderr) == Ndates
    assert len(stdout) == Ndates

    return keys, stdout, stderr

def parse_javastdout(single_stdout, single_request):

    datestr_processed = single_stdout.split('=')[1]

    if len(datestr_processed) == 0:
        datestr_processed = pd.NA

    else:
        datestr_processed = datestr_processed.split()

        if len(datestr_processed) != 2:
            raise Exception(f'`parsedate.py` | Unexpected output for {single_request}: stdout={single_stdout}')

        datestr_processed = [d[:10] for d in datestr_processed] # remove time details
        datestr_processed = sorted(list(set(datestr_processed)))
        datestr_processed = '/'.join(datestr_processed)

    return datestr_processed

def parse_java(multiple_datestr, datekey, raise_javaexception=False, verbose=True, indent=''):

    basedatekey = datekey.split('_processedby_')[0].upper()

    # Execute the java command

    keys, stdout, stderr = execute_java(multiple_datestr, verbose=verbose, indent=indent)

    # Process the command output
    # format: SUCCESS:date1 date2 or ERROR:error or RAISE:error_message or JAVAEXCEPTION:error_message

    ## Capture raised errors

    for i,single_stderr in enumerate(stderr):

        single_stderr = single_stderr.split('=')

        if len(single_stderr) != 2:
            raise Exception(f'`parsedate.py` | [DEV] {keys[i]}: ' + '='.join(single_stderr))

        elif len(single_stderr[1]) != 0:

            stderr_type = single_stderr[0]
            stderr_message = single_stderr[1]

            if stderr_type == 'RAISE':
                raise Exception(f'`parsedate.py` | {keys[i]}: ' + stderr_message)

            if stderr_type == 'JAVAEXCEPTION':
                stderr_message = stderr_message.split()
                error_type = stderr_message[0]
                error_msg = ' '.join(stderr_message[1:])
                if raise_javaexception:
                    raise Exception(f'`parsedate.py` | {error_type} raised for {keys[i]}: {error_msg}')
                else:
                    printv(f'WARNING | {error_type} raised for {keys[i]}: {error_msg}', verbose=verbose, indent=indent)
                    stderr[i] = f'{basedatekey}_JAVA_' + error_type.split('.')[-1].upper()

            elif stderr_type == 'ERROR':
                if len(stderr_message.split()) > 1:
                    # multiple error messages detected
                    # java code flaw
                    stderr_message = re.sub('RECORDED_DATE_MISMATCH','',stderr_message).strip()
                if len(stderr_message.split()) > 1:
                    # multiple error messages detected
                    # note: never encountered during testing
                    stderr_message = ';'.join(stderr_message.split())
                    print('unexpected:',stderr_message) #debug
                stderr[i] = re.sub('RECORDED_DATE',f'{basedatekey}',stderr_message)

            else:
                raise Exception(f'`parsedate.py` | [DEV] Unexpected error type for {keys[i]}: {single_stderr}')

        else:

            stderr[i] = pd.NA

    ## Extract the two parsed dates

    for i,single_stdout in enumerate(stdout):

        stdout[i] = parse_javastdout(single_stdout, keys[i])

    return list(zip(stdout,stderr))

def validate_format(format):

    # Validate the ordering preference string (`format`)

    _, _, stderr = execute_java(f"('2003-06-02', '{format}')", verbose=False) #debug
    stderr = stderr[0].split('=')

    if len(stderr) != 2:
        raise Exception('`parsedate.py` | ' + '='.join(stderr))

    if stderr[0] == 'RAISE':
        raise Exception('`parsedate.py | ' + stderr[1])

def create_javaarg(datesstr_list, format=None):

    # Validate the ordering preference string (`format`)

    if format is None:
        format=''
    if isinstance(format, list):
        if (len(datesstr_list)!=len(format)):
            raise ValueError(f'`parsedate.py` | `datesstr_list` and `format` must have the same length')
        for fmt in format:
            validate_format(fmt)
    if isinstance(format, str):
        validate_format(format)
        format = [format]*len(datesstr_list)
    if not isinstance(format, str | list):
        raise TypeError(f'`parsedate.py` | `format` must be a string or a list, not a {type(format).__name__}')

    # Remove any character that holds structural significance in the Java command

    datesstr_list = pd.Series(datesstr_list).str.replace(r'[,;()"]+' + r"|'+",' ',regex=True)
    datesstr_list = datesstr_list.str.replace(r'\s+',' ',regex=True)
    datesstr_list = datesstr_list.str.strip().tolist()

    # Create the Java command
    # e.g "('2025-03-04','');('01-1997','')"

    multiple_datestr = list(zip(datesstr_list,format))
    multiple_datestr = [str(single_request) for single_request in multiple_datestr]
    multiple_datestr = ';'.join(multiple_datestr)

    return multiple_datestr

def gbif_dateparser(df, datekey, index, format=None, raise_javaexception=False, verbose=True, indent=''):

    multiple_datesstr = df.loc[index,datekey].tolist()
    multiple_datestr = create_javaarg(multiple_datesstr, format=format)
    result = parse_java(multiple_datestr, datekey, raise_javaexception=raise_javaexception, verbose=verbose, indent=indent)

    return result

def parallel_dateparser(df, datekey, datestr_index, cpu, format=None, raise_javaexception=False, verbose=True, indent=''):

    ndates = len(datestr_index)
    batch_size = 1000
    index_start = list(range(ndates))[::batch_size]
    index_end = list(range(batch_size,ndates))[::batch_size] + [ndates]
    index_slides = list(zip(index_start,index_end))

    nbatch = len(index_slides)
    cpu = min(cpu, nbatch)

    printv(f"* Parse {datekey.split('_processedby_')[0]} | {ndates} dates to process ({nbatch} batches)", verbose=verbose, indent=indent)
    printv(f'INFO | {cpu} CPUs will be used', verbose=verbose, indent=indent)

    params = {
              'format': format,
              'raise_javaexception': raise_javaexception,
              'verbose': verbose,
              'indent': indent
             }

    if cpu != 1:
        parallel = Parallel(n_jobs=cpu, prefer='threads')
        # Note: the outputs are returned in the same order as the submissions
        if verbose:
            with tqdmjoblib.apply(tqdm(desc=indent + 'Progress', total=nbatch)) as progress_bar:
                results = parallel(delayed(gbif_dateparser)(df, datekey, copy.deepcopy(datestr_index[start:end]), **params) for start,end in index_slides)
        else:
            results = parallel(delayed(gbif_dateparser)(df, datekey, copy.deepcopy(datestr_index[start:end]), **params) for start,end in index_slides)
        results = list(itertools.chain(*results))

    if cpu == 1:
        results = []
        if verbose:
            process = tqdm(index_slides, desc=indent + 'Progress')
        else:
            process = index_slides
        for start,end in process:
            results += gbif_dateparser(df, datekey, datestr_index[start:end], **params)

    printv('', verbose=verbose)

    return results

def assemble_date(df, datekey, datekeyout, yearkey=None, monthkey=None, daykey=None, stdnan=True, parallel=False, cpu=None, verbose=True, indent=''):

    if (yearkey is None):
        return df

    basedatekey = datekey.split('_processedby_')[0].upper()
    _, yearkey, _ = getcolumnname.apply(df, yearkey, '', inplace=True)
    if (monthkey is not None):
        _, monthkey, _ = getcolumnname.apply(df, monthkey, '', inplace=True)
    if (daykey is not None):
        _, daykey, _ = getcolumnname.apply(df, daykey, '', inplace=True)

    print_colnames = [yearkey, monthkey, daykey]
    print_colnames = [col.split('_processedby_')[0] for col in print_colnames if col is not None]
    printv(f'* Build date from {", ".join(print_colnames)} columns', verbose=verbose, indent=indent)

    # Exclude lines with a missing or unlikely year value

    date2process = (pd.isnull(df[datekeyout])) & (df['issue_parsedate'] != f'{basedatekey}_UNLIKELY')
#    print(df.loc[date2process,datekey]) #debug

    baseyearkey = yearkey.split('_processedby_')[0].upper()
    df[f'TEMPORARYPARSEDATE_{yearkey}'] = df[yearkey].values
    yearkey = f'TEMPORARYPARSEDATE_{yearkey}'
    tempcol = [yearkey]
    joincol = []
    if (monthkey is not None):
        basemonthkey = monthkey.split('_processedby_')[0].upper()
        df[f'TEMPORARYPARSEDATE_{monthkey}'] = df[monthkey].values
        monthkey = f'TEMPORARYPARSEDATE_{monthkey}'
        tempcol.append(monthkey)
        joincol.append(monthkey)
    if (daykey is not None):
        basedaykey = daykey.split('_processedby_')[0].upper()
        df[f'TEMPORARYPARSEDATE_{daykey}'] = df[daykey].values
        daykey = f'TEMPORARYPARSEDATE_{daykey}'
        tempcol.append(daykey)
        joincol.append(daykey)

    df = convertdatetype.apply(df, yearkey=yearkey, monthkey=monthkey, daykey=daykey, drop_inconsistent=False, drop_ambiguous=False, drop_empty=False, verbose=verbose, indent=indent)
    df[tempcol] = df[tempcol].astype('string')
    if (monthkey is not None):
        isonedigit = (df[monthkey].fillna('_MISSING_').str.len()==1)
        df.loc[isonedigit,monthkey] = '0' + df.loc[isonedigit,monthkey]
    if (daykey is not None):
        isonedigit = (df[daykey].fillna('_MISSING_').str.len()==1)
        df.loc[isonedigit,daykey] = '0' + df.loc[isonedigit,daykey]

    # Exclude lines where date and year/month/day values mismatch

    tempcol.append('issue_isdatemismatch')
    df = isdatemismatch.apply(df, datekey, yearkey, *joincol, stdnan=stdnan, cvttype=False, parallel=parallel, cpu=cpu, drop_empty=False, verbose=False, indent=indent)
    isissue = (~pd.isnull(df['issue_isdatemismatch']))
    df.loc[isissue,'issue_isdatemismatch'] = df.loc[isissue,'issue_isdatemismatch'].str.replace('TEMPORARYPARSEDATE_','',case=True)
    df.loc[isissue,'issue_parsedate'] = df.loc[isissue,'issue_parsedate'].str.cat(df.loc[isissue,'issue_isdatemismatch'], sep=';', na_rep='')
    df.loc[isissue,'issue_parsedate'] = df.loc[isissue,'issue_parsedate'].str.strip(' ;')

    date2process = date2process & (pd.isnull(df['issue_isdatemismatch']) | (~df['issue_isdatemismatch'].str.contains('MISMATCH', regex=True)))

    # Exclude lines with a missing or incomplete year value

    isincomplete = (~pd.isnull(df[yearkey])) & (df[yearkey].str.len() < 4) # ambiguous year strings
    date2process = date2process & (~pd.isnull(df[yearkey])) & (~isincomplete)

    if (daykey is not None):

        # Replace the date with a missing value where the day is specified but the month is missing

        df.loc[(~pd.isnull(df[daykey])) & pd.isnull(df[monthkey]), daykey] = pd.NA

    # Assemble the date following the ISO 8601 standard

    ## Build the date from available year, month, and day values

    df.loc[date2process, datekeyout] = df.loc[date2process, yearkey].str.cat(df.loc[date2process, joincol], sep='-', na_rep='')
    df.loc[date2process, datekeyout] = df.loc[date2process, datekeyout].str.strip('- ')

    isassembled = date2process & (~pd.isnull(df[datekeyout]))
    df = modifyissuecolumn.apply(df, issuekey='issue_parsedate', issuemsg=f'{basedatekey}_ASSEMBLED', subset=isassembled)

    ## Clean columns

    df.drop(columns=tempcol, inplace=True)

    return df

@export
def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, format=None, raise_javaexception=False, inplace=False, stdnan=True, parallel=False, cpu=None, drop_empty=False, verbose=True, indent=''):

    if (yearkey is None) and (monthkey is not None):
        raise Exception(f'`parsedate.py` | `monthkey`={monthkey} but `yearkey` is None')
    if (monthkey is None) and (daykey is not None):
        raise Exception(f'`parsedate.py` | `daykey`={daykey} but `monthkey` is None')

    if parallel and cpu is None:
        cpu = len(os.sched_getaffinity(0))
    if not parallel:
        cpu = 1

    df, datekey, datekeyout = getcolumnname.apply(df, datekey, 'parsedate', inplace=inplace)
    if not inplace:
        df[datekeyout] = pd.NA

    df[datekey] = df[datekey].astype('string')
    df['issue_parsedate'] = pd.NA

    # Parse dates

    params = {
              'format': format,
              'cpu': cpu,
              'raise_javaexception': raise_javaexception,
              'verbose': verbose,
              'indent': indent
             }

    isdate = (~pd.isnull(df[datekey]))
    if any(isdate):
        datestr_index = list(isdate[isdate].index)
        df.loc[datestr_index,[datekeyout,'issue_parsedate']] = parallel_dateparser(df, datekey, datestr_index, **params)
        condition = pd.isnull(df.loc[isdate,[datekeyout,'issue_parsedate']]).all(axis=1)
        if condition.any():
            error_index = list(df[condition].index)
            raise Exception(f'`parsedate.py` | Unexpected output: both stderr and stdout are empty for line(s) {error_index}')

    # If no concatenated date is present or parsing fails,
    # construct the date from available year, month and day columns

    df = assemble_date(df, datekey, datekeyout=datekeyout, yearkey=yearkey, monthkey=monthkey, daykey=daykey, stdnan=stdnan, parallel=parallel, cpu=cpu, verbose=verbose, indent=indent)

    df['issue_parsedate'] = df['issue_parsedate'].astype('string')
    df[datekeyout] = df[datekeyout].astype('string')

    if drop_empty and pd.isnull(df['issue_parsedate']).all():
        df.drop(columns=['issue_parsedate'], inplace=True)

    printv('', verbose=verbose)

    return df
