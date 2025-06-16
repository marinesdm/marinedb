#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import modifyissuecolumn

# Global variable

__all__ = [] # populated using the @export decorator

def drop_emptygeneratedcolumn(df, gencolumn):

    if pd.isnull(df[gencolumn]).all():
        df.drop(columns=gencolumn, inplace=True)

    return df

def get_basekey(key, columns):

    basekey = key.split('_processedby_')[0]
    if ('generatedby' in basekey):
        basekey = basekey.split('_generatedby_')[0]
        columns = [col.split('_processedby_')[0] for col in columns]
        if basekey in columns:
            basekey += '-GEN'
    basekey = basekey.upper()

    return basekey

@export
def astype_Int64(df, key, drop_empty=True, verbose=True, indent=''):

    basekey = get_basekey(key, list(df.columns))

    # Pre-process date components (strip)

    df[key] = df[key].astype('string').str.replace(r'^\s+|\s+$','',regex=True)

    # Replace string with missing values if it contains non-numeric characters
    # (excluding floating point)

    notonlynumbers = df[key].str.contains(r'[^.0-9]', regex=True)
    notfloatingpoint = (df[key].str.count(r'\.') > 1)
    condition = (notonlynumbers | notfloatingpoint) #debug
    if condition.any():
        print(df.loc[condition, key]) #debug
        print(df.loc[~condition,key])
    df.loc[notonlynumbers | notfloatingpoint, key] = pd.NA
    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{basekey}_INVALID', subset=(notonlynumbers | notfloatingpoint))

    # Convert to integers

    df[key] = df[key].astype('Float64').astype('Int64')

    # Clean

    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

@export
def convert_year(df, yearkey, drop_ambiguous=False, drop_empty=True, verbose=True, indent=''):
    print('yearkey:', yearkey) #debug
    baseyearkey = get_basekey(yearkey, list(df.columns))

    # Convert to integers

    df = astype_Int64(df, yearkey, drop_empty=drop_empty, verbose=verbose, indent=indent)

    # Invalid years

    ismissing = pd.isnull(df[yearkey])
    yearlength = df[yearkey].astype('string').str.len()
    invalidyear =  (~ismissing) & ((yearlength == 3) | (yearlength > 4))
    df.loc[invalidyear, yearkey] = pd.NA
    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{baseyearkey}_INVALID', subset=invalidyear)

    # Ambiguous year string
    # e.g. does "20" represent 1720, 1820, 1920, or 2020?

    ismissing = pd.isnull(df[yearkey])
    yearlength = df[yearkey].astype('string').str.len()
    isincomplete = (~ismissing) & (yearlength < 4)
    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{baseyearkey}_AMBIGUOUS', subset=isincomplete)
    if drop_ambiguous:
        df.loc[isincomplete, yearkey] = pd.NA

    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

@export
def convert_month(df, monthkey, drop_empty=True, verbose=True, indent=''):

    basemonthkey = get_basekey(monthkey, list(df.columns))

    # Convert to integers

    df = astype_Int64(df, monthkey, drop_empty=drop_empty, verbose=verbose, indent=indent)

    # Invalid months

    ismissing = pd.isnull(df[monthkey])
    isinvalid = (df[monthkey] > 12) | (df[monthkey] < 1)
    invalidmonth = (~ismissing) & isinvalid
    df.loc[invalidmonth, monthkey] = pd.NA
    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{basemonthkey}_INVALID', subset=invalidmonth)
    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

@export
def convert_day(df, daykey, drop_empty=True, verbose=True, indent=''):

    basedaykey = get_basekey(daykey, list(df.columns))

    # Convert to integers

    df = astype_Int64(df, daykey, drop_empty=drop_empty, verbose=verbose, indent=indent)

    # Invalid days

    ismissing = pd.isnull(df[daykey])
    isinvalid = (df[daykey] > 31) | (df[daykey] < 1)
    invalidday = (~ismissing) & isinvalid
    df.loc[invalidday, daykey] = pd.NA
    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{basedaykey}_INVALID', subset=invalidday)
    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

def isvaliddate(df, yearkey, monthkey, daykey):

    columns = list(df.columns)
    baseyearkey = get_basekey(yearkey, columns)
    basemonthkey = get_basekey(monthkey, columns)
    basedaykey = get_basekey(daykey, columns)

    maxdaybymonth = pd.Series([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])

    # Nonexistent date
    ismissing = (pd.isnull(df[daykey]) | pd.isnull(df[monthkey]) | pd.isnull(df[daykey]))
    isvaliddate = ismissing
    isvaliddate[~ismissing] = (df.loc[~ismissing,daykey] <= maxdaybymonth[df.loc[~ismissing,monthkey]].set_axis(df.loc[~ismissing,:].index))

    # Leap years with 29 days in February
    isleapyear = (df[yearkey]%4 == 0) & ((df[yearkey]%100 != 0) | (df[yearkey]%400 == 0))
    condition = (~ismissing) & isleapyear & (df[monthkey] == 2)
    isvaliddate[condition] = (df.loc[condition, daykey] <= 29)

    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{baseyearkey}_{basemonthkey}_{basedaykey}_COMBINATION_INVALID', subset=(~isvaliddate))

    return df

@export
def apply(df, datekey=None, yearkey=None, monthkey=None, daykey=None, format='ISO8601', drop_inconsistent=False, drop_ambiguous=False, drop_empty=False, verbose=True, indent=''):

    if (datekey is not None) and (datekey not in df.columns):
        printv(f"INFO | Since '{datekey}' was not found in the columns, it will be ignored", verbose=verbose, indent=indent)
        datekey = None
    if (yearkey is not None) and (yearkey not in df.columns):
        printv(f"INFO | Since '{yearkey}' was not found in the columns, it will be ignored", verbose=verbose, indent=indent)
        yearkey = None
    if (monthkey is not None) and (monthkey not in df.columns):
        printv(f"INFO | Since '{monthkey}' was not found in the columns, it will be ignored", verbose=verbose, indent=indent)
        monthkey = None
    if (daykey is not None) and (daykey not in df.columns):
        printv(f"INFO | Since '{daykey}' was not found in the columns, it will be ignored", verbose=verbose, indent=indent)
        daykey = None

    if (datekey is None) and (yearkey is None) and (monthkey is None) and (daykey is None):
        printv('INFO | No column specified, the dataframe is returned as is', verbose=verbose, indent=indent)
        return df

    if (yearkey is None) and (monthkey is not None):
        raise Exception(f"`convertdatetype.py` | `yearkey`={yearkey}, but `monthkey`='{monthkey}'. Please either assign a value to `yearkey` or set `monthkey` to None.")
    if (monthkey is None) and (daykey is not None):
        raise Exception(f"`convertdatetype.py` | `monthkey`={monthkey}, but `daykey`='{daykey}'. Please either assign a value to `monthkey` or set `daykey` to None.")

    # Convert the date column to datetime format
    # Warning : If the function is applied to a column containing unprocessed date intervals,
    #           the result may be unexpected:
    #           - date intervals may be replaced by missing values (if errors='coerce')
    #           - pd.datetime() may interpret the second date as the time (e.g. 2021-03-02/2021-06-02 becomes '2021-03-02 20:21:00-02:00')
    #           - other special cases may arise that we haven't observed

    if datekey is not None:
        df[datekey] = pd.to_datetime(df[datekey].astype('string'), format=format, errors='coerce')
        # errors='coerce':
        #    invalid parsing set as NaT (Not a Time)
        #    e.g. NaT if date < 1677-09-22 or date > 2262-04-11 (Timestamp limitations)
        #    Remark : time span can be wider with unit > ns (ms, s ...)
        #    https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timestamp-limitations
        #    https://numpy.org/doc/stable/reference/arrays.datetime.html#datetime-units
        #    Warning : it may obscure other underlying issues

        df[datekey] = df[datekey].dt.tz_localize(None) # remove the time zone information (and preserve local time)

    # Verify hierarchical consistency:
    # - if the month is present, the year must also be present
    # - if the day is present, both year and month must be present

    if yearkey is not None:
        df['issue_convertdatetype'] = pd.NA
        df['issue_convertdatetype'] = df['issue_convertdatetype'].astype('string')

    columns = list(df.columns)
    if yearkey is not None:
        baseyearkey = get_basekey(yearkey, columns)
    if monthkey is not None:
        basemonthkey = get_basekey(monthkey, columns)
    if daykey is not None:
        basedaykey = get_basekey(daykey, columns)

    if monthkey is not None:
        yearmonth_inconsistency = pd.isnull(df[yearkey]) & (~pd.isnull(df[monthkey]))
        df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{baseyearkey}_{basemonthkey}_INCONSISTENT', subset=yearmonth_inconsistency)
    if daykey is not None:
        yearday_inconsistency = pd.isnull(df[yearkey]) & (~pd.isnull(df[daykey]))
        monthday_inconsistency = pd.isnull(df[monthkey]) & (~pd.isnull(df[daykey]))
        df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{baseyearkey}_{basedaykey}_INCONSISTENT', subset=yearday_inconsistency)
        df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{basemonthkey}_{basedaykey}_INCONSISTENT',  subset=monthday_inconsistency)

    # Convert the year, month, and day columns to integers

    if yearkey is not None:
        df = convert_year(df, yearkey, drop_ambiguous=drop_ambiguous, drop_empty=drop_empty, verbose=verbose, indent=indent)
    if monthkey is not None:
        df = convert_month(df, monthkey, drop_empty=drop_empty, verbose=verbose, indent=indent)
    if daykey is not None:
        df = convert_day(df, daykey, drop_empty=drop_empty, verbose=verbose, indent=indent)
    if (yearkey is not None) and (monthkey is not None) and (daykey is not None):
        df = isvaliddate(df, yearkey, monthkey, daykey)
        df.loc[df['issue_convertdatetype'].astype('string').str.contains('COMBINATION_INVALID'), daykey] = pd.NA

    # Ensure hierarchical consistency

    if drop_inconsistent:
       if monthkey is not None:
           df.loc[pd.isnull(df[yearkey]),monthkey] = pd.NA
       if daykey is not None:
           df.loc[pd.isnull(df[yearkey]),daykey] = pd.NA
           df.loc[pd.isnull(df[monthkey]),daykey] = pd.NA

    return df
