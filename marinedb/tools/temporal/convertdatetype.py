# coding: utf-8

#External import

import pandas as pd

# Internal import

from marinedb.tools import modifyissuecolumn

def drop_emptygeneratedcolumn(df, gencolumn):

    if pd.isnull(df[gencolumn]).all():
        df.drop(columns=gencolumn, inplace=True)

    return df

def astype_Int64(df, key, drop_empty=True):

    basekey = key.split('_processedby_')[0].upper()

    # Pre-process date components (strip)

    df[key] = df[key].astype('string').str.replace(r'^\s+|\s+$','',regex=True)

    # Replace string with missing values if it contains non-numeric characters
    # (excluding floating point)

    notonlynumbers = df[key].str.contains(r'[^.0-9]', regex=True)
    df.loc[notonlynumbers, key] = pd.NA
    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{basekey}_INVALID', subset=notonlynumbers)

    # Convert to integers

    df[key] = df[key].astype('Float64').astype('Int64')

    # Clean

    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

def convert_year(df, yearkey, drop_ambiguous=False, drop_empty=True):

    baseyearkey = yearkey.split('_processedby_')[0].upper()

    # Convert to integers

    df = astype_Int64(df, yearkey, drop_empty=drop_empty)

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

def convert_month(df, monthkey, drop_empty=True):

    basemonthkey = monthkey.split('_processedby_')[0].upper()

    # Convert to integers

    df = astype_Int64(df, monthkey, drop_empty=drop_empty)

    # Invalid months

    ismissing = pd.isnull(df[monthkey])
    isinvalid = (df[monthkey] > 12) | (df[monthkey] < 1)
#    monthlength = df[monthkey].astype('string').str.len()
    invalidmonth = (~ismissing) & isinvalid
    df.loc[invalidmonth, monthkey] = pd.NA
    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{basemonthkey}_INVALID', subset=invalidmonth)
    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

def convert_day(df, daykey, drop_empty=True):

    basedaykey = daykey.split('_processedby_')[0].upper()

    # Convert to integers

    df = astype_Int64(df, daykey, drop_empty=drop_empty)

    # Invalid days

    ismissing = pd.isnull(df[daykey])
    isinvalid = (df[daykey] > 31) | (df[daykey] < 1)
#    daylength = df[daykey].astype('string').str.len()
    invalidday = (~ismissing) & isinvalid
    df.loc[invalidday, daykey] = pd.NA
    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{basedaykey}_INVALID', subset=invalidday)
    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

def isvaliddate(df, yearkey, monthkey, daykey):

    baseyearkey = yearkey.split('_processedby_')[0].upper()
    basemonthkey = monthkey.split('_processedby_')[0].upper()
    basedaykey = daykey.split('_processedby_')[0].upper()

    maxdaybymonth = pd.Series([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
#    maxdaybymonth_leapyear = pd.Series([0, 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    ismissing = (pd.isnull(df[daykey]) | pd.isnull(df[monthkey]) | pd.isnull(df[daykey]))
    isvaliddate = ismissing
    isvaliddate[~ismissing] = (df.loc[~ismissing,daykey] <= maxdaybymonth[df.loc[~ismissing,monthkey]].set_axis(df.loc[~ismissing,:].index))
    isleapyear = (df[yearkey]%4 == 0) & ((df[yearkey]%100 != 0) | (df[yearkey]%400 == 0))
    isvaliddate[isleapyear & (~ismissing) & (df[monthkey] == 2)] = (df.loc[isleapyear & (~ismissing) & (df[monthkey] == 2),daykey] <= 29)
#    df.loc[isleapyear,'isvaliddate'] = (df.loc[isleapyear,daykey] <= maxdaybymonth_leapyear[df.loc[isleapyear,monthkey]])
#    df.loc[~isleapyear,'isvaliddate'] = (df.loc[~isleapyear,daykey] <= maxdaybymonth[df.loc[~isleapyear,monthkey]])

    df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{baseyearkey}_{basemonthkey}_{basedaykey}_COMBINATION_INVALID', subset=(~isvaliddate))

    return df

def apply(df, datekey=None, yearkey=None, monthkey=None, daykey=None, format='ISO8601', drop_inconsistent=False, drop_ambiguous=False, drop_empty=False):

    if (datekey is None) and (yearkey is None) and (monthkey is None) and (daykey is None):
        print('            INFO | No column specified, the dataframe is returned as is.')
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
        #    Remark : time span can been wider with unit > ns (ms, s ...)
        #    https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timestamp-limitations
        #    https://numpy.org/doc/stable/reference/arrays.datetime.html#datetime-units
        #    Warning : there may be other parsing issues and they may be mask

        df[datekey]=df[datekey].dt.tz_localize(None) # remove the time zone information (and preserve local time)

    # Verify hierarchical consistency:
    # - if the month is present, the year must also be present
    # - if the day is present, both year and month must be present

    if yearkey is not None:
        df['issue_convertdatetype'] = pd.NA
        df['issue_convertdatetype'] = df['issue_convertdatetype'].astype('string')

    if yearkey is not None:
        baseyearkey = yearkey.split('_processedby_')[0].upper()
    if monthkey is not None:
        basemonthkey = monthkey.split('_processedby_')[0].upper()
    if daykey is not None:
        basedaykey = daykey.split('_processedby_')[0].upper()

    if monthkey is not None:
        yearmonth_inconsistency = pd.isnull(df[yearkey]) & (~pd.isnull(df[monthkey]))
        df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{baseyearkey}_{basemonthkey}_INCONSISTENT', subset=yearmonth_inconsistency)
    if daykey is not None:
        yearday_inconsistency = pd.isnull(df[yearkey]) & (~pd.isnull(df[daykey]))
        monthday_inconsistency = pd.isnull(df[monthkey]) & (~pd.isnull(df[daykey]))
        df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{baseyearkey}_{basedaykey}_INCONSISTENT', subset=yearday_inconsistency)
        df = modifyissuecolumn.apply(df, issuekey='issue_convertdatetype', issuemsg=f'{basemonthkey}_{basedaykey}_INCONSISTENT',  subset=monthday_inconsistency)

#    if drop_inconsistent:
#        if monthkey is not None:
#            df.loc[yearmonth_inconsistency,monthkey] = pd.NA
#        if daykey is not None:
#            df.loc[yearday_inconsistency,daykey] = pd.NA
#            df.loc[monthday_inconsistency,daykey] = pd.NA

    # Convert the year, month, and day columns to integers

    if yearkey is not None:
        df = convert_year(df, yearkey, drop_ambiguous=drop_ambiguous, drop_empty=drop_empty)
    if monthkey is not None:
        df = convert_month(df, monthkey, drop_empty=drop_empty)
    if daykey is not None:
        df = convert_day(df, daykey, drop_empty=drop_empty)
    if (yearkey is not None) and (monthkey is not None) and (daykey is not None):
        df = isvaliddate(df, yearkey, monthkey, daykey)

    # Ensure hierarchical consistency

    if drop_inconsistent:
       if monthkey is not None:
           df.loc[pd.isnull(df[yearkey]),monthkey] = pd.NA
       if daykey is not None:
           df.loc[pd.isnull(df[yearkey]),daykey] = pd.NA
           df.loc[pd.isnull(df[monthkey]),daykey] = pd.NA

    return df
