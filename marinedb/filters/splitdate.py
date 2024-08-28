import pandas as pd
import filters.convertdatetype
import filters.processdateinterval

def apply(df, key, overwrite=False, overwrite_type='all'): #flag

    # Split date into year/month/day

    #Warning : This function must only be used on a column that does not contain date intervals, otherwise an exception may be thrown by pd.to_datetime.
    #          If necessary, run processdateinterval.py first.

    #overwrite_type='interval' or 'all'

    process=[True]*len(df)

    columns = df.columns
    if ('day' in columns) or ('month' in columns) or ('year' in columns):

       if overwrite:

            if overwrite_type=='all':
                print(f"            WARNING | `day`, `month` and/or `year` columns already exist and will be overwritten")

            if overwrite_type=='interval':

                if f'flag_{key}_interval' not in columns:
                    print(f"            INFO | overwrite_type='interval' ; flag_{key}_interval column does not yet exist ; running processdateinterval")
                    df = processdateinterval.apply(df, key, inplace=False, flag=True)
                    key = f'{key}_processedby_processdateinterval'

                print(f"            WARNING | `day`, `month` and/or `year` columns already exist and will be overwritten for date intervals")

            process = df[f'flag_{key}_interval'].tolist()
            colnames = {"day":"day", "month":"month", "year":"year"}

        else:
            colnames = {"day":"day_processedby_splitdate", "month":"month_processedby_splitdate", "year":"year_processedby_splitdate"}

    else:
        colnames = {"day":"day", "month":"month", "year":"year"}


    # Convert to datetime & UTC

    tempcol = f'{key}_processing'
    df[tempcol] = df[key].values.copy()
    #df[tempcol] = pd.to_datetime(df[tempcol], format='mixed', yearfirst=True, errors='coerce', utc=True) #errors='coerce':
                                                                                                         #    invalid parsing set as NaT (Not a Time)
                                                                                                         #    e.g. NaT if date < 1677-09-22 or date > 2262-04-11 (outside al>
                                                                                                         #    Remark : time span can been wider with unit > ns (ms, s ...)
                                                                                                         #    Warning : there may be other parsing issues and they may be ma>
                                                                                                         #utc=True:
                                                                                                         #    https://pandas.pydata.org/pandas-docs/stable/reference/api/pan>
                                                                                                         #    localized as or converted to UTC
                                                                                                         #format='mixed':
                                                                                                         #    infer the format for each element individually

    #df[tempcol]=df[tempcol].dt.tz_localize(None) # remove the time zone information and preserve local time
    df = convertdatetype.apply(df, tempcol)

    # Split date into year, month & day

    df.loc[process,colnames['year']]=df.loc[process,tempcol].dt.year
    df.loc[process,colnames['month']]=df.loc[process,tempcol].dt.month
    df.loc[process,colnames['day']]=df.loc[process,tempcol].dt.day
    df.drop(columns=[tempcol], inplace=True)

    # Take date precision into account
    # (pd.to_datetime automatically adds day and/or month when missing)

    date_format = df[key].astype('str').str.len()
    #tempcol = f'{key}_precision'
    #df[tempcol]='unk'
    #df.loc[process & (np.where(date_format>7)[0]),tempcol]='day' #>= YYYY-MM-DD
    #df.loc[process & (np.where(date_format==7)[0]),[colnames['day'],tempcol]]=[pd.NA,colnames['month']] #YYYY-MM
    #df.loc[np.where(date_format==4)[0],[colnames['day'],colnames['month'],tempcol]]=[pd.NA, pd.NA,colnames['year']] #YYYY
    df.loc[process & (np.where(date_format==7)[0]), colnames['day']]=pd.NA #YYYY-MM
    df.loc[np.where(date_format==4)[0],[colnames['day'],colnames['month']]]=[pd.NA, pd.NA] #YYYY

    df[colnames['day']] = df[colnames['day']].astype('Int64')
    df[colnames['month']] = df[colnames['month']].astype('Int64')
    df[colnames['year']] = df[colnames['year']].astype('Int64')

    #if flag:
    #    return df
    #else:
    #    df.drop(columns=[tempcol], inplace=True)
    #    return df

    return df
