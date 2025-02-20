
import re
from operator import itemgetter
import pandas as pd
from joblib import Parallel, delayed
import os
from tqdm import tqdm
import itertools
from unidecode import unidecode
import yaml
from datetime import datetime

from marinedb.utils import standardizenan
from marinedb.utils import tqdmjoblib
from marinedb.tools.temporal import parsedatecomponent as pdc

PATH = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(PATH,'month.yaml'),'r') as f:
    file = yaml.safe_load(f)
    MONTH_MAPPING = file['month_mapping']

YEAR_NOW = datetime.now().year

def _isempty(string):

    doesnotcontaindigit = re.sub(r'[^0-9]','',string)
    doesnotcontaindigit = (len(doesnotcontaindigit) == 0)

    return doesnotcontaindigit

def _isyearmismatch(datestr, yearstr):

    if len(yearstr) == 1:
        yearstr = '0' + yearstr

    if not ((len(yearstr) == 2) or (len(yearstr) == 4)):
        return datestr, 'YEAR_INVALID'

    # STEP N°1: Does `datestr` contain 4-character substrings, i.e, year substrings?

    yearmatchiter = re.finditer(r'(^|(?<=[^0-9]))([1-2][0-9]{3})(?=[^0-9]|$)', datestr)
    cut = [0]
    for match in yearmatchiter:
        if len(cut) != 1:
            # assumption: if one 4-character substring is a year,
            # then all 4-character substrings are years
            # remove them from the string to prevent false matches,
            # as only month and day remain to be checked
            cut += [match.start(), match.end()]
        if (yearstr in match.group()) and (int(match.group())<=YEAR_NOW):
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
                            print('error!!')
                            return datestr, 'RECORDED_DATE_MISMATCH'
                    else:
                        mismatch = mismatch[:start] + mismatch[end:]
                else:
                    return datestr, 'RECORDED_DATE_MISMATCH'

    return mismatch, ''

def _ismonthmismatch(datestr, monthstr):

    if not ((len(monthstr) == 1) or (len(monthstr) == 2)):
        return datestr, 'MONTH_INVALID'

    # STEP N°1: Does `datestr` contain the 2-digit `monthstr`?

    if len(monthstr) == 1:
        monthstr = '0' + monthstr

    mismatch = re.sub(monthstr, ' ', datestr)
    if mismatch == datestr:

        if monthstr[0] == '0':

            # STEP N°2: Does `datestr` contain the 1-digit `monthstr`?

            # match `monthstr` if it is isolated by non-numeric characters

            monthstr = monthstr[-1]
            mismatch = re.sub(fr'(?:^|[^0-9])({monthstr})(?:[^0-9]|$)', ' ', datestr, count=1)

            if mismatch == datestr:

                # match `monthstr` without requiring isolation by non-numeric characters

                mismatch = re.sub(monthstr, ' ', datestr, count=1)
                if mismatch == datestr:
                    return datestr, 'RECORDED_DATE_MISMATCH'

        else:
            return datestr, 'RECORDED_DATE_MISMATCH'

    return mismatch, ''

def _isdaymismatch(datestr, daystr):

    if not ((len(daystr) == 1) or (len(daystr) == 2)):
        return datestr, 'DAY_INVALID'

    # STEP N°1: Does `datestr` contain the 2-digit `daystr`?

    if len(daystr) == 1:
        daystr = '0' + daystr

    mismatch = re.sub(daystr, ' ', datestr)

    if (mismatch == datestr):

        if (daystr[0] == '0'):

            # STEP N°2: Does `datestr` contain the 1-digit `daystr`?

            # match `daystr` if it is isolated by non-numeric characters

            daystr = daystr[-1]
            mismatch = re.sub(fr'(?:^|[^0-9])({daystr})(?:[^0-9]|$)', ' ', datestr, count=1)

            if mismatch == datestr:

                # match `daystr` without requiring isolation by non-numeric characters

                mismatch = re.sub(daystr[-1], ' ', datestr, count=1)
                if mismatch == datestr:
                    return datestr, 'RECORDED_DATE_MISMATCH'

        else:
            return datestr, 'RECORDED_DATE_MISMATCH'

    return mismatch, ''

def ismismatch_str(datestr, yearstr=None, monthstr=None, daystr=None):
    print('key:',datestr,yearstr,monthstr,daystr)
    # WARNING:
    # This code detects mismatches between a date string and year, month, and/or day values.
    # However, the absence of mismatches does not guarantee a correct match,
    # and some mismatches may also result from an unrecognized month names (e.g. unsupported language),
    # an unhandled date format (e.g. Unix timestamp, week based), or other limitations in the code
    # assumption:
    # - if the date string contains a month, it also includes a year
    # - if it contains a day, it also includes both a month and a year
    # (this assumption leads to failures when the month name is unrecognized)

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
        while (match!=-1) and (not processed):
            try:
                # convert month names to numerical representation
                nummonth = MONTH_MAPPING[match.group()]
                datestr = datestr[:match.start()] + str(nummonth) + datestr[match.end():]
                processed = True
            except KeyError:
                # text that is not a recognized month name
                # (e.g. unsupported language or incorrect spelling)
                match = next(matchiter, -1)
        # remove any alphabetic characters and commas
        datestr = re.sub(r'[a-zA-Z]+|,',' ',datestr)

    datestr = re.sub('\s+',' ',datestr)

    # A single date string should not exceed 10 characters
    # e.g. YYYYMMDD, YYMMDD, DD/MM/YYYY, YYYY-MM-DD, YYYY-Www, DD.MM.YYYY ...
    # Remove time details and second date from date intervals to prevent false matches

    if len(datestr) > 10:
        print('uncertain',datestr)
        prefix = 'UNCERTAIN_'
    else:
        print('no')
        prefix = ''
    datestr = datestr[:10]

    # Check year, month, day mismatch

    mismatch = datestr
    doesmismatch = False

    ## Year mismatch
    if (yearstr is not None) and (not pd.isnull(yearstr)):
        mismatch, doesmismatch = _isyearmismatch(datestr, yearstr)
        mismatch = re.sub('\s+',' ',mismatch).strip()
        print('mismatch:',mismatch,doesmismatch)
        if (len(doesmismatch) != 0):
            return prefix + doesmismatch
        if _isempty(mismatch):
            return doesmismatch

    ## Month mismatch
    if (monthstr is not None) and (not pd.isnull(monthstr)):
        mismatch, doesmismatch = _ismonthmismatch(mismatch, monthstr)
        mismatch = re.sub('\s+',' ',mismatch).strip()
        print('mismatch:',mismatch,doesmismatch)
#        if (len(doesmismatch) != 0) or _isempty(mismatch):
#            return prefix + doesmismatch
        if (len(doesmismatch) != 0):
            return prefix + doesmismatch
        if _isempty(mismatch):
            return doesmismatch


    ## Day mismatch
    if (daystr is not None) and (not pd.isnull(daystr)):
        mismatch, doesmismatch = _isdaymismatch(mismatch, daystr)
        mismatch = re.sub('\s+',' ',mismatch).strip()
        print('mismatch:',mismatch,doesmismatch)
#        if (len(doesmismatch) != 0) or _isempty(mismatch):
#            return prefix + doesmismatch
        if (len(doesmismatch) != 0):
            return prefix + doesmismatch
        if _isempty(mismatch):
            return doesmismatch


    if (not pd.isnull(yearstr)) and (not pd.isnull(monthstr)) and (not pd.isnull(daystr)):
        # residual characters
        junkmatch = re.search(mismatch, datestr)
        if junkmatch and (junkmatch.end() == len(datestr)):
            # likely time details and additional date information
            return ''
        return 'UNCERTAIN_RECORDED_DATE_MATCH'

    return ''

def _get_mismatchissue(df, batch, paramsK, paramsV, verbose=False):

    result = []
    if verbose:
        process = tqdm(batch, desc='        Progress')
    else:
        process = batch

    for idx in process:
        params = dict(zip(paramsK, df.loc[idx,paramsV].astype('string').tolist()))
        doesmismatch = ismismatch_str(**params)
        if len(doesmismatch)==0:
            doesmismatch = pd.NA
        result.append(doesmismatch)

    return result

def _create_args(df, idx, paramsK, paramsV):
    params = dict(zip(paramsK, df.loc[idx,paramsV].astype('string').tolist()))
    return params

def apply(df, datekey, yearkey, monthkey=None, daykey=None, stdnan=True, cvttype=True, parallel=False, cpu=None):

    # WARNING:
    # This code detects mismatches between a date string and year, month, and/or day values.
    # However, the absence of mismatches does not guarantee a correct match,
    # and some mismatches may also result from an unrecognized month names (e.g. unsupported language),
    # an unhandled date format (e.g. Unix timestamp, week based), or other limitations in the code
    # Thus, the output of this code should be interpreted as a weak signal of a mismatch

    if parallel and cpu is None:
        cpu = len(os.sched_getaffinity(0))
    if not parallel:
        cpu = 1

    if cpu == 1:
        parallel = False

    tempcol = []
    if stdnan or cvttype:

        # Create temporary columns to preserve the original year, month, and day values

        tempcol += [f'{yearkey}_temp']
        df[f'{yearkey}_temp'] = df[yearkey].copy()
        yearkey = f'{yearkey}_temp'
        if monthkey is not None:
            tempcol += [f'{monthkey}_temp']
            df[f'{monthkey}_temp'] = df[monthkey].copy()
            monthkey = f'{monthkey}_temp'
        if daykey is not None:
            tempcol += [f'{daykey}_temp']
            df[f'{daykey}_temp'] = df[daykey].copy()
            daykey = f'{daykey}_temp'

    params = {"datestr" : datekey, "yearstr" : yearkey, "monthstr" : monthkey, "daystr" : daykey}
    #print(params)
    params = {key : value for key, value in params.items() if value is not None}
    paramsK = list(params.keys())
    paramsV = list(itemgetter(*paramsK)(params))

    if stdnan:
        print('        ** isdatemismatch | standardizenan')
        df = standardizenan.apply(df, key=paramsV)

    if cvttype:
        print('        ** isdatemismatch | parsedatecomponent')
        df = pdc.parse_year(df, yearkey)
        #print(df)
        if monthkey is not None:
            df = pdc.parse_month(df, monthkey)
        if daykey is not None:
            df = pdc.parse_day(df, daykey)
        #print(df)

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
        results = list(itertools.chain(*results))

        df.loc[isdate,'issue_isdatemismatch'] = results

    else:
        df.loc[isdate,'issue_isdatemismatch'] = _get_mismatchissue(df, isdate, paramsK, paramsV, verbose=True)

    if ('issue_convertdatetype' in df.columns):
        tempcol += ['issue_convertdatetype']
        isissue = (~pd.isnull(df['issue_convertdatetype']))
        df.loc[isissue,'issue_convertdatetype'] = df.loc[isissue,'issue_convertdatetype'].str.replace('_TEMP','')
        df.loc[isissue,'issue_isdatemismatch'] = df.loc[isissue,'issue_isdatemismatch'].str.cat(df.loc[isissue,'issue_convertdatetype'], sep=';', na_rep='')
        df.loc[isissue,'issue_isdatemismatch'] = df.loc[isissue,'issue_isdatemismatch'].str.strip(' ;')

    # Clean columns

    df.drop(columns=tempcol, inplace=True)
    df['issue_isdatemismatch'] = df['issue_isdatemismatch'].astype('string')

    return df

