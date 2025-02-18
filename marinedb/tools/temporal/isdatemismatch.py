
import re
from operator import itemgetter
import pandas as pd
from joblib import Parallel, delayed
import os
from tqdm import tqdm
import itertools

from marinedb.utils import standardizenan
from marinedb.utils import tqdmjoblib
from marinedb.tools.temporal import parsedatecomponent as pdc

def _isempty(string):

    doesnotcontaindigit = re.sub(r'[^0-9]','',string)
    doesnotcontaindigit = (len(doesnotcontaindigit) == 0)

    return doesnotcontaindigit

def _isyearmismatch(datestr, yearstr):

    if not ((len(yearstr) == 2) or (len(yearstr) == 4)):
        return datestr, False

    mismatch = re.sub(yearstr, '', datestr)
    if len(mismatch) == len(datestr):

        if len(yearstr) == 2:
            return datestr, True

        mismatch = re.sub(yearstr[-2:], '', datestr, count=1)
        if len(mismatch) == len(datestr):
            return datestr, True

    return mismatch, False

def _ismonthmismatch(datestr, monthstr):

    if not ((len(monthstr) == 1) or (len(monthstr) == 2)):
        return datestr, False

    if len(monthstr) == 1:
        monthstr = "0" + monthstr

    mismatch = re.sub(monthstr, '', datestr)
    if len(mismatch) == len(datestr):
        mismatch = re.sub(monthstr[-1:], '', datestr, count=1)
        if len(mismatch) == len(datestr):
            return datestr, True

    return mismatch, False

def _isdaymismatch(datestr, daystr):

    if not ((len(daystr) == 1) or (len(daystr) == 2)):
        return datestr, False

    if len(daystr) == 1:
        daystr = "0" + daystr

    mismatch = re.sub(daystr, '', datestr)
    if len(mismatch) == len(datestr):
        mismatch = re.sub(daystr[-1:], '', datestr, count=1)
        if len(mismatch) == len(datestr):
            return datestr, True

    return mismatch, False

def ismismatch_str(datestr, yearstr=None, monthstr=None, daystr=None):

    mismatch = datestr
    doesmismatch = False

    if (yearstr is not None) and (not pd.isnull(yearstr)):
        mismatch, doesmismatch = _isyearmismatch(datestr, yearstr)
        if doesmismatch or _isempty(mismatch):
            return doesmismatch

    if (monthstr is not None) and (not pd.isnull(monthstr)):
        mismatch, doesmismatch = _ismonthmismatch(mismatch, monthstr)
        if doesmismatch or _isempty(mismatch):
            return doesmismatch

    if (daystr is not None) and (not pd.isnull(daystr)):
        mismatch, doesmismatch = _isdaymismatch(mismatch, daystr)
        if doesmismatch or _isempty(mismatch):
            return doesmismatch

    return False

def _get_mismatchissue(df, batch, paramsK, paramsV, verbose=False):

    result = []
    if verbose:
        process = tqdm(batch, desc='        Progress')
    else:
        process = batch

    for idx in process:
        params = dict(zip(paramsK, df.loc[idx,paramsV].astype('string').tolist()))
        doesmismatch = ismismatch_str(**params)
        if doesmismatch:
            result.append('RECORDED_DATE_MISMATCH')
        else:
            result.append(pd.NA)

    return result

def _create_args(df, idx, paramsK, paramsV):
    params = dict(zip(paramsK, df.loc[idx,paramsV].astype('string').tolist()))
    return params

def apply(df, datekey, yearkey, monthkey=None, daykey=None, stdnan=True, cvttype=True, parallel=False, cpu=None):
    bli=df
    if parallel and cpu is None:
        cpu = len(os.sched_getaffinity(0))
    if not parallel:
        cpu = 1

    if cpu == 1:
        parallel = False

    tempcol = []
    if stdnan or cvttype:

        # Create temporary columns to preserve the original year, month, and day values

        tempcol += ['year_temp']
        df['year_temp'] = df[yearkey].copy()
        yearkey = 'year_temp'
        if monthkey is not None:
            tempcol += ['month_temp']
            df['month_temp'] = df[monthkey].copy()
            monthkey = 'month_temp'
        if daykey is not None:
            tempcol += ['day_temp']
            df['day_temp'] = df[daykey].copy()
            dayket = 'day_temp'
    print("checkreference:",bli is df)
    params = {"datestr" : datekey, "yearstr" : yearkey, "monthstr" : monthkey, "daystr" : daykey}
    params = {key : value for key, value in params.items() if value is not None}
    paramsK = list(params.keys())
    paramsV = list(itemgetter(*paramsK)(params))

    if stdnan:
        print('        ** isdatemismatch | standardizenan')
        df = standardizenan.apply(df, key=paramsV)
    print("checkreference:",bli is df)
    if cvttype:
        print('        ** isdatemismatch | parsedatecomponent')
        df = pdc.parse_year(df, yearkey)
        if monthkey is not None:
            df = pdc.parse_month(df, monthkey)
        if daykey is not None:
            df = pdc.parse_day(df, daykey)
        print("'issue_convertdatetype':",'issue_convertdatetype' in df.columns)
    print("checkreference:",bli is df)

#    if ('issue_isdatemismatch' not in df.columns):
#        df['issue_isdatemismatch'] = pd.NA
#        df['issue_isdatemismatch'] = df['issue_isdatemismatch'].astype('string')

    isdate = list(df[~pd.isnull(df[datekey])].index)
    ndates = len(isdate)

    batch_size = 5000
    if ndates <= batch_size:
        parallel=False

    if parallel:

        index_start = list(range(ndates))[::batch_size]
        batches = [isdate[start : start + batch_size] for start in index_start]
        nbatch = len(batches)
        cpu = min(cpu, nbatch)

        print(f'        ** isdatemismatch | {ndates} lines to process ({nbatch} batches)')
        print(f'        INFO | {cpu} CPUs will be used')

        with tqdmjoblib.apply(tqdm(desc='        Progress', total=nbatch)) as progress_bar:
            results = Parallel(n_jobs=cpu)(delayed(_get_mismatchissue)(df, batch, paramsK, paramsV, verbose=False) for batch in batches)
#        with parallel_config(backend="loky", inner_max_num_threads=2):
#            results = Parallel(n_jobs=cpu)(delayed(get_mismatchissue)(_create_args(df, idx, paramsK, paramsV)) for idx in isdate)
        results = list(itertools.chain(*results))
        df.loc[isdate,'issue_isdatemismatch'] = results

    else:

        df.loc[isdate,'issue_isdatemismatch'] = _get_mismatchissue(df, isdate, paramsK, paramsV, parallel=parallel, verbose=True)

    if ('issue_convertdatetype' in df.columns):
        tempcol += ['issue_convertdatetype']
        isissue = (~pd.isnull(df['issue_convertdatetype']))
        df.loc[isissue,'issue_convertdatetype'] = df.loc[isissue,'issue_convertdatetype'].str.replace('_TEMP','')
        df.loc[isissue,'issue_isdatemismatch'] = df.loc[isissue,'issue_isdatemismatch'].str.cat(df.loc[isissue,'issue_convertdatetype'], sep=';', na_rep='')
        df.loc[isissue,'issue_isdatemismatch'] = df.loc[isissue,'issue_isdatemismatch'].str.strip(' ;')

    # Clean columns

    df.drop(columns=tempcol, inplace=True)

#    for idx in tqdm(isdate, desc='        Progress'):
#        tempparams = dict(zip(paramsK, df.loc[idx,paramsV].astype('string').tolist()))
#        doesmismatch = ismismatch_str(**tempparams)
#        if doesmismatch:
#            df.loc[idx,'issue_isdatemismatch'] = 'RECORDED_DATE_MISMATCH'

    return df

