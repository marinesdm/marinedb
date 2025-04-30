#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
import os
import re

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname, modifyissuecolumn
from marinedb.tools.temporal import convertdatetype
from marinedb.tools.temporal import processdateinterval

# Global variable

__all__ = [] # populated using the @export decorator


def get_basekey(key, columns):

    basekey = key.split('_processedby_')[0]
    if ('generatedby' in basekey):
        basekey = basekey.split('_generatedby_')[0]
        columns = [col.split('_processedby_')[0] for col in columns]
        if basekey in columns:
            basekey += '-GEN'
    basekey = basekey.upper()

    return basekey

def clean(df, yearkey, monthkey, daykey, issuekey, split, dropcolumns=None, drop_empty=True, verbose=True, indent=''):

    # Drop columns

    if dropcolumns is None:
        dropcolumns = []

    if drop_empty:
        printv(f'INFO | Only non-empty generated columns will be returned', verbose=verbose, indent=indent)
        # i.e., the dataframe can be returned as is
        if pd.isnull(df[yearkey]).all():
            dropcolumns += [yearkey]
        if pd.isnull(df[monthkey]).all():
            dropcolumns += [monthkey]
        if pd.isnull(df[daykey]).all():
            dropcolumns += [daykey]
        if pd.isnull(df[issuekey]).all():
            dropcolumns += [issuekey]

    df.drop(columns=dropcolumns, inplace=True)

    # Convert dtypes

    try:

        df[yearkey] = df[yearkey].astype('Int64')
        df[monthkey] = df[monthkey].astype('Int64')
        df[daykey] = df[daykey].astype('Int64')

    except ValueError as error:

        if split == 'interval':
            printv(f"INFO | Failed to convert `{yearkey}`, `{monthkey}` and `{daykey}` to integers (type='{split}'). Converting to strings instead.", verbose=verbose, indent=indent)
            df[yearkey] = df[yearkey].astype('string')
            df[monthkey] = df[monthkey].astype('string')
            df[daykey] = df[daykey].astype('string')
        else:
            raise ValueError('`splitdate.py` | ' + error)

    issuekeys = [col for col in df.columns if 'issue' in col]
    df[issuekeys] = df[issuekeys].astype('string')

    return df

def call_processdateinterval(df, datekey, drop_interval, strategy='overlap', maxinterval_number=1, maxinterval_level='years', verbose=True, indent=''):
    print('column:', df.columns)
    # Warning :
    # If the function is applied to a DataFrame that lacks 'flag_{basedatekey}_dateinterval' column,
    # `processdateinterval.py` will be executed, regardless of whether date intervals have already been processed

    basedatekey = datekey.split('_processedby_')[0]
    print('basedatekey:',basedatekey)
    # Check if the `datekey` column has already been processed by `processdateinterval`

    flagname = f'flag_{basedatekey}_isdateinterval'
    if ('processdateinterval' in datekey) and (flagname not in df.columns):

        # The column has already been processed by `processdateinterval`
        # but `processdateinterval` has been called with flag=False

        ## Has the column version preceding `processdateinterval` been retained?

        modulenames = datekey.split('_processedby_')[1].split('_')
        stop_index = modulenames.index('processdateinterval')
        if stop_index > 0:
            previouscolumnversion = basedatekey + '_processedby_' + '_'.join(modulenames[:stop_index])
        else:
            previouscolumnversion = basedatekey
        print('previous',previouscolumnversion)
        if previouscolumnversion in df.columns:
            ## Identify date intervals from the column version prior to `processdateinterval`
            df[flagname] = processdateinterval.isdateinterval(df, previouscolumnversion)
            print('HERE') #debug
        else:
            print('ICICICI')
            ## No remaining date intervals, with no way to determine prior existence
            df[flagname] = False

    if flagname not in df.columns:
        print('ICI') #debug
        # Process date intervals

        printv(f'* Apply `processdateinterval` to {basedatekey}', verbose=verbose, indent=indent)

        df = processdateinterval.apply(df, datekey, drop_interval=drop_interval, strategy=strategy, maxinterval_number=maxinterval_number, maxinterval_level=maxinterval_level, inplace=False, flag=True, verbose=verbose, indent=indent + '  ')

    # Column name for futher processing

    colstart = f'{basedatekey}_processedby'
    datekeyin = [col for col in df.columns if (col[:len(colstart)] == colstart) and ('processdateinterval' in col)]
    if len(datekeyin) > 1:
        raise Exception(f"`splitdate.py` | Mutiple column names contain '{colstart}' and 'processdateinterval': {datekeyin}. An issue may have occurred during execution.")
    elif len(datekeyin) == 1:
        datekeyin = datekeyin[0]
    else:
        # `processdateinterval` has been called with inplace=True
        datekeyin = datekey

    printv('', verbose=verbose)
    print('column:', df.columns) #debug
    return df, datekeyin

@export
def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, split='all', drop_interval=False, drop_mismatch=True, drop_empty=False, inplace=False, flag=True, strategy='overlap', maxinterval_number=1, maxinterval_level='years', verbose=True, indent=''):

    # Verifications

    if split not in ['all','interval']:
        raise ValueError(f"`splitdate.py` | `split` must be 'all' or 'interval'")

    if (monthkey is not None) and (yearkey is None):
        raise Exception(f"`splitdate.py` | yearkey={yearkey} but monthkey='{monthkey}'. Please assign a value to `yearkey` or set `monthkey` to None.")
    if (daykey is not None) and (monthkey is None):
        raise Exception(f"`splitdate.py` | monthkey={monthkey} but daykey='{daykey}'. Please assign a value to `monthkey` or set `daykey` to None.")

    # Set up

    columns = list(df.columns)
    yearmodulename = 'splitdate'
    monthmodulename = 'splitdate'
    daymodulename = 'splitdate'
    yearinplace = inplace
    monthinplace = inplace
    dayinplace = inplace

    if (yearkey is None):
        yearkey = 'year_generatedby_splitdate'
        yearmodulename = ''
        yearinplace = True
        keyin = [col for col in columns if yearkey in col]
        doeskeyexist = (len(keyin) > 0)
        if doeskeyexist:
            raise Exception(f'`splitdate.py` | {yearkey} found in {",".join(keyin)} columns')
    if (monthkey is None):
        monthkey = 'month_generatedby_splitdate'
        monthmodulename = ''
        monthinplace = True
        keyin = [col for col in columns if monthkey in col]
        doeskeyexist = (len(keyin) > 0)
        if doeskeyexist:
            raise Exception(f'`splitdate.py` | {monthkey} found in {",".join(keyin)} columns')
    if (daykey is None):
        daykey = 'day_generatedby_splitdate'
        daymodulename = ''
        dayinplace = True
        keyin = [col for col in columns if daykey in col]
        doeskeyexist = (len(keyin) > 0)
        if doeskeyexist:
            raise Exception(f'`splitdate.py` | {daykey} found in {",".join(keyin)} columns')
    print(yearkey,monthkey, daykey) #debug
    df, datekey, _ = getcolumnname.apply(df, datekey, '', inplace=True)
    df, yearkey, yearkeyout = getcolumnname.apply(df, yearkey, yearmodulename, inplace=yearinplace)
    df, monthkey, monthkeyout = getcolumnname.apply(df, monthkey, monthmodulename, inplace=monthinplace)
    df, daykey, daykeyout = getcolumnname.apply(df, daykey, daymodulename, inplace=dayinplace)
    print(yearkey,monthkey, daykey) #debug
    print(yearkeyout,monthkeyout, daykeyout) #debug
    issuekey = ('issue_splitdate' if (split == 'all') else 'issue_splitdateinterval')
    df[issuekey] = pd.NA
    columns = list(df.columns)

    processdateinterval_params = {
                                  'drop_interval': drop_interval,
                                  'strategy': strategy,
                                  'maxinterval_number': maxinterval_number,
                                  'maxinterval_level': maxinterval_level
                                  }

    df, datekey = call_processdateinterval(df, datekey, **processdateinterval_params, verbose=verbose, indent=indent)
    print(df.columns) #debug
    printv(f'* Split into year/month/day when known', verbose=verbose, indent=indent)

    baseyearkey = get_basekey(yearkey, columns)
    basemonthkey = get_basekey(monthkey, columns)
    basedaykey = get_basekey(daykey, columns)
    basedatekey = datekey.split('_processedby_')[0]

    flagcolumn = f'flag_{basedatekey}_isdateinterval'
    assert (flagcolumn in df.columns)
    intervalcolumns = list(set(df.columns) - set(columns))
    intervalcolumns = [col for col in intervalcolumns if ('issue_' not in col)]

#    flagcolumn = [col for col in intervalcolumns if ('flag_' in col)]
#    flagcolumn = flagcolumn[0]
    print('intervalcolumns:',intervalcolumns)
    # Select the dates to process
    # split='all': all dates
    # split='interval': date intervals only

    if split == 'interval':
        process = df[flagcolumn]
    else:
        process = pd.Series([True]*len(df))

    # Prepare the columns for storing results
    # inplace=True: replace `yearkey`/`monthkey`/`daykey` if the columns already exist
    # inplace=False: create new columns to avoid overwriting data in existing columns

    isyear = (yearkey in columns)
    ismonth = (monthkey in columns)
    isday = (daykey in columns)
    print(isyear, ismonth, isday)

    ## Preprocess and store available year, month, and day values

    if isyear:

        convertdf = convertdatetype.apply(df.copy(), yearkey=yearkey, monthkey=monthkey, daykey=daykey, drop_inconsistent=False, drop_ambiguous=False, drop_empty=False, verbose=False, indent=indent)

        year = convertdf[yearkey].astype('string').copy()
        isonedigit = (year.astype('string').str.len() == 1)
        year[isonedigit] = '0' + year[isonedigit]

        if ismonth:

            month = convertdf[monthkey].astype('string').copy()
            isonedigit = (month.astype('string').str.len() == 1)
            month[isonedigit] = '0' + month[isonedigit]

        if isday:

            day = convertdf[daykey].astype('string').copy()
            isonedigit = (day.astype('string').str.len() == 1)
            day[isonedigit] = '0' + day[isonedigit]

        del convertdf

    ## Initialize the output columns


    if not isyear:
        df[yearkeyout] = pd.NA
    if not ismonth:
        df[monthkeyout] = pd.NA
    if not isday:
        df[daykeyout] = pd.NA

    if isday or ismonth or isyear:

        if inplace:

            print_columns = np.array([f"`{daykey.split('_processedby_')[0]}`", f"`{monthkey.split('_processedby_')[0]}`", f"`{yearkey.split('_processedby_')[0]}`"])[[isday, ismonth, isyear]]
            if split == 'all':
#                printv(f"WARNING | `{daykey.split('_processedby_')[0]}`, `{monthkey.split('_processedby_')[0]}` and/or `{yearkey.split('_processedby_')[0]}` columns already exist and will be overwritten", verbose=verbose, indent=indent)
                printv(f"WARNING | {', '.join(print_columns)} column(s) already exist(s) and will be overwritten", verbose=verbose, indent=indent)
            if split == 'interval':
#                printv(f"WARNING | `{daykey.split('_processedby_')[0]}`, `{monthkey.split('_processedby_')[0]}` and/or `{yearkey.split('_processedby_')[0]}` columns already exist and will be overwritten for date intervals", verbose=verbose, indent=indent)
                printv(f"WARNING | {', '.join(print_columns)} column(s) already exist(s) and will be overwritten for date intervals", verbose=verbose, indent=indent)

        else:

            if isyear:
                df[yearkeyout] = df[yearkey].copy()
            if ismonth:
                df[monthkeyout] = df[monthkey].copy()
            if isday:
                df[daykeyout] = df[daykey].copy()

    df[yearkeyout] = df[yearkeyout].astype('string')
    df[monthkeyout] = df[monthkeyout].astype('string')
    df[daykeyout] = df[daykeyout].astype('string')

    isoutputcolumnsgenerated = (not inplace) or ((not isday) and (not ismonth) and (not isyear))
    drop_empty = (drop_empty and isoutputcolumnsgenerated)

    printv(f"INFO | daykey='{daykeyout}', monthkey='{monthkeyout}', yearkey='{yearkeyout}'", verbose=verbose, indent=indent)

    if (split == 'interval') and (~df[flagcolumn]).all():

        # No date interval

        printv(f"INFO | split='{split}', but no date intervals were found", verbose=verbose, indent=indent)

        if flag:
            dropcolumns = None
        else:
            dropcolumns = intervalcolumns

        df = clean(df, yearkeyout, monthkeyout, daykeyout, issuekey, split, dropcolumns=dropcolumns, drop_empty=drop_empty, verbose=verbose, indent=indent)

        return df

    if (split == 'interval') and drop_interval:

        # Replace year, month and day values with NaN for interval dates

        if isyear:
            df.loc[process,yearkeyout] = pd.NA
        if ismonth:
            df.loc[process,monthkeyout] = pd.NA
        if isday:
            df.loc[process,daykeyout] = pd.NA

        # Clean

        if flag:
            dropcolumns = None
        else:
            dropcolumns = intervalcolumns

        df = clean(df, yearkeyout, monthkeyout, daykeyout, issuekey, split, dropcolumns=dropcolumns, drop_empty=drop_empty, verbose=verbose, indent=indent)

        return df

    # Split date into year, month & day

    date_split = df.loc[process,datekey].str.split('-')

    df.loc[process,yearkeyout] = date_split.str[0][process].astype('string').values
    df.loc[process,monthkeyout] = date_split.str[1][process].astype('string').values
    df.loc[process,daykeyout] = date_split.str[2][process].astype('string').values

    # Handle date intervals

    if drop_interval:
        df.loc[df[flagcolumn],yearkeyout] = pd.NA
        df.loc[df[flagcolumn],monthkeyout] = pd.NA
        df.loc[df[flagcolumn],daykeyout] = pd.NA

    df[yearkeyout] = df[yearkeyout].astype('string')
    df[monthkeyout] = df[monthkeyout].astype('string')
    df[daykeyout] = df[daykeyout].astype('string')

    # Replace mismatched year, month, or day values with NaN

    if isyear:
        ismissing = (pd.isnull(df[yearkeyout]) | pd.isnull(year))
        isfourdigit = (year.str.len() == 4)
        # four-digit years
        condition = (~ismissing) & isfourdigit & process
        isyearmismatch = (df.loc[condition,yearkeyout] != year[condition])
        isyearmismatch = list(isyearmismatch[isyearmismatch].index)
        # one-digit years or two-digit years
        condition = (~ismissing) & (~isfourdigit) & process
        refyear = year[condition].astype('string')
        mapindex = list(refyear.index)
        isyearmismatch += [mapindex[idx] for idx,y in enumerate(refyear) if (y != df.loc[mapindex[idx],yearkeyout][-2:])]
        df = modifyissuecolumn.apply(df, issuekey, f'{baseyearkey}_MISMATCH', subset=isyearmismatch)

    if ismonth:
        ismissing = (pd.isnull(df[monthkeyout]) | pd.isnull(month))
        ismonthmismatch = (df.loc[(~ismissing) & process,monthkeyout] != month[(~ismissing) & process])
        ismonthmismatch = ismonthmismatch[ismonthmismatch].index
        df = modifyissuecolumn.apply(df, issuekey, f'{basemonthkey}_MISMATCH', subset=ismonthmismatch)

    if isday:
        ismissing = (pd.isnull(df[daykeyout]) | pd.isnull(day))
        isdaymismatch = (df.loc[(~ismissing) & process,daykeyout] != day[(~ismissing) & process])
        isdaymismatch = isdaymismatch[isdaymismatch].index
        df = modifyissuecolumn.apply(df, issuekey, f'{basedaykey}_MISMATCH', subset=isdaymismatch)

    if drop_mismatch:
        if isyear:
            df.loc[isyearmismatch,[yearkeyout,monthkeyout,daykeyout]] = pd.NA
        if ismonth:
            df.loc[ismonthmismatch,[monthkeyout,daykeyout]] = pd.NA
        if isday:
            df.loc[isdaymismatch,daykeyout] = pd.NA

    # Ensure hierarchical consistency:
    # - if year is missing, set month and day to NaN
    # - if month is missing, set day to NaN

    df.loc[process & pd.isnull(df[yearkeyout]),[monthkeyout,daykeyout]] = pd.NA
    df.loc[process & pd.isnull(df[monthkeyout]),daykeyout] = pd.NA

    # Clean

    if flag:
        dropcolumns = None
    else:
        dropcolumns = intervalcolumns

    df = clean(df, yearkeyout, monthkeyout, daykeyout, issuekey, split=split, dropcolumns=dropcolumns, drop_empty=drop_empty, verbose=verbose, indent=indent)

    printv('', verbose=verbose)

    return df
