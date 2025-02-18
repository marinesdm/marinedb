import pandas as pd
import numpy as np

from marinedb.tools import convertdatetype
from marinedb.tools import processdateinterval


def _processdateinterval(df, key, drop):

    if f'flag_{key}_interval' not in df.columns: #flag_{key}_interval column does not yet exist
        print(f'            ** splitdate | processdateinterval (default parameters)')
        df = processdateinterval.apply(df, key, drop=drop, flag=True, inplace=False)

    if drop:
        key2process = key
    elif f'{key}_processedby_processdateinterval' in df.columns:
        key2process = f'{key}_processedby_processdateinterval'
    else: #assumption: processdateinterval has been called with inplace=True
        key2process = key

    return df, key2process


def apply(df, key, split_type='all', drop_interval=False, inplace=False, flag=False):

    # Split date into year/month/day

    # Warning : If the function is applied to a column containing unprocessed date intervals,
    #           or to a column that has been processed for date intervals but for which the `flag_{key}_interval` column has not be retained
    #           `processdateinterval.py` will be run with default parameters (maxinterval_number=1, maxinterval_level='years')
    #           If necessary, run `processdateinterval.py` with flag=True first

    # split_type = 'interval' or 'all'

    columns = df.columns

    df, key2process = _processdateinterval(df, key, drop=drop_interval)
    flagname = f'flag_{key}_interval'
    intervalcolumns = list(set(df.columns) - set(columns))

    # Select the dates to be processed: all dates or date intervals only
    # resp. split_type='all' or split_type='interval'

    if split_type == 'interval':
        process = df[flagname]
    else:
        # i.e split_type == 'all'
        process = np.full(len(df),True)

    # Select the columns in which the result will be stored
    # inplace=True: inplace `year`/`month`/`day` if the columns already exist
    # inplace=False: create new columns to avoid overwriting data in existing columns

    isday = ('day' in columns)
    ismonth = ('month' in columns)
    isyear = ('year' in columns)

    if isday or ismonth or isyear:

        if inplace:

            colnames = {'day':'day', 'month':'month', 'year':'year'}

            if split_type == 'all':
                print(f'            WARNING | `day`, `month` and/or `year` columns already exist and will be overwritten')
            if split_type == 'interval':
                print(f'            WARNING | `day`, `month` and/or `year` columns already exist and will be overwritten for date intervals')

        else:

            colnames = {'day':'day_processedby_splitdate', 'month':'month_processedby_splitdate', 'year':'year_processedby_splitdate'}

            if isday:
                df[colnames['day']] = df['day'].copy()
            if ismonth:
                df[colnames['month']] = df['month'].copy()
            if isyear:
                df[colnames['year']] = df['year'].copy()

    else:

        colnames = {'day':'day', 'month':'month', 'year':'year'}


    if (split_type=='interval') and drop_interval:

        print(f'            WARNING | `splitdate.py` only returns columns created during script execution if they are not empty') #consequently, it can return the dataframe unchanged

        if isday:
            df.loc[process,colnames['day']] = pd.NA
            df[colnames['day']] = df[colnames['day']].astype('Int64')
        if ismonth:
            df.loc[process,colnames['month']] = pd.NA
            df[colnames['month']] = df[colnames['month']].astype('Int64')
        if isyear:
            df.loc[process,colnames['year']] = pd.NA
            df[colnames['year']] = df[colnames['year']].astype('Int64')


        if flag:
            return df
        else:
            df.drop(columns=intervalcolumns, inplace=True)
            return df

    # Convert to datetime & UTC

    print(f'            ** splitdate | convertdatetype')

    tempcol = f'{key}_processing'
    df[tempcol] = df[key2process].copy()
    df = convertdatetype.apply(df, tempcol)

    # Split date into year, month & day

    print(f'            ** splitdate | split into year/month/day when known')

    df.loc[process,colnames['year']] = df.loc[process,tempcol].dt.year
    df.loc[process,colnames['month']] = df.loc[process,tempcol].dt.month
    df.loc[process,colnames['day']] = df.loc[process,tempcol].dt.day
    df.drop(columns=[tempcol], inplace=True)

    # Take date precision into account
    # (pd.to_datetime automatically adds day and/or month when missing)

    tempcol = f'{key}_precision'
    df[tempcol] = df[key2process].astype('str').str.len()

    df.loc[process & (df[tempcol]==7), colnames['day']] = pd.NA #YYYY-MM
    df.loc[process & (df[tempcol]==4),[colnames['day'],colnames['month']]] = [pd.NA, pd.NA] #YYYY

    df.drop(columns=[tempcol], inplace=True)

    # Handle date intervals

    if drop_interval:
        df.loc[df[flagname],colnames['day']] = pd.NA
        df.loc[df[flagname],colnames['month']] = pd.NA
        df.loc[df[flagname],colnames['year']] = pd.NA

    df[colnames['day']] = df[colnames['day']].astype('Int64')
    df[colnames['month']] = df[colnames['month']].astype('Int64')
    df[colnames['year']] = df[colnames['year']].astype('Int64')


    if not flag:
        df.drop(columns=intervalcolumns, inplace=True)
        return df

    return df
