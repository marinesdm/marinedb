# coding: utf-8

# External import

import sys
import subprocess
import pandas as pd
import os
from joblib import Parallel, delayed
import math
import re
import itertools
from tqdm import tqdm

import time #DEBUG

# Internal import

from marinedb.utils import tqdmjoblib
from marinedb.tools.temporal import parsedatecomponent as pdc
from marinedb.tools.temporal import isdatemismatch

# Global variables

PATH = os.path.dirname(os.path.abspath(__file__))
JAR_PATH = os.path.join(PATH,'gbif-date-parser-20250214.jar')

def _execute_java(multiple_datestr):

    # Execute the java command

    cmd = ['java', '-jar', JAR_PATH, multiple_datestr]

    a = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    keys = []
    stdout = []
    for line in a.stdout:

        line = line.decode("utf-8").strip()
        nsep = line.count("=")
        if nsep==1:
            stdout.append(line)
        elif nsep==2:
            single_datestr = re.search(r'DATE=(.*)\s',line).group(1)
            single_ordering = re.search(r'ORDERING=(.*)$',line).group(1)
            keys.append((single_datestr,single_ordering))
        else:
            raise Exception(f'unexpected output: more than two equality signs in {line}')

    stderr = []
    for line in a.stderr:
        line = line.decode("utf-8").strip()
        stderr.append(line)

    a.terminate()

    return keys, stdout, stderr

def _parse_javastdout(single_stdout, single_request):

    datestr_processed = single_stdout.split("=")[1]

    if len(datestr_processed)==0:
        datestr_processed = pd.NA

    else:
        datestr_processed = datestr_processed.split()

        if len(datestr_processed)!=2:
            raise Exception(f'unexpected output for {single_request}: stdout={single_stdout}')

        datestr_processed = sorted(list(set(datestr_processed)))
        datestr_processed = '/'.join(datestr_processed)

    return datestr_processed

def parse_java(multiple_datestr):

    # Execute the java command

    keys, stdout, stderr = _execute_java(multiple_datestr)

    # Process the command output
    # format: SUCCESS:date1 date2 or ERROR:error or RAISE:error_message

    ## Capture raised errors

    for i,single_stderr in enumerate(stderr):

        single_stderr = single_stderr.split('=')

        if len(single_stderr[1])!=0:

            stderr_type = single_stderr[0]
            stderr_message = single_stderr[1]
            if stderr_type=='RAISE':
                raise Exception(f'{keys[i]}: ' + stderr_message)
            # multiple error messages detected
            if len(stderr_message.split()) > 1:
                # java code flaw
                stderr_message = re.sub('RECORDED_DATE_MISMATCH','',stderr_message).strip()
            if len(stderr_message.split()) > 1:
                # (never encountered during testing)
                stderr_message = ';'.join(stderr_message.split())
            stderr[i]=stderr_message

        else:
            stderr[i]=pd.NA

    ## Extract the two parsed dates

    for i,single_stdout in enumerate(stdout):

        stdout[i]=_parse_javastdout(single_stdout, keys[i])

    return list(zip(stdout,stderr))

def validate_format(format):

    # Validate the ordering format

    _, _, stderr = _execute_java(f"('2003-06-02', '{format}')")
    stderr = stderr[0].split('=')
    if stderr[0] == 'RAISE':
        raise Exception(stderr[1])

def create_javaarg(datesstr_list, format=None):

    # Validate the ordering format

    if format is None:
        format=''
    if isinstance(format, list):
        if (len(datesstr_list)!=len(format)):
            raise ValueError(f'`datesstr_list` and `format` must have the same length')
        for fmt in format:
            validate_format(fmt)
    if isinstance(format, str):
        validate_format(format)
        format = [format]*len(datesstr_list)
    if not isinstance(format, str | list):
        raise TypeError(f'`format` must be a string or a list, not a {type(format).__name__}')

    # Remove any character that holds structural significance in the Java command

    datesstr_list = pd.Series(datesstr_list).str.replace(r'[,;()"]+' + r"|'+",' ',regex=True)
    datesstr_list = datesstr_list.str.replace(r'\s+',' ',regex=True)
    datesstr_list = datesstr_list.str.strip().tolist()

    # Create the Java command

    multiple_datestr = list(zip(datesstr_list,format))
    multiple_datestr = [str(single_request) for single_request in multiple_datestr]
    multiple_datestr = ';'.join(multiple_datestr)

    return multiple_datestr

def gbif_parse_date(df, datekey, index, format=None):

    multiple_datesstr = df.loc[index,datekey].tolist()
    multiple_datestr = create_javaarg(multiple_datesstr, format=format)
    result = parse_java(multiple_datestr)

    return result

def parallel_parse_date(df, datekey, datestr_index, cpu, format=None):

    ndates = len(datestr_index)
    batch_size = 1000
    index_start = list(range(ndates))[::batch_size]
    index_end = list(range(batch_size,ndates))[::batch_size] + [ndates]
    index_slides = list(zip(index_start,index_end))

    nbatch = len(index_slides)
    cpu = min(cpu, nbatch)
    print(f'        ** parsedate | {ndates} dates to process ({nbatch} batches)')
    print(f'        INFO | {cpu} CPUs will be used')

    if cpu != 1:
        with tqdmjoblib.apply(tqdm(desc='        Progress', total=nbatch)) as progress_bar:
            parallel = Parallel(n_jobs=cpu, prefer='threads')
             # the outputs are returned in the same order as the submissions
            results = parallel(delayed(gbif_parse_date)(df, datekey, datestr_index[start:end], format=format) for start,end in index_slides)
        results = list(itertools.chain(*results))

    if cpu == 1:
        results = []
        for start,end in tqdm(index_slides):
            results += gbif_parse_date(df, datekey, datestr_index[start:end], format=format)

    return results

def assemble_date(df, datekey, storekey, yearkey=None, monthkey=None, daykey=None, stdnan=True, parallel=False, cpu=None):

    if (yearkey is None):
        return df

    date2process = (pd.isnull(df[storekey])) & (df['issue_parsedate']!='RECORDED_DATE_UNLIKELY')

    # Process year strings

    tempcol = ['year_temp']
    joincol = []
    df['year_temp'] = df[yearkey].values

    df = pdc.parse_year(df, yearkey='year_temp', drop_ambiguous=False)
    df['year_temp'] = df['year_temp'].astype('string')

    isincomplete = (~pd.isnull(df[yearkey])) & (df[yearkey].astype('string').str.len()<4)
    date2process = date2process & (~isincomplete)

    if (monthkey is not None):

        # Process month strings

        tempcol += ['month_temp']
        joincol = ['month_temp']
        df['month_temp'] = df[monthkey].values
        df = pdc.parse_month(df, 'month_temp')
        df['month_temp'] = df['month_temp'].astype('string')

        if (daykey is not None):

            # Process day strings

            tempcol += ['day_temp']
            joincol += ['day_temp']
            df['day_temp'] = df[daykey].values
            df = pdc.parse_day(df, 'day_temp')
            df['day_temp'] = df['day_temp'].astype('string')
            df.loc[(~pd.isnull(df['day_temp'])) & pd.isnull(df['month_temp']), 'day_temp'] = pd.NA

    # Assemble the date following the ISO 8601 standard

    ## Exclude lines where date and year/month/day values mismatch

    tempcol += ['issue_isdatemismatch']
    df = isdatemismatch.apply(df, datekey, 'year_temp', *joincol, stdnan=stdnan, cvttype=False, parallel=parallel, cpu=cpu)
    print()
    print(df)
    print()
    isissue = (~pd.isnull(df['issue_isdatemismatch']))
    df.loc[isissue,'issue_parsedate'] = df.loc[isissue,'issue_parsedate'].str.cat(df.loc[isissue,'issue_isdatemismatch'], sep=';', na_rep='')
    df.loc[isissue,'issue_parsedate'] = df.loc[isissue,'issue_parsedate'].str.strip(' ;')

    date2process = date2process & (pd.isnull(df['issue_isdatemismatch']) | (~df['issue_isdatemismatch'].str.contains('RECORDED_DATE_MISMATCH')))

    df.loc[date2process, storekey] = df.loc[date2process, 'year_temp'].str.cat(df.loc[date2process, joincol], sep='-', na_rep='')
    df.loc[date2process, storekey] = df.loc[date2process, storekey].str.strip('- ')

    isassembled = date2process & (~pd.isnull(df[storekey]))
    df.loc[isassembled, 'issue_parsedate'] = df.loc[isassembled, 'issue_parsedate'].fillna('') + ';DATE_ASSEMBLED'
    df.loc[isassembled, 'issue_parsedate'] = df.loc[isassembled, 'issue_parsedate'].str.strip(' ;')

    ## Clean columns

    if 'issue_convertdatetype' in df.columns:
        tempcol += ['issue_convertdatetype']
    df.drop(columns=tempcol, inplace=True)

    return df


def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, format=None, inplace=False, stdnan=True, parallel=False, cpu=None):

    if (yearkey is None) and (monthkey is not None):
        raise Exception(f'`monthkey`={monthkey} but `yearkey` is None')
    if (monthkey is None) and (daykey is not None):
        raise Exception(f'`daykey`={daykey} but `monthkey` is None')

    if parallel and cpu is None:
        cpu=len(os.sched_getaffinity(0))
    if not parallel:
        cpu=1

    if inplace:
        colname=datekey
    else:
        colname=f'{datekey}_processedby_parsedate'

    df[datekey] = df[datekey].astype('string')

    # Parse dates

    isdate = (~pd.isnull(df[datekey]))
    datestr_index = list(isdate[isdate].index)
    df.loc[datestr_index,[colname,'issue_parsedate']] = parallel_parse_date(df, datekey, datestr_index, format=format, cpu=cpu)
    print(df.loc[datestr_index,'issue_parsedate'].value_counts())
    condition = pd.isnull(df.loc[isdate,[colname,'issue_parsedate']]).all(axis=1)
    if condition.any():
        error_index = list(df[condition].index)
        raise Exception(f'unexpected output: both stderr and stdout are empty for line(s) {error_index}')

    # If no concatenated date is present or parsing fails,
    # construct the date from available year, month and day columns

    df = assemble_date(df, datekey, storekey=colname, yearkey=yearkey, monthkey=monthkey, daykey=daykey, stdnan=stdnan, parallel=parallel, cpu=cpu)

    df['issue_parsedate'] = df['issue_parsedate'].astype('string')
    df[colname] = df[colname].astype('string')

    return df
