# coding: utf-8

import sys
import subprocess
import pandas as pd
import os
from joblib import Parallel, delayed
import math
import re
import itertools

import time #DEBUG

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
            stderr[i]=stderr_message

        else:
            stderr[i]=pd.NA

    ## Extract the two parsed dates

    for i,single_stdout in enumerate(stdout):

        stdout[i]=_parse_javastdout(single_stdout, keys[i])

    return list(zip(stdout,stderr))

def validate_format(format): #TEMP ?

    _, _, stderr = _execute_java(f"('2003-06-02', '{format}')")
    stderr = stderr[0].split('=')
    if stderr[0] == 'RAISE':
        raise Exception(stderr[1])

def create_javaarg(datesstr_list, format=None):

    if format is None:
        format=''
    if isinstance(format,list):
        if (len(datesstr_list)!=len(format)):
            raise ValueError(f'`datesstr_list` and `format` must have the same length')
        for fmt in format:
            validate_format(fmt)
    if isinstance(format,str):
        validate_format(format)
        format = [format]*len(datesstr_list)
    if not isinstance(format,str | list):
        raise TypeError(f'`format` must be a string or a list, not a {type(format).__name__}')

    multiple_datestr = list(zip(datesstr_list,format))
    multiple_datestr = [str(single_request) for single_request in multiple_datestr]
    multiple_datestr = ';'.join(multiple_datestr)

    return multiple_datestr

def gbif_parse_date(df, key, index, format=None):

    multiple_datesstr = df.loc[index,key].tolist()
    multiple_datestr = create_javaarg(multiple_datesstr, format=format)
    result = parse_java(multiple_datestr)

    return result

def parallel_parse_date(df, key, datestr_index, cpu, format=None):

    ndates = len(datestr_index)
    batch_size=1000
    index_start = list(range(ndates))[::batch_size]
    index_end = list(range(batch_size,ndates))[::batch_size] + [ndates]
    index_slides = list(zip(index_start,index_end))

    with Parallel(n_jobs=cpu, prefer='threads', verbose=10) as parallel:
        results = parallel(delayed(gbif_parse_date)(df, key, datestr_index[start:end], format=format) for start,end in index_slides) # order of the outputs = order of submission

    results = list(itertools.chain(*results))

    return results

def apply(df, key, format=None, inplace=False, parallel=False, cpu=None):

    if parallel and cpu is None:
        cpu=len(os.sched_getaffinity(0))
    if not parallel:
        cpu=1

    print(f'        INFO | {cpu} CPUs will be used')

    if inplace:
        colname=key
    else:
        colname=f'{key}_processedby_parsedate'

    df[key] = df[key].astype('string')
    isdate = (~pd.isnull(df[key]))
    datestr_index = list(isdate[isdate].index)

    time_start=time.time() #DEBUG

#    ndates = len(datestr2process)
#    print(ndates) #DEBUG
#    batch_size=1000
#    nbatch = math.ceil(ndates/batch_size)
#    print(nbatch) #DEBUG
#    for batch in range(nbatch):

#        start = batch*batch_size
#        if batch==(nbatch-1):
#            end = ndates
#        else:
#            end = start + batch_size

#        index = datestr2process[start:end]
#        multiple_datesstr = df.loc[index,key].tolist()
#        multiple_datestr = create_javaarg(multiple_datesstr, format=format)

#        df.loc[index,[colname,'issue_parsedate']] = parse_java(multiple_datestr)
#        time_end=time.time() #DEBUG
#        print(f'TIME: {round(time_end - time_start,0)}s for {end} lines')

    df.loc[datestr_index,[colname,'issue_parsedate']] = parallel_parse_date(df, key, datestr_index, format=format, cpu=cpu)

    condition = pd.isnull(df.loc[isdate,[colname,'issue_parsedate']]).all(axis=1)
    if condition.any():
        error_index = list(df[condition].index)
        raise Exception(f'unexpected output: both stderr and stdout are empty for line(s) {error_index}')

    df['issue_parsedate'] = df['issue_parsedate'].astype('string')
    df[colname] = df[colname].astype('string')

    return df


if __name__ == '__main__':

    if len(sys.argv) not in [2, 3]:
        print('Usage: python parse.py <date> [format]')
        sys.exit(1)

    if len(sys.argv) == 3:
        parse_java(sys.argv[1], sys.argv[2])
    else:
        parse_java(sys.argv[1])
