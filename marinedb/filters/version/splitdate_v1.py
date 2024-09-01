import pandas as pd
import numpy as np
import filters.convertdatetype as convertdatetype
import filters.processdateinterval as processdateinterval


def _processdateinterval(df, key, drop):

    columns=df.columns

    if f'flag_{key}_interval' not in columns:
        print(f"            processdateinterval |flag_{key}_interval column does not yet exist, running with default parameters") 
        df = processdateinterval.apply(df, key, drop=drop, inplace=False, flag=True)
        key2process = f'{key}_processedby_processdateinterval'
    elif f'{key}_processedby_processdateinterval' in columns:
        key2process = f'{key}_processedby_processdateinterval'
    else: #assumption: processdateinterval as been called with inplace=True
        key2process=key

    return df, key2process


def apply(df, key, drop_interval=False, overwrite=False, overwrite_type='all', flag=False):

    # Split date into year/month/day

    #Warning : If the function is applied to a column containing unprocessed date intervals, these will be treated as missing values,
    #          unless drop_interval=False or (overwrite=True & overwrite_type='interval')
    #          If necessary, run processdateinterval.py first.

    #overwrite_type='interval' or 'all'

    #drop_interval=False, overwrite=False : processdateinterval si besoin, création ..._processedby_splitdate, script
    #drop_interval=True, overwrite=False : création ..._processedby_splitdate, script (convertdatetype replaces date intervals with missing values, and therefore also years, months and days)
    #drop_interval=False, overwrite=True, overwrite_type='all' : processdateinterval si besoin, script
    #drop_interval=False, overwrite=True, overwrite_type='interval' : processdateinterval si besoin, récupérer les indices des intervalles, script sur le subset
    #drop_interval=True, overwrite=True, overwrite_type='all' : script
    #drop_interval=True, overwrite=True, overwrite_type='interval' : processdateinterval si besoin, récupérer les indices des intervalles, remplacer ou remplir day/month/year par pd.NA

    process=np.full(len(df),True)
    key2process=key
    columns = df.columns

    df, key2process = _processdateinterval(df, key, drop=drop_interval)
    newcolumns=set(df.columns) - set(columns)

    if ('day' in columns) or ('month' in columns) or ('year' in columns):

        if overwrite:

            colnames = {"day":"day", "month":"month", "year":"year"}

            if overwrite_type=='all':

                print(f"            WARNING | `day`, `month` and/or `year` columns already exist and will be overwritten")

            if overwrite_type=='interval':

                print(f"            WARNING | `day`, `month` and/or `year` columns already exist and will be overwritten for date intervals")

                process = df[f'flag_{key}_interval'].tolist()

                if drop_interval:
                    df.loc[process,colnames['day']]=pd.NA
                    df.loc[process,colnames['month']]=pd.NA
                    df.loc[process,colnames['year']]=pd.NA
                    if flag:
                        return df
                    else:
                        df.drop(columns=newcolumns, inplace=True)
                        return df

        else:
            colnames = {"day":"day_processedby_splitdate", "month":"month_processedby_splitdate", "year":"year_processedby_splitdate"}

    else:

        colnames = {"day":"day", "month":"month", "year":"year"}

        if overwrite and (overwrite_type=='interval') and drop_interval:
            print("WARNING | `day`, `month` and/or `year` columns does not exist yet")
            print("           In this case, applying `splitdate.py` to the intervals alone with `drop_interval=True` would create 3 empty columns.")
            print("           `splitdate.py` returns the dataframe unchanged")
            return df

    # Convert to datetime & UTC

    tempcol = f'{key}_processing'
    df[tempcol] = df[key2process].values.copy()
    df = convertdatetype.apply(df, tempcol)

    # Split date into year, month & day

    df.loc[process,colnames['year']]=df.loc[process,tempcol].dt.year
    df.loc[process,colnames['month']]=df.loc[process,tempcol].dt.month
    df.loc[process,colnames['day']]=df.loc[process,tempcol].dt.day
    df.drop(columns=[tempcol], inplace=True)

    # Take date precision into account
    # (pd.to_datetime automatically adds day and/or month when missing)

    tempcol = f'{key}_precision'
    df[tempcol] = df[key2process].astype('str').str.len()

    df.loc[process & (df[tempcol]==7), colnames['day']]=pd.NA #YYYY-MM
    df.loc[process & (df[tempcol]==4),[colnames['day'],colnames['month']]]=[pd.NA, pd.NA] #YYYY

    df[colnames['day']] = df[colnames['day']].astype('Int64')
    df[colnames['month']] = df[colnames['month']].astype('Int64')
    df[colnames['year']] = df[colnames['year']].astype('Int64')

    df.drop(columns=[tempcol], inplace=True)

    if not flag and not drop_interval:
        df.drop(columns=newcolumns, inplace=True)
        return df

    return df
