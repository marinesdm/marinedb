# coding: utf-8

# External import

import subprocess
#import signal
import pandas as pd
import os
from joblib import Parallel, delayed
import re
import itertools
from tqdm import tqdm

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils import tqdmjoblib
from marinedb.tools import getcolumnname
from marinedb.tools.temporal import convertdatetype
from marinedb.tools.temporal import isdatemismatch

# Global variables

__all__ = [] # populated using the @export decorator

PATH = os.path.dirname(os.path.abspath(__file__))
JAR_PATH = os.path.join(PATH,'gbif-date-parser-20250214.jar')
SCRIPT_NAME = os.path.basename(__file__)[:-3]
TIMEOUT = 600 #seconds

def execute_java(multiple_datestr):

    # Execute the java command

    cmd = ['java', '-jar', JAR_PATH, multiple_datestr]

#    try:
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    p.wait(timeout=TIMEOUT)
#    except subprocess.TimeoutExpired as err:
#        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
#        raise TimeoutError(err.message)


    keys = []
    stdout = []
    for line in p.stdout:

        line = line.decode('utf-8').strip()
        nsep = line.count('=')
        if nsep==1:
            stdout.append(line)
        elif nsep==2:
            single_datestr = re.search(r'DATE=(.*)\s',line).group(1)
            single_ordering = re.search(r'ORDERING=(.*)$',line).group(1)
            keys.append((single_datestr,single_ordering))
        else:
            raise Exception(f'`parsedate.py` | unexpected output: more than two equality signs in {line}')

    stderr = []
    for line in p.stderr:
        line = line.decode('utf-8').strip()
        stderr.append(line)

    p.terminate()

    return keys, stdout, stderr

def parse_javastdout(single_stdout, single_request):

    datestr_processed = single_stdout.split('=')[1]

    if len(datestr_processed)==0:
        datestr_processed = pd.NA

    else:
        datestr_processed = datestr_processed.split()

        if len(datestr_processed)!=2:
            raise Exception(f'`parsedate.py` | unexpected output for {single_request}: stdout={single_stdout}')

        datestr_processed = [d[:10] for d in datestr_processed] # remove time details
        datestr_processed = sorted(list(set(datestr_processed)))
        datestr_processed = '/'.join(datestr_processed)

    return datestr_processed

def parse_java(multiple_datestr, datekey):

    basedatekey = datekey.split('_processedby_')[0].upper()

    # Execute the java command

    keys, stdout, stderr = execute_java(multiple_datestr)

    # Process the command output
    # format: SUCCESS:date1 date2 or ERROR:error or RAISE:error_message

    ## Capture raised errors

    for i,single_stderr in enumerate(stderr):

        single_stderr = single_stderr.split('=')

        if len(single_stderr) != 2:
            single_stderr = [err for err in single_stderr if err not in ['ERROR','RAISE']]
            raise Exception(f'`parsedate.py` | {keys[i]}: ' + '='.join(single_stderr))

        elif len(single_stderr[1]) != 0:

            stderr_type = single_stderr[0]
            stderr_message = single_stderr[1]
            if stderr_type == 'RAISE':
                raise Exception(f'`parsedate.py` | {keys[i]}: ' + stderr_message)
            # multiple error messages detected
            if len(stderr_message.split()) > 1:
                # java code flaw
                stderr_message = re.sub('RECORDED_DATE_MISMATCH','',stderr_message).strip()
            if len(stderr_message.split()) > 1:
                # Note: never encountered during testing
                stderr_message = ';'.join(stderr_message.split())
            stderr[i] = re.sub('RECORDED_DATE',f'{basedatekey}',stderr_message)

        else:
            stderr[i] = pd.NA

    ## Extract the two parsed dates

    for i,single_stdout in enumerate(stdout):

        stdout[i] = parse_javastdout(single_stdout, keys[i])

    return list(zip(stdout,stderr))

def validate_format(format):

    # Validate the ordering preference string (`format`)

    _, _, stderr = execute_java(f"('2003-06-02', '{format}')")
    stderr = stderr[0].split('=')

    if len(stderr) != 2:
        stderr = [err for err in stderr if err not in ['ERROR','RAISE']]
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

    multiple_datestr = list(zip(datesstr_list,format))
    multiple_datestr = [str(single_request) for single_request in multiple_datestr]
    multiple_datestr = ';'.join(multiple_datestr)

    return multiple_datestr

def gbif_dateparser(df, datekey, index, format=None):

    multiple_datesstr = df.loc[index,datekey].tolist()
    multiple_datestr = create_javaarg(multiple_datesstr, format=format)
    result = parse_java(multiple_datestr, datekey)

    return result

def parallel_dateparser(df, datekey, datestr_index, cpu, format=None):

    ndates = len(datestr_index)
    batch_size = 1000
    index_start = list(range(ndates))[::batch_size]
    index_end = list(range(batch_size,ndates))[::batch_size] + [ndates]
    index_slides = list(zip(index_start,index_end))

    nbatch = len(index_slides)
    cpu = min(cpu, nbatch)
    print(f'          ** parsedate | {ndates} dates to process ({nbatch} batches)')
    print(f'          INFO | {cpu} CPUs will be used')

    if cpu != 1:
        with tqdmjoblib.apply(tqdm(desc='          Progress', total=nbatch)) as progress_bar:
            parallel = Parallel(n_jobs=cpu, prefer='threads')
            # the outputs are returned in the same order as the submissions
            results = parallel(delayed(gbif_dateparser)(df, datekey, datestr_index[start:end], format=format) for start,end in index_slides)
        results = list(itertools.chain(*results))

    if cpu == 1:
        results = []
        for start,end in tqdm(index_slides,desc='          Progress'):
            results += gbif_dateparser(df, datekey, datestr_index[start:end], format=format)

    return results

def assemble_date(df, datekey, outputkey, yearkey=None, monthkey=None, daykey=None, stdnan=True, parallel=False, cpu=None):

    if (yearkey is None):
        return df

    basedatekey = datekey.split('_processedby_')[0].upper()

    print_colnames = [yearkey, monthkey, daykey]
    print_colnames = [col for col in print_colnames if col is not None]

    # Exclude lines with a missing or unlikely year value

    date2process = (pd.isnull(df[outputkey])) & (df['issue_parsedate']!=f'{basedatekey}_UNLIKELY')

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

    df = convertdatetype.apply(df, yearkey=yearkey, monthkey=monthkey, daykey=daykey, drop_inconsistent=False, drop_ambiguous=False, drop_empty=False)
    df[tempcol] = df[tempcol].astype('string')
    if (monthkey is not None):
        isonedigit = (df[monthkey].fillna('_MISSING_').str.len()==1)
        df.loc[isonedigit,monthkey] = '0' + df.loc[isonedigit,monthkey]
    if (daykey is not None):
        isonedigit = (df[daykey].fillna('_MISSING_').str.len()==1)
        df.loc[isonedigit,daykey] = '0' + df.loc[isonedigit,daykey]

    # Exclude lines where date and year/month/day values mismatch

    tempcol.append('issue_isdatemismatch')
    df = isdatemismatch.apply(df, datekey, yearkey, *joincol, stdnan=stdnan, cvttype=False, parallel=parallel, cpu=cpu, drop_empty=False)
    isissue = (~pd.isnull(df['issue_isdatemismatch']))
    df.loc[isissue,'issue_isdatemismatch'] = df.loc[isissue,'issue_isdatemismatch'].str.replace('TEMPORARYPARSEDATE_','',case=True)
    df.loc[isissue,'issue_parsedate'] = df.loc[isissue,'issue_parsedate'].str.cat(df.loc[isissue,'issue_isdatemismatch'], sep=';', na_rep='')
    df.loc[isissue,'issue_parsedate'] = df.loc[isissue,'issue_parsedate'].str.strip(' ;')

    date2process = date2process & (pd.isnull(df['issue_isdatemismatch']) | (~df['issue_isdatemismatch'].str.contains(r'MISMATCH|' + f'COMBINATION_INVALID', regex=True)))

    # Exclude lines with a missing or incomplete year value

    isincomplete = (~pd.isnull(df[yearkey])) & (df[yearkey].str.len() < 4) # ambiguous year strings
    date2process = date2process & (~pd.isnull(df[yearkey])) & (~isincomplete)

    if (daykey is not None):

        # Exclude lines where the day is specified but the month is missing

        df.loc[(~pd.isnull(df[daykey])) & pd.isnull(df[monthkey]), daykey] = pd.NA

    # Assemble the date following the ISO 8601 standard

    ## Build the date from available year, month, and day values

    print(f'          ** parsedate | date construction from {", ".join(print_colnames)} columns')
    df.loc[date2process, outputkey] = df.loc[date2process, yearkey].str.cat(df.loc[date2process, joincol], sep='-', na_rep='')
    df.loc[date2process, outputkey] = df.loc[date2process, outputkey].str.strip('- ')

    isassembled = date2process & (~pd.isnull(df[outputkey]))
    df.loc[isassembled, 'issue_parsedate'] = df.loc[isassembled, 'issue_parsedate'].fillna('') + f';{basedatekey}_ASSEMBLED'
    df.loc[isassembled, 'issue_parsedate'] = df.loc[isassembled, 'issue_parsedate'].str.strip(' ;')

    ## Clean columns

    df.drop(columns=tempcol, inplace=True)

    return df

@export
def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, format=None, inplace=False, stdnan=True, parallel=False, cpu=None):

    if (yearkey is None) and (monthkey is not None):
        raise Exception(f'`parsedate.py` | `monthkey`={monthkey} but `yearkey` is None')
    if (monthkey is None) and (daykey is not None):
        raise Exception(f'`parsedate.py` | `daykey`={daykey} but `monthkey` is None')

    if parallel and cpu is None:
        cpu=len(os.sched_getaffinity(0))
    if not parallel:
        cpu=1

    df, datekey, outputkey = getcolumnname.apply(df, datekey, SCRIPT_NAME, inplace=inplace)

    df[datekey] = df[datekey].astype('string')
    df['issue_parsedate'] = pd.NA

    # Parse dates

    isdate = (~pd.isnull(df[datekey]))
    datestr_index = list(isdate[isdate].index)
    df.loc[datestr_index,[outputkey,'issue_parsedate']] = parallel_dateparser(df, datekey, datestr_index, format=format, cpu=cpu)
    condition = pd.isnull(df.loc[isdate,[outputkey,'issue_parsedate']]).all(axis=1)
    if condition.any():
        error_index = list(df[condition].index)
        raise Exception(f'`parsedate.py` | unexpected output: both stderr and stdout are empty for line(s) {error_index}')

    # If no concatenated date is present or parsing fails,
    # construct the date from available year, month and day columns

    df = assemble_date(df, datekey, outputkey=outputkey, yearkey=yearkey, monthkey=monthkey, daykey=daykey, stdnan=stdnan, parallel=parallel, cpu=cpu)

    df['issue_parsedate'] = df['issue_parsedate'].astype('string')
    df[outputkey] = df[outputkey].astype('string')

    return df
