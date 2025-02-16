
import pandas as pd

def astype_Int64(df, key):

    # Pre-process date components

    df[key] = df[key].astype('string').str.replace(r'^\s+|\s+$','',regex=True)

    # Replace string with missing values if it contains non-numeric characters
    # (excluding floating point)

    if ('issue_convertdatetype' not in df.columns):
        df['issue_convertdatetype'] = pd.NA
        df['issue_convertdatetype'] = df['issue_convertdatetype'].astype('string')

    iskey = (~pd.isnull(df[key]))
    notonlynumbers = df.loc[iskey, key].str.contains(r'[^.0-9]', regex=True)
    notonlynumbers_index = notonlynumbers[notonlynumbers].index
    df.loc[notonlynumbers_index, key] = pd.NA
    df.loc[notonlynumbers_index, 'issue_convertdatetype'] = df.loc[notonlynumbers_index, 'issue_convertdatetype'].fillna('') + f';{key.upper()}_INVALID'
    df.loc[notonlynumbers_index, 'issue_convertdatetype'] = df.loc[notonlynumbers_index, 'issue_convertdatetype'].str.strip(';')

    # Convert to integers

    df[key] = df[key].astype('Float64').astype('Int64')
    if pd.isnull(df['issue_convertdatetype']).all():
        df = df.drop('issue_convertdatetype', axis=1)
    else:
        df['issue_convertdatetype'] = df['issue_convertdatetype'].astype('string')

    return df

def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, format='ISO8601'):

    if (yearkey is None) and (monthkey is not None):
        raise Exception(f'`monthkey`={monthkey} but `yearkey` is None')
    if (monthkey is None) and (daykey is not None):
        raise Exception(f'`daykey`={daykey} but `monthkey` is None')

    # Convert the date column to datetime format
    #Warning : If the function is applied to a column containing unprocessed date intervals,
    #          the result may be unexpected:
    #          - date intervals may be replaced by missing values (errors='coerce')
    #          - pd.datetime() may interpret the second date as the time (e.g. 2021-03-02/2021-06-02 becomes '2021-03-02 20:21:00-02:00')
    #          - other special cases may arise that we haven't observed

    df[datekey] = pd.to_datetime(df[datekey].astype('string'), format=format) #, errors='coerce') DEBUG repérer erreurs éventuelles
    #errors='coerce':
    #    invalid parsing set as NaT (Not a Time)
    #    e.g. NaT if date < 1677-09-22 or date > 2262-04-11 (Timestamp limitations)
    #    Remark : time span can been wider with unit > ns (ms, s ...)
    #    https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timestamp-limitations
    #    https://numpy.org/doc/stable/reference/arrays.datetime.html#datetime-units
    #    Warning : there may be other parsing issues and they may be mask

    df[datekey]=df[datekey].dt.tz_localize(None) # remove the time zone information (and preserve local time)

    # Convert the year, month, and day columns to integers

    if yearkey is not None:
        df = astype_Int64(df, yearkey)
    if monthkey is not None:
        df = astype_Int64(df, monthkey)
        df.loc[pd.isnull(df[yearkey]),monthkey] = pd.NA
    if daykey is not None:
        df = astype_Int64(df, daykey)
        df.loc[pd.isnull(df[yearkey]),daykey] = pd.NA
        df.loc[pd.isnull(df[monthkey]),daykey] = pd.NA

    return df
