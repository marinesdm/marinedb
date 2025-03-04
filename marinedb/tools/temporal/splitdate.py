# coding: utf-8

# External import

import pandas as pd
import numpy as np

# Internal import

from marinedb.tools.temporal import convertdatetype
from marinedb.tools.temporal import processdateinterval


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
    # If the function is applied to a DataFrame that lacks 'flag_{basedatekey}_interval' column,
    # `processdateinterval.py` will be executed, regardless of whether date intervals have already been processed

    basedatekey = datekey.split('_processedby_')[0]

    # Check if the 'datekey' column has already been processed by `processdateinterval`

#    column = [col for col in df.columns if (basedatekey in col) and ('processdateinterval' in col)]
#    if len(column) > 1:
#        # unexpected
#        raise Exception(f"`splitdate.py` | Multiple columns found containing '{basedatekey}' & 'processdateinterval': {column}. An issue may have occurred during execution.")

    isprocessedby_processdateinterval = ('processdateinterval' in datekey)

    if isprocessedby_processdateinterval and (f'flag_{basedatekey}_interval' not in df.columns):

        # The column has already been processed by `processdateinterval`
        # but `processdateinterval` has been called with flag=False

        # Attempt to detect date intervals from the previous version of the column
        modulenames = datekey.split('_processedby_')[1].split('_')
        stop_index = modulenames.index('processdateinterval')
        if stop_index > 0:
            previouscolumnversion = basedatekey + '_processedby_' + '_'.join(modulenames[:stop_index])
        else:
            previouscolumnversion = basedatekey

        if previouscolumnversion in df.columns:
            df[f'flag_{basedatekey}_interval'] = processdateinterval.isdateinterval(df, previouscolumnversion)
        else:
            # No remaining date intervals, with no way to determine prior existence
            df[f'flag_{basedatekey}_interval'] = False

    if f'flag_{basedatekey}_interval' not in df.columns:
        print(f'            ** splitdate | processdateinterval')
        df = processdateinterval.apply(df, datekey, drop_interval=drop_interval, strategy=strategy, maxinterval_number=maxinterval_number, maxinterval_level=maxinterval_level, inplace=False, flag=True)

    datekeyin = [col for col in df.columns if (basedatekey in col) and ('processdateinterval' in col)]
    if len(datekeyin) > 1:
        # unexpected
        raise Exception(f"`splitdate.py` | Multiple columns found containing '{basedatekey}' & 'processdateinterval': {column}. An issue may have occurred during execution.")
    elif len(datekeyin) == 1:
        datekeyin = datekeyin[0]
    else:
        # `processdateinterval` has been called with inplace=True
        datekeyin = datekey

#    if drop_interval:
#        datekey2process = datekey
#    elif f'{datekey}_processedby_processdateinterval' in df.columns:
#        datekey2process = f'{datekey}_processedby_processdateinterval'
#    else:
#        # assumption: processdateinterval has been called with inplace=True
#        datekey2process = datekey

    return df, datekeyin

#def _process_year(df, yearkey):
#
#    year = convertdatetype.convert_year(df[[yearkey]].copy(), yearkey, drop_ambiguous=False)
#    if ('issue_convertdatetype' in year.columns):
#        df['issue_convertdatetype'] = year['issue_convertdatetype'].values
#
#    year = year[yearkey]
#
#    return year

#def _process_month(df, monthkey):
#
#    month = convertdatetype.convert_month(df[[monthkey]].copy(), monthkey)
#    if ('issue_convertdatetype' in month.columns):
#        if ('issue_convertdatetype' in df.columns):
#            ismissing = pd.isnull(month['issue_convertdatetype'])
#            df.loc[~ismissing, 'issue_convertdatetype'] = df.loc[~ismissing, 'issue_convertdatetype'].str.cat(month.loc[~ismissing, 'issue_convertdatetype'], sep=';', na_rep='')
#            df.loc[~ismissing, 'issue_convertdatetype'] = df.loc[~ismissing, 'issue_convertdatetype'].str.strip(';')
#        else:
#            df['issue_convertdatetype'] = month['issue_convertdatetype'].values
#
#    month = month[monthkey]
#
#    return month

#def _process_day(df, daykey):
#
#    day = convertdatetype.convert_day(df[[daykey]].copy(), daykey)
#    if ('issue_convertdatetype' in day.columns):
#        if ('issue_convertdatetype' in df.columns):
#            ismissing = pd.isnull(day['issue_convertdatetype'])
#            df.loc[~ismissing, 'issue_convertdatetype'] = df.loc[~ismissing, 'issue_convertdatetype'].str.cat(day.loc[~ismissing, 'issue_convertdatetype'], sep=';', na_rep='')
#            df.loc[~ismissing, 'issue_convertdatetype'] = df.loc[~ismissing, 'issue_convertdatetype'].str.strip(';')
#        else:
#            df['issue_convertdatetype'] = day['issue_convertdatetype'].values
#
#    day = day[daykey]
#
#    return day

def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, split='all', drop_interval=False, drop_mismatch=True, drop_empty=False, inplace=False, flag=True, strategy='overlap', maxinterval_number=1, maxinterval_level='years'):

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
    df, yearkey, yearkeyout = getcolumnname.apply(df, yearkey, 'splitdate', inplace=inplace)
    df, monthkey, monthkeyout = getcolumnname.apply(df, monthkey, 'splitdate', inplace=inplace)
    df, daykey, daykeyout = getcolumnname.apply(df, daykey, 'splitdate', inplace=inplace)

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
    flagcolumn = f'flag_{basedatekey}_interval'
    intervalcolumns = list(set(df.columns) - set(columns))
    intervalcolumns = [col for col in intervalcolumns if 'issue' not in col]

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

#    if isyear:
#        year = _process_year(df, yearkey)
#    if ismonth:
#        month = _process_month(df, monthkey)
#    if isday:
#        day = _process_day(df, daykey)
    if isyear:

        convertdf = convertdatetype.apply(df.copy(), yearkey=yearkey, monthkey=monthkey, daykey=daykey, drop_inconsistent=False, drop_ambiguous=False, drop_empty=False)
#        df.loc[process,colnames['year']] = convertdf.loc[process,yearkey].copy()
        year = convertdf[yearkey].astype('string').copy()
        isonedigit = (year.astype('string').str.len() == 1)
        year[isonedigit] = '0' + year[isonedigit]

        if ismonth:

#            df.loc[process,colnames['month']] = convertdf.loc[process,monthkey].copy()
            month = convertdf[monthkey].astype('string').copy()
            isonedigit = (month.astype('string').str.len() == 1)
            month[isonedigit] = '0' + month[isonedigit]

        if isday:

#            df.loc[process,colnames['day']] = convertdf.loc[process,daykey].copy()
            day = convertdf[daykey].astype('string').copy()
            isonedigit = (day.astype('string').str.len() == 1)
            day[isonedigit] = '0' + day[isonedigit]

#        if ('issue_convertdatetype' in convertdf.columns):
#            df['issue_convertdatetype'] = convertdf['issue_convertdatetype'].values #GESTION ISSUE ICI

        del convertdf

    ## Initialize the output columns

    if isday or ismonth or isyear:

        if inplace:

            colnames = {'day':daykey, 'month':monthkey, 'year':yearkey}

            if split == 'all':
                print(f'            WARNING | `{daykey}`, `{monthkey}` and/or `{yearkey}` columns already exist and will be overwritten')
            if split == 'interval':
                print(f'            WARNING | `{daykey}`, `{monthkey}` and/or `{yearkey}` columns already exist and will be overwritten for date intervals')

        else:

#            colnames = {'day':f'{daykey}_processedby_splitdate', 'month':f'{monthkey}_processedby_splitdate', 'year':f'{yearkey}_processedby_splitdate'}
            colnames = {'day':daykeyout, 'month':monthkeyout, 'year':yearkeyout}

            if isyear:
                df[colnames['year']] = df[yearkey].copy()
            if ismonth:
                df[colnames['month']] = df[monthkey].copy()
            if isday:
                df[colnames['day']] = df[daykey].copy()

    else:

        colnames = {'day':daykey, 'month':monthkey, 'year':yearkey}

    isoutputcolumnsgenerated = (not inplace) or ((not isday) and (not ismonth) and (not isyear))
    drop_empty = (drop_empty and isoutputcolumnsgenerated)

    print(f"            INFO | daykey='{colnames['day']}', monthkey='{colnames['month']}', yearkey='{colnames['year']}'")

    if (split == 'interval') and (~df[flagcolumn]).all():
        print(f"            INFO | split='{split}', but no date intervals were found")
        if flag:
     #CHAGER ICI RETOURNER ISSUE ET COLONNES PROCESSED BY !!!!!!!!         
            return df
        else:
            df.drop(columns=intervalcolumns, inplace=True)
            return df

    if (split=='interval') and drop_interval:

        # Replace year, month and day values with NaN for interval dates

        if isyear:
            df.loc[process,colnames['year']] = pd.NA
            #df[colnames['year']] = df[colnames['year']].astype('Int64')
        if ismonth:
            df.loc[process,colnames['month']] = pd.NA
            #df[colnames['month']] = df[colnames['month']].astype('Int64')
        if isday:
            df.loc[process,colnames['day']] = pd.NA
            #df[colnames['day']] = df[colnames['day']].astype('Int64')

        # Clean

        if not flag:
            dropcolumns = intervalcolumns
        else:
            dropcolumns = None

        df = _clean(df, colnames['year'], colnames['month'], colnames['day'], issuekey, split, dropcolumns=dropcolumns, drop_empty=drop_empty)

#        dropcolumns = []
#        if isoutputcolumnsgenerated:
#            if pd.isnull(df[colnames['year']]).all():
#                dropcolumns += [colnames['year']]
#            if pd.isnull(df[colnames['month']]).all():
#                dropcolumns += [colnames['month']]
#            if pd.isnull(df[colnames['day']]).all():
#                dropcolumns += [colnames['day']]

#        if not flag:
#            dropcolumns += intervalcolumns

#        df.drop(columns=dropcolumns, inplace=True)

        return df

    # Split date into year, month & day

    print(f'            ** splitdate | split into year/month/day when known')

    date_split = df.loc[process,datekey].str.split('-')

    df.loc[process,colnames['year']] = date_split.str[0][process].values
    df.loc[process,colnames['month']] = date_split.str[1][process].values
    df.loc[process,colnames['day']] = date_split.str[2][process].values

    # Handle date intervals

    if drop_interval:
        df.loc[df[flagcolumn],colnames['year']] = pd.NA
        df.loc[df[flagcolumn],colnames['month']] = pd.NA
        df.loc[df[flagcolumn],colnames['day']] = pd.NA

    df[colnames['year']] = df[colnames['year']].astype('string')
    df[colnames['month']] = df[colnames['month']].astype('string')
    df[colnames['day']] = df[colnames['day']].astype('string')
#    df[colnames['year']] = df[colnames['year']].astype('Int64')
#    df[colnames['month']] = df[colnames['month']].astype('Int64')
#    df[colnames['day']] = df[colnames['day']].astype('Int64')
#    df = convertdatetype.convert_year(df, colnames['year'], drop_ambiguous=False)
#    df = convertdatetype.convert_month(df, colnames['month'])
#    df = convertdatetype.convert_day(df, colnames['day'])

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
#        isonedigit = (refyear.astype('string').str.len() == 1)
#        refyear[isonedigit] = '0' + refyear[isonedigit]
        mapindex = list(refyear.index)
        isyearmismatch += [mapindex[idx] for idx,y in enumerate(refyear) if (y != df.loc[mapindex[idx],colnames['year']][-2:])]
        df.loc[isyearmismatch,issuekey] = f'{yearkey.upper()}_MISMATCH'

#        if drop_mismatch:
#            df.loc[isyearmismatch,[colnames['year'],colnames['month'],colnames['day']]] = pd.NA

    if ismonth:
        ismissing = (pd.isnull(df[colnames['month']]) | pd.isnull(month))
        ismonthmismatch = (df.loc[(~ismissing) & process,colnames['month']] != month[(~ismissing) & process])
        ismonthmismatch = ismonthmismatch[ismonthmismatch].index
        df.loc[ismonthmismatch,issuekey] = f'{monthkey.upper()}_MISMATCH'

#        if drop_mismatch:
#            df.loc[ismonthmismatch,[colnames['month'],colnames['day']]] = pd.NA

    if isday:
        ismissing = (pd.isnull(df[colnames['day']]) | pd.isnull(day))
        isdaymismatch = (df.loc[(~ismissing) & process,colnames['day']] != day[(~ismissing) & process])
        isdaymismatch = isdaymismatch[isdaymismatch].index
        df.loc[isdaymismatch,issuekey] = f'{daykey.upper()}_MISMATCH'

#        if drop_mismatch:
#            df.loc[isdaymismatch,colnames['day']] = pd.NA

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

#    ismissing = pd.isnull(df[colnames['year']])
    df.loc[process & pd.isnull(df[colnames['year']]),[colnames['month'],colnames['day']]] = pd.NA
#    ismissing = pd.isnull(df[colnames['month']])
    df.loc[process & pd.isnull(df[colnames['month']]),colnames['day']] = pd.NA

    # Clean

#    print(f'            INFO | Only non-empty generated columns will be returned')

    if not flag:
        dropcolumns = intervalcolumns
    else:
        dropcolumns = None

    df = _clean(df, colnames['year'], colnames['month'], colnames['day'], issuekey, split=split, dropcolumns=dropcolumns, drop_empty=drop_empty)

#    dropcolumns = []
#    if isoutputcolumnsgenerated:
#        if pd.isnull(df[colnames['year']]).all():
#            dropcolumns += [colnames['year']]
#        if pd.isnull(df[colnames['month']]).all():
#            dropcolumns += [colnames['month']]
#        if pd.isnull(df[colnames['day']]).all():
#            dropcolumns += [colnames['day']]
#        if pd.isnull(df[issuekey]).all():
#            dropcolumns += [issuekey]

#    if not flag:
#        dropcolumns += intervalcolumns

#    df.drop(columns=dropcolumns, inplace=True)

#    try:
#        df[colnames['year']] = df[colnames['year']].astype('Int64')
#        df[colnames['month']] = df[colnames['month']].astype('Int64')
#        df[colnames['day']] = df[colnames['day']].astype('Int64')
#    except ValueError as error:
#        if split=='interval':
#            print(f"            INFO | Failed to convert `{colnames['year']}`, `{colnames['month']}` and `{colnames['day']}` to integers (type='{split}'). Converting to strings instead.")
#            df[colnames['year']] = df[colnames['year']].astype('string')
#            df[colnames['month']] = df[colnames['month']].astype('string')
#            df[colnames['day']] = df[colnames['day']].astype('string')
#        else:
#            raise ValueError(error)

#    issuecolumns = [col for col in df.columns if 'issue' in col]
#    df[issuecolumns] = df[issuecolumns].astype('string')

    return df
