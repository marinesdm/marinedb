#!/usr/bin/python
# coding: utf-8

#External import

import os
import re
import yaml
import itertools
import pandas as pd
from tqdm import tqdm
from datetime import datetime
from unidecode import unidecode
from operator import itemgetter
from joblib import Parallel, delayed
from importlib.resources import files

# Internal import

from marinedb.utils import tqdmjoblib
from marinedb.utils import standardizenan
from marinedb.utils.allexport import export
from marinedb.tools.temporal import convertdatetype

# Global variables

__all__ = [] # populated using the @export decorator

MONTH_PATH = files('marinedb.tools.data').joinpath('month.yaml')
with open(MONTH_PATH,'r') as f:
    file = yaml.safe_load(f)
    MONTH_MAPPING = file['month_mapping']

YEAR_NOW = datetime.now().year

def isempty(string):

    doesnotcontaindigit = re.sub(r'[^0-9]','',string)
    doesnotcontaindigit = (len(doesnotcontaindigit) == 0)

    return doesnotcontaindigit

def isyearmismatch(datestr, yearstr, datekey, yearkey):

    if len(yearstr) == 1:
        yearstr = '0' + yearstr

    if not ((len(yearstr) == 2) or (len(yearstr) == 4)):
        return datestr, f'{yearkey.upper()}_INVALID'

    # STEP N°1: Does `datestr` contain 4-character substrings, i.e, year-like substrings?

    yearmatchiter = re.finditer(r'(^|(?<=[^0-9]))([1-2][0-9]{3})(?=[^0-9]|$)', datestr)
    cut = [0]
    for match in yearmatchiter:
        if len(cut) != 1:
            # assumption: if one 4-character substring is a year,
            # then all 4-character substrings are years
            # remove them from the string to prevent false matches
            # as only month and day remain to be checked
            cut += [match.start(), match.end()]
        if (yearstr in match.group()) and (int(match.group()) <= YEAR_NOW):
            # year match
            cut += [match.start(), match.end()]
    cut.append(len(datestr))

    if len(cut)>2:
        mismatch = ' '.join([datestr[i:j] for i,j in zip(cut[0::2],cut[1::2])])
    else:
        mismatch = datestr

    if mismatch == datestr:

        if len(yearstr) == 4:

            # STEP N°2: Does `datestr` contain the 4-digit `yearstr`?

            mismatch = re.sub(yearstr, ' ', mismatch)

        if mismatch == datestr:

            # STEP N°3: Does `datestr` contain the 2-digit `yearstr`?

            # match `yearstr` only if it is isolated by non-numeric characters

            newyearstr = yearstr[-2:]
            mismatch = re.sub(fr'(?:^|[^0-9])({newyearstr})(?:[^0-9]|$)', ' ', mismatch, count=1)

            if mismatch == datestr:

                # match `yearstr` without requiring isolation by non-numeric characters

                yearmatch = re.search(newyearstr, mismatch)
                if yearmatch:
                    start, end = yearmatch.start(), yearmatch.end()
                    if start == 2:
                        # the first 2 characters likely represent the thousand and
                        # hundred digits of the year
                        if len(yearstr)==2:
                            mismatch = mismatch[end:]
                        else:
                            # as the 4-digit `yearstr` match failed,
                            # the 2-digit match is likely a false positive
                            # e.g. '03' from '2003' incorrectly matching '03' from '1903'
                            return datestr, f'{datekey.upper()}_{yearkey.upper()}_MISMATCH'
                    else:
                        mismatch = mismatch[:start] + mismatch[end:]
                else:
                    return datestr, f'{datekey.upper()}_{yearkey.upper()}_MISMATCH'

    return mismatch, ''

def ismonthmismatch(datestr, monthstr, datekey, monthkey):

    if not ((len(monthstr) == 1) or (len(monthstr) == 2)):
        return datestr, f'{monthkey.upper()}_INVALID'

    # STEP N°1: Does `datestr` contain the 2-digit `monthstr`?

    if (len(monthstr) == 1):
        monthstr = '0' + monthstr

    mismatch = re.sub(monthstr, ' ', datestr)
    if (mismatch == datestr):

        if (monthstr[0] == '0'):

            # STEP N°2: Does `datestr` contain the 1-digit `monthstr`?

            # match `monthstr` if it is isolated by non-numeric characters

            monthstr = monthstr[-1]
            mismatch = re.sub(fr'(?:^|[^0-9])({monthstr})(?:[^0-9]|$)', ' ', datestr, count=1)

            if (mismatch == datestr):

                # match `monthstr` without requiring isolation by non-numeric characters

                mismatch = re.sub(monthstr, ' ', datestr, count=1)
                if (mismatch == datestr):
                    return datestr, f'{datekey.upper()}_{monthkey.upper()}_MISMATCH'

        else:
            return datestr, f'{datekey.upper()}_{monthkey.upper()}_MISMATCH'

    return mismatch, ''

def isdaymismatch(datestr, daystr, datekey, daykey):

    if not ((len(daystr) == 1) or (len(daystr) == 2)):
        return datestr, f'{daykey.upper()}_INVALID'

    # STEP N°1: Does `datestr` contain the 2-digit `daystr`?

    if (len(daystr) == 1):
        daystr = '0' + daystr

    mismatch = re.sub(daystr, ' ', datestr)

    if (mismatch == datestr):

        if (daystr[0] == '0'):

            # STEP N°2: Does `datestr` contain the 1-digit `daystr`?

            # match `daystr` if it is isolated by non-numeric characters

            daystr = daystr[-1]
            mismatch = re.sub(fr'(?:^|[^0-9])({daystr})(?:[^0-9]|$)', ' ', datestr, count=1)

            if (mismatch == datestr):

                # match `daystr` without requiring isolation by non-numeric characters

                mismatch = re.sub(daystr[-1], ' ', datestr, count=1)
                if (mismatch == datestr):
                    return datestr, f'{datekey.upper()}_{daykey.upper()}_MISMATCH'

        else:
            return datestr, f'{datekey.upper()}_{daykey.upper()}_MISMATCH'

    return mismatch, ''

@export
def issingledatemismatch(datestr, datekey, yearstr, yearkey, monthstr=None, monthkey=None, daystr=None, daykey=None):

    # WARNING:
    # This code detects mismatches between a date string and year, month, or day values.
    # However, the absence of mismatches does not guarantee a correct match,
    # and some mismatches may also result from an unrecognized month names (e.g. unsupported language),
    # an unhandled date format (e.g. Unix timestamp, week based), or other limitations in the code
    # assumption:
    # - if the date string contains a month, it also includes a year
    # - if it contains a day, it also includes both a month and a year
    # The process stops if a mismatch is found. Therefore, the detected issues are not exhaustive.

    if ((monthstr is not None) and (monthkey is None)) or ((monthstr is None) and (monthkey is not None)):
        raise Exception(f'`isdatemismatch.py` | either `monthstr` or `monthkey` is None, while the other is not.')
    if ((daystr is not None) and (daykey is None)) or ((daystr is None) and (daykey is not None)):
        raise Exception(f'`isdatemismatch.py` | either `daystr` or `daykey` is None, while the other is not.')

    basedatekey = datekey.split('_processedby_')[0].upper()
    basekeys = []
    if yearkey is not None:
        baseyearkey = yearkey.split('_processedby_')[0].upper()
        basekeys.append(yearkey)
    if monthkey is not None:
        basemonthkey = monthkey.split('_processedby_')[0].upper()
        basekeys.append(monthkey)
    if daykey is not None:
        basedaykey = daykey.split('_processedby_')[0].upper()
        basekeys.append(daykey)
    basekeys = '_'.join(basekeys)

    # Process text-based date format
    # e.g. Month DD, YYYY

    try:
        datestr = datestr.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError,UnicodeEncodeError):
        pass
    datestr = unidecode(datestr.lower().strip())

    if re.search(r'[a-zA-Z]', datestr):
        # find sequences of alphabetic characters
        matchiter = re.finditer(r'[a-zA-Z]+', datestr)
        processed = False
        match = next(matchiter, -1)
        while (match != -1) and (not processed):
            try:
                # convert month names to numerical representation
                nummonth = MONTH_MAPPING[match.group()]
                datestr = datestr[:match.start()] + str(nummonth) + datestr[match.end():]
                processed = True
            except KeyError:
                # not a recognized month name
                # (e.g. unsupported language or incorrect spelling)
                match = next(matchiter, -1)
        # remove any alphabetic characters and commas
        datestr = re.sub(r'[a-zA-Z]+|,',' ',datestr)

    datestr = re.sub('\s+',' ',datestr)

    # A single date string should not exceed 10 characters
    # e.g. YYYYMMDD, YYMMDD, DD/MM/YYYY, YYYY-MM-DD, YYYY-Www, DD.MM.YYYY ...
    # Remove time details and second date from date intervals to prevent false matches

    if len(datestr) > 10:
        prefix = 'UNCERTAIN_'
    else:
        prefix = ''
    datestr = datestr[:10]

    # Check year, month, day mismatch

    mismatch = datestr
    doesmismatch = False

    ## Year mismatch
    if (yearstr is not None) and (not pd.isnull(yearstr)):
        mismatch, doesmismatch = isyearmismatch(datestr, yearstr, basedatekey, baseyearkey)
        mismatch = re.sub('\s+',' ',mismatch).strip()
        if (len(doesmismatch) != 0):
            return prefix + doesmismatch
        if isempty(mismatch):
            return doesmismatch

    ## Month mismatch
    if (monthstr is not None) and (not pd.isnull(monthstr)):
        mismatch, doesmismatch = ismonthmismatch(mismatch, monthstr, basedatekey, basemonthkey)
        mismatch = re.sub('\s+',' ',mismatch).strip()
        if (len(doesmismatch) != 0):
            return prefix + doesmismatch
        if isempty(mismatch):
            return doesmismatch

    ## Day mismatch
    if (daystr is not None) and (not pd.isnull(daystr)):
        mismatch, doesmismatch = isdaymismatch(mismatch, daystr, basedatekey, basedaykey)
        mismatch = re.sub('\s+',' ',mismatch).strip()
        if (len(doesmismatch) != 0):
            return prefix + doesmismatch
        if isempty(mismatch):
            return doesmismatch

    if (not pd.isnull(yearstr)) and (not pd.isnull(monthstr)) and (not pd.isnull(daystr)):
        # residual characters
        junkmatch = re.search(mismatch, datestr)
        if junkmatch and (junkmatch.end() == len(datestr)):
            # likely time details and additional date information
            return ''
        return f'UNCERTAIN_{basedatekey.upper()}_{basekeys.upper()}_MATCH'

    return ''

def get_mismatchissue(df, batch, paramsK, paramsV, verbose=False, indent=''):

    paramsmap = {'datestr' : 'datekey', 'yearstr' : 'yearkey', 'monthstr' : 'monthkey', 'daystr' : 'daykey'}
    paramskey = itemgetter(*paramsK)(paramsmap)
    if isinstance(paramskey,tuple):
        paramskey = list(paramskey)
    else:
        paramskey = [paramskey]
    paramskey = dict(zip(paramskey,paramsV))

    result = []
    if verbose:
        process = tqdm(batch, desc=indent + 'Progress')
    else:
        process = batch

    for idx in process:
        params = dict(zip(paramsK, df.loc[idx,paramsV].astype('string').values.tolist()))
        doesmismatch = issingledatemismatch(**params, **paramskey)
        if len(doesmismatch) == 0:
            doesmismatch = pd.NA
        result.append(doesmismatch)

    return result

#def create_args(df, idx, paramsK, paramsV):
#
#    params = dict(zip(paramsK, df.loc[idx,paramsV].astype('string').values.tolist()))
#
#    return params

@export
def apply(df, datekey, yearkey, monthkey=None, daykey=None, stdnan=True, cvttype=True, parallel=False, cpu=None, drop_empty=False, indent=''):

    # WARNING:
    # This code detects mismatches between a date string and year, month, and/or day values.
    # However:
    # - the absence of mismatches does not guarantee a correct match (e.g. "2025-01-02" & "2025-02-01" both match "2025"/"02"/"01"),
    # - some mismatches may also result from an unrecognized month names (e.g. unsupported language),
    #   an unhandled date format (e.g. Unix timestamp, week based), or other limitations in the code
    # Thus, the output of this code should be interpreted as a weak signal of a mismatch

    if parallel and cpu is None:
        cpu = len(os.sched_getaffinity(0))
    if not parallel:
        cpu = 1

    if cpu == 1:
        parallel = False

    dropcolumns = []
    if stdnan or cvttype:

        # Create temporary columns to preserve the original year, month, and day values

        dropcolumns += [f'TEMPORARYISDATEMISMATCH_{yearkey}']
        df[f'TEMPORARYISDATEMISMATCH_{yearkey}'] = df[yearkey].copy()
        yearkey = f'TEMPORARYISDATEMISMATCH_{yearkey}'
        if monthkey is not None:
            dropcolumns += [f'TEMPORARYISDATEMISMATCH_{monthkey}']
            df[f'TEMPORARYISDATEMISMATCH_{monthkey}'] = df[monthkey].copy()
            monthkey = f'TEMPORARYISDATEMISMATCH_{monthkey}'
        if daykey is not None:
            dropcolumns += [f'TEMPORARYISDATEMISMATCH_{daykey}']
            df[f'TEMPORARYISDATEMISMATCH_{daykey}'] = df[daykey].copy()
            daykey = f'TEMPORARYISDATEMISMATCH_{daykey}'

    params = {'datestr' : datekey, 'yearstr' : yearkey, 'monthstr' : monthkey, 'daystr' : daykey}
    params = {key : value for key, value in params.items() if value is not None}
    paramsK = list(params.keys())
    paramsV = itemgetter(*paramsK)(params)
    if isinstance(paramsV, tuple):
        paramsV = list(paramsV)
    else:
        paramsV = [paramsV]

    if stdnan:
        # prevent mismatches caused by unrecognized missing values
        print(indent + '** isdatemismatch | standardizenan')
        df = standardizenan.apply(df, key=paramsV)

    if cvttype:
        # prevent mismatches caused by invalid year/month/day strings
        print(indent + '** isdatemismatch | convertdatetype')
        df = convertdatetype.apply(df, yearkey=yearkey, monthkey=monthkey, daykey=daykey, drop_inconsistent=False, drop_ambiguous=False, drop_empty=drop_empty, indent=indent)

    # Check for mismatches between the date string and the year, month, or day strings

    df['issue_isdatemismatch'] = pd.NA
    isdateindex = list(df[~pd.isnull(df[datekey])].index)
    ndates = len(isdateindex)
    batch_size = 5000
    if ndates <= batch_size:
        parallel = False

    if parallel:

        index_start = list(range(ndates))[::batch_size]
        batches = [isdateindex[start : start + batch_size] for start in index_start]
        nbatch = len(batches)
        cpu = min(cpu, nbatch)

        print(indent + f'** isdatemismatch | {ndates} lines to process ({nbatch} batches)')
        print(indent + f'INFO | {cpu} CPUs will be used')

        with tqdmjoblib.apply(tqdm(desc=indent + 'Progress', total=nbatch)) as progress_bar:
            results = Parallel(n_jobs=cpu)(delayed(get_mismatchissue)(df, batch, paramsK, paramsV, verbose=False, indent=indent) for batch in batches)
        results = list(itertools.chain(*results))

        df.loc[isdateindex,'issue_isdatemismatch'] = results

    else:
        df.loc[isdateindex,'issue_isdatemismatch'] = get_mismatchissue(df, isdateindex, paramsK, paramsV, verbose=True, indent=indent)

    # Clean columns

    if ('issue_convertdatetype' in df.columns):

        dropcolumns += ['issue_convertdatetype']
        isissue = (~pd.isnull(df['issue_convertdatetype']))
        df.loc[isissue,'issue_isdatemismatch'] = df.loc[isissue,'issue_isdatemismatch'].str.cat(df.loc[isissue,'issue_convertdatetype'], sep=';', na_rep='')
        df.loc[isissue,'issue_isdatemismatch'] = df.loc[isissue,'issue_isdatemismatch'].str.strip(' ;')

    if stdnan or cvttype:
        df['issue_isdatemismatch'] = df['issue_isdatemismatch'].str.replace(r'TEMPORARYISDATEMISMATCH_','',case=True)

    df['issue_isdatemismatch'] = df['issue_isdatemismatch'].astype('string')

    if drop_empty and pd.isnull(df['issue_isdatemismatch']).all():
        dropcolumns += ['issue_isdatemismatch']

    df.drop(columns=dropcolumns, inplace=True)

    return df

