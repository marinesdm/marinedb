# coding: utf-8

import sys
import subprocess
import pandas as pd
import os
from joblib import Parallel, delayed

PATH = os.path.dirname(os.path.abspath(__file__))
JAR_PATH = os.path.join(PATH,'gbif-date-parser-20250211.jar')

def execute_java(date_str, format=None):

    # Execute the java command

    cmd = ['java', '-jar', JAR_PATH, date_str]
    if format is not None:
        cmd.append(format)

    a = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Process the command output
    # format: SUCCESS:date1 date2 or ERROR:error or RAISE:error_message

    ## Capture raised errors

    stderr = []
    old_stderr = [] #DEBUG
    for line in a.stderr:
        line = line.decode('utf-8').strip()
        old_stderr.aooend(line) #DEBUG
        stderr_type = line.split('=')[0]
        stderr_message = line.split('=')[1]
        if stderr_type=='RAISE':
            raise Exception(stderr_message)
        stderr.append(stderr_message)

    if len(stderr)!=0:
        if len(stderr)!=1:
            print(old_stderr) #DEBUG
            raise Exception(f'Unexpected output for date={date_str}: stderr={stderr}')
        stderr = stderr[0]
    else:
        stderr = ''

    ## Extract the two parsed dates

    stdout = []
    old_stdout = [] #DEBUG
    for line in a.stdout:
        line = line.decode('utf-8').strip()
        old_stdout.append(line) #DEBUG
        stdout.append(line.split('=')[1])

    if len(stdout)!=0:
        if len(stdout)!=1:
            print(old_stdout) #DEBUG
            raise Exception(f'Unexpected output for date={date_str}: stdout={stdout}')
        stdout = stdout[0].split()
        if len(stdout)!=2:
            print(old_stdout) #DEBUG
            raise Exception(f'Unexpected output for date={date_str}: stdout={stdout}')

    a.terminate()

    if (len(stderr)==0) and (len(stdout)==0):
        raise Exception(f'Unexpected output for date={date_str}: both stderr and stdout are empty')
    #print(f'stdout: {stdout}, stderr : {stderr}')

    return stdout, stderr

def _parse_date(date_str, format=None):

    if pd.isnull(date_str):
        return [pd.NA,pd.NA]

    dates, issue = execute_java(date_str, format=format)

    if len(dates)==0:
        return [pd.NA, issue]
    else:
        return ['/'.join(list(set(dates))),pd.NA] #PROBLÈME INTERVALLE INVERSÉ


def apply(df, key, format=None, inplace=False, cpu=None):

    if cpu is None:
        cpu=len(os.sched_getaffinity(0))

    print(f'        INFO | {cpu} CPUs will be used')

    if inplace:
        colname=key
    else:
        colname=f'{key}_processedby_parsedate'

    df[key]=df[key].astype('string')
    #dfByDates = df.loc[~pd.isnull(df[key]),[key]].groupby(key)
    #unique_dates = list(dfByDates.groups.keys())
    unique_dates = list(df.loc[~pd.isnull(df[key]),key].unique())

    ndates=len(unique_dates)
    print(f'        * Standardizing date format | {ndates} unique dates')
    with Parallel(n_jobs=cpu, prefer='threads', verbose=1) as parallel:
        results = parallel(delayed(_parse_date)(date_str,format=format) for date_str in unique_dates) # order of the outputs = order of submission
#        results = parallel(delayed(_parse_date)(df.loc[idx,key],format=format) for idx in range(Ndates))
    print(results[:10])
    #df[[colname,'issue_parsedate']] = results

    df[key] = df[key].fillna('_MISSING_')
    df = df.set_index(key)
    for idx,date in enumerate(unique_dates):
        df.loc[date,[colname,'issue_parsedate']] = results[idx]
    df = df.reset_index(drop=inplace).replace('_MISSING_',pd.NA)
    df['issue_parsedate'] = df['issue_parsedate'].astype('string')

    return df


if __name__ == '__main__':

    if len(sys.argv) not in [2, 3]:
        print('Usage: python parse.py <date> [format]')
        sys.exit(1)

    if len(sys.argv) == 3:
        parse_date(sys.argv[1], sys.argv[2])
    else:
        parse_date(sys.argv[1])
