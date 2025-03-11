# coding: utf-8

# External import

import pandas as pd
import numpy as np
import os

# Internal import

from marinedb.tools import getcolumnname, modifyissuecolumn
from marinedb.tools.temporal import convertdatetype
from marinedb.tools.temporal import processdateinterval

# Global variable

SCRIPT_NAME = os.path.basename(__file__)[:-3]

#def modify_issue(df, issuekey, issue, subset=None):

#    if (subset is None):
#        subset = list(df.index)

#    df.loc[subset, issuekey] = df.loc[subset, issuekey].fillna('') + f';{issue}'
#    df.loc[subset, issuekey] = df.loc[subset, issuekey].str.strip(';')
#    df[issuekey] = df[issuekey].astype('string')

#    return df

def _clean(df, yearkey, monthkey, daykey, issuekey, split, dropcolumns=None, drop_empty=True):

    # Drop columns

    if dropcolumns is None:
        dropcolumns = []

    if drop_empty:
        print(f'            INFO | only non-empty generated columns will be returned')
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

        if split=='interval':
            print(f"            INFO | failed to convert `{yearkey}`, `{monthkey}` and `{daykey}` to integers (type='{split}'). Converting to strings instead.")
            df[yearkey] = df[yearkey].astype('string')
            df[monthkey] = df[monthkey].astype('string')
            df[daykey] = df[daykey].astype('string')
        else:
            raise ValueError(error)

    issuekeys = [col for col in df.columns if 'issue' in col]
    df[issuekeys] = df[issuekeys].astype('string')

    return df

def _processdateinterval(df, datekey, drop_interval, strategy='overlap', maxinterval_number=1, maxinterval_level='years'):

    # Warning :
    # If the function is applied to a DataFrame that lacks 'flag_{basedatekey}_dateinterval' column,
    # `processdateinterval.py` will be executed, regardless of whether date intervals have already been processed

    basedatekey = datekey.split('_processedby_')[0]

    # Check if the `datekey` column has already been processed by `processdateinterval`

    if ('processdateinterval' in datekey) and (f'flag_{basedatekey}_dateinterval' not in df.columns):

        # The column has already been processed by `processdateinterval`
        # but `processdateinterval` has been called with flag=False

        ## Has the column version preceding `processdateinterval` been retained?

        modulenames = datekey.split('_processedby_')[1].split('_')
        stop_index = modulenames.index('processdateinterval')
        if stop_index > 0:
            previouscolumnversion = basedatekey + '_processedby_' + '_'.join(modulenames[:stop_index])
        else:
            previouscolumnversion = basedatekey

        if previouscolumnversion in df.columns:
            ## Identify date intervals from the column version prior to `processdateinterval`
            df[f'flag_{basedatekey}_dateinterval'] = processdateinterval.isdateinterval(df, previouscolumnversion)
        else:
            ## No remaining date intervals, with no way to determine prior existence
            print('here')
            df[f'flag_{basedatekey}_dateinterval'] = False

    if f'flag_{basedatekey}_dateinterval' not in df.columns:

        # Process date intervals

        print(f'            ** splitdate | processdateinterval')

        df = processdateinterval.apply(df, datekey, drop_interval=drop_interval, strategy=strategy, maxinterval_number=maxinterval_number, maxinterval_level=maxinterval_level, inplace=False, flag=True)

    # Column name for futher processing

    datekeyin = [col for col in df.columns if (col[:len(basedatekey)] == basedatekey) and ('processdateinterval' in col)]
    if len(datekeyin) > 1:
#        for col in datekeyin:
#            coldiff = set(col) - set(datekeyin[-1])
#            if (len(coldiff) != 0):
#                # unexpected
        raise Exception(f"`splitdate.py` | '{basedatekey}' & 'processdateinterval': {datekeyin}. An issue may have occurred during execution.")
    elif len(datekeyin) == 1:
        datekeyin = datekeyin[0]
    else:
        # `processdateinterval` has been called with inplace=True
        datekeyin = datekey

    return df, datekeyin

def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, split='all', drop_interval=False, drop_mismatch=True, drop_empty=False, inplace=False, flag=True, strategy='overlap', maxinterval_number=1, maxinterval_level='years'):

    # output: issue_splitdate/issue_splitdateinterval, flagcolumn, yearkeyout, monthkeyout, daykeyout

    if split not in ['all','interval']:
        raise ValueError(f"`splitdate.py` | `split` must be 'all' or 'interval'")

    if (monthkey is not None) and (yearkey is None):
        raise Exception(f"`splitdate.py` | yearkey={yearkey} but monthkey='{monthkey}'. Please assign a value to `yearkey` or set `monthkey` to None.")
    if (daykey is not None) and (monthkey is None):
        raise Exception(f"`splitdate.py` | monthkey={monthkey} but daykey='{daykey}'. Please assign a value to `monthkey` or set `daykey` to None.")

    if (yearkey is None):
        yearkey = 'year'
    if (monthkey is None):
        monthkey = 'month'
    if (daykey is  None):
        daykey = 'day'

    df, datekey, _ = getcolumnname.apply(df, datekey, '', inplace=True)
    df, yearkey, yearkeyout = getcolumnname.apply(df, yearkey, SCRIPT_NAME, inplace=inplace)
    df, monthkey, monthkeyout = getcolumnname.apply(df, monthkey, SCRIPT_NAME, inplace=inplace)
    df, daykey, daykeyout = getcolumnname.apply(df, daykey, SCRIPT_NAME, inplace=inplace)

    columns = df.columns
    issuekey = ('issue_splitdate' if (split == 'all') else 'issue_splitdateinterval')
    df[issuekey] = pd.NA

    processdateinterval_params = {
                                  'drop_interval': drop_interval,
                                  'strategy': strategy,
                                  'maxinterval_number': maxinterval_number,
                                  'maxinterval_level': maxinterval_level
                                  }

    df, datekey = _processdateinterval(df, datekey, **processdateinterval_params)

    basedatekey = datekey.split('_processedby_')[0]
    baseyearkey = yearkey.split('_processedby_')[0].upper()
    basemonthkey = monthkey.split('_processedby_')[0].upper()
    basedaykey = daykey.split('_processedby_')[0].upper()
    flagcolumn = f'flag_{basedatekey}_dateinterval'
    intervalcolumns = list(set(df.columns) - set(columns))
    intervalcolumns = [col for col in intervalcolumns if ('flag' in col) or ('dateinterval_indays' in col)]
#    intervalcolumns = [col for col in intervalcolumns if 'issue' not in col]

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

    ## Preprocess and store available year, month, and day values

    if isyear:

        convertdf = convertdatetype.apply(df.copy(), yearkey=yearkey, monthkey=monthkey, daykey=daykey, drop_inconsistent=False, drop_ambiguous=False, drop_empty=False)

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

    colnames = {'day':daykeyout, 'month':monthkeyout, 'year':yearkeyout} #DEBUG : si marche remplacer tous les colnames par out

    if isday or ismonth or isyear:

        if inplace:

#            colnames = {'day':daykey, 'month':monthkey, 'year':yearkey}

            if split == 'all':
                print(f'            WARNING | `{daykey}`, `{monthkey}` and/or `{yearkey}` columns already exist and will be overwritten')
            if split == 'interval':
                print(f'            WARNING | `{daykey}`, `{monthkey}` and/or `{yearkey}` columns already exist and will be overwritten for date intervals')

        else:

#            colnames = {'day':f'{daykey}_processedby_splitdate', 'month':f'{monthkey}_processedby_splitdate', 'year':f'{yearkey}_processedby_splitdate'}

            if isyear:
                df[colnames['year']] = df[yearkey].copy()
            if ismonth:
                df[colnames['month']] = df[monthkey].copy()
            if isday:
                df[colnames['day']] = df[daykey].copy()

#    else:

#        colnames = {'day':daykey, 'month':monthkey, 'year':yearkey}

    df[colnames['year']] = df[colnames['year']].astype('string')
    df[colnames['month']] = df[colnames['month']].astype('string')
    df[colnames['day']] = df[colnames['day']].astype('string')

    isoutputcolumnsgenerated = (not inplace) or ((not isday) and (not ismonth) and (not isyear))
    drop_empty = (drop_empty and isoutputcolumnsgenerated)

    print(f"            INFO | daykey='{colnames['day']}', monthkey='{colnames['month']}', yearkey='{colnames['year']}'")

    if (split == 'interval') and (~df[flagcolumn]).all():

        # No date interval

        print(f"            INFO | split='{split}', but no date intervals were found")

        if flag:
            dropcolumns = None
        else:
            dropcolumns = intervalcolumns

        df = _clean(df, colnames['year'], colnames['month'], colnames['day'], issuekey, split, dropcolumns=dropcolumns, drop_empty=drop_empty)

        return df

    if (split == 'interval') and drop_interval:

        # Replace year, month and day values with NaN for interval dates

        if isyear:
            df.loc[process,colnames['year']] = pd.NA
        if ismonth:
            df.loc[process,colnames['month']] = pd.NA
        if isday:
            df.loc[process,colnames['day']] = pd.NA

        # Clean

        if not flag:
            dropcolumns = intervalcolumns
        else:
            dropcolumns = None

        df = _clean(df, colnames['year'], colnames['month'], colnames['day'], issuekey, split, dropcolumns=dropcolumns, drop_empty=drop_empty)

        return df

    # Split date into year, month & day

    print(f'            ** splitdate | split into year/month/day when known')

    date_split = df.loc[process,datekey].str.split('-')

    df.loc[process,colnames['year']] = date_split.str[0][process].astype('string').values
    df.loc[process,colnames['month']] = date_split.str[1][process].astype('string').values
    df.loc[process,colnames['day']] = date_split.str[2][process].astype('string').values

    # Handle date intervals

    if drop_interval:
        df.loc[df[flagcolumn],colnames['year']] = pd.NA
        df.loc[df[flagcolumn],colnames['month']] = pd.NA
        df.loc[df[flagcolumn],colnames['day']] = pd.NA

    df[colnames['year']] = df[colnames['year']].astype('string')
    df[colnames['month']] = df[colnames['month']].astype('string')
    df[colnames['day']] = df[colnames['day']].astype('string')

    # Replace mismatched year, month, or day values with NaN

    if isyear:
        ismissing = (pd.isnull(df[colnames['year']]) | pd.isnull(year))
        isfourdigit = (year.str.len() == 4)
        # four-digit years
        condition = (~ismissing) & isfourdigit & process
        isyearmismatch = (df.loc[condition,colnames['year']] != year[condition])
        isyearmismatch = list(isyearmismatch[isyearmismatch].index)
        # one-digit years or two-digit years
        condition = (~ismissing) & (~isfourdigit) & process
        refyear = year[condition].astype('string')
        mapindex = list(refyear.index)
        isyearmismatch += [mapindex[idx] for idx,y in enumerate(refyear) if (y != df.loc[mapindex[idx],colnames['year']][-2:])]
        df = modifyissuecolumn.apply(df, issuekey, f'{baseyearkey}_MISMATCH', subset=isyearmismatch)

    if ismonth:
        ismissing = (pd.isnull(df[colnames['month']]) | pd.isnull(month))
        ismonthmismatch = (df.loc[(~ismissing) & process,colnames['month']] != month[(~ismissing) & process])
        ismonthmismatch = ismonthmismatch[ismonthmismatch].index
        df = modifyissuecolumn.apply(df, issuekey, f'{basemonthkey}_MISMATCH', subset=ismonthmismatch)

    if isday:
        ismissing = (pd.isnull(df[colnames['day']]) | pd.isnull(day))
        isdaymismatch = (df.loc[(~ismissing) & process,colnames['day']] != day[(~ismissing) & process])
        isdaymismatch = isdaymismatch[isdaymismatch].index
        df = modifyissuecolumn.apply(df, issuekey, f'{basedaykey}_MISMATCH', subset=isdaymismatch)

    if drop_mismatch:
        if isyear:
            df.loc[isyearmismatch,[colnames['year'],colnames['month'],colnames['day']]] = pd.NA
        if ismonth:
            df.loc[ismonthmismatch,[colnames['month'],colnames['day']]] = pd.NA
        if isday:
            df.loc[isdaymismatch,colnames['day']] = pd.NA

    # Ensure hierarchical consistency:
    # - if year is missing, set month and day to NaN
    # - if month is missing, set day to NaN

    df.loc[process & pd.isnull(df[colnames['year']]),[colnames['month'],colnames['day']]] = pd.NA
    df.loc[process & pd.isnull(df[colnames['month']]),colnames['day']] = pd.NA

    # Clean

    if not flag:
        dropcolumns = intervalcolumns
    else:
        dropcolumns = None

    df = _clean(df, colnames['year'], colnames['month'], colnames['day'], issuekey, split=split, dropcolumns=dropcolumns, drop_empty=drop_empty)

    return df
