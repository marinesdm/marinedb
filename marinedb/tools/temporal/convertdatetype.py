# coding: utf-8

#External import
import pandas as pd

def create_issue_convertdatetype(df):

    if ('issue_convertdatetype' not in df.columns):
        df['issue_convertdatetype'] = pd.NA
        df['issue_convertdatetype'] = df['issue_convertdatetype'].astype('string')

    return df

#def modify_issue_convertdatetype(dfser, subset=None, issue=None):

#    if (issue is None):
#        raise Exception('`convertdatetype.py` | Please specify a value for `issue`')

#    if (subset is None):
#        print(f'            INFO | modify_issue_convertdatetype() will be applied to all rows (`subset`={subset})')
#        subset = list(dfser.index)

#    if isinstance(dfser,pd.DataFrame):
#        issueSeries = dfser['issue_convertdatetype']
#    elif isinstance(dfser,pd.Series):
#        issueSeries = dfser
#    else:
#        raise Exception(f'`convertdatetype.py` | Only DataFrame and Series types are supported')

#    issueSeries[subset] = issueSeries[subset].fillna('') + f';{issue}'
#    issueSeries[subset] = issueSeries[subset].str.strip(';')
#    issueSeries = issueSeries.astype('string')

# shallow copy, souldn't be necessary:
#    if isinstance(dfser,pd.DataFrame):
#        df.loc[subset, 'issue_convertdatetype'] = issueSeries[subset]

def modify_issue_convertdatetype(df, issue, subset=None):

    if (subset is None):
#        print(f'            INFO | modify_issue_convertdatetype() will be applied to all rows (`subset`={subset})')
        subset = list(df.index)

    df.loc[subset, 'issue_convertdatetype'] = df.loc[subset, 'issue_convertdatetype'].fillna('') + f';{issue}'
    df.loc[subset, 'issue_convertdatetype'] = df.loc[subset, 'issue_convertdatetype'].str.strip(';')
    df['issue_convertdatetype'] = df['issue_convertdatetype'].astype('string')

    return df

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
    df = create_issue_convertdatetype(df)
    df = modify_issue_convertdatetype(df, f'{basekey}_INVALID', notonlynumbers)

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
    df = create_issue_convertdatetype(df)
    df = modify_issue_convertdatetype(df, f'{baseyearkey}_INVALID', invalidyear)

    # Ambiguous year string
    # e.g. does "20" represent 1720, 1820, 1920, or 2020?

    ismissing = pd.isnull(df[yearkey])
    yearlength = df[yearkey].astype('string').str.len()
    isincomplete = (~ismissing) & (yearlength < 4)
    df = modify_issue_convertdatetype(df, f'{baseyearkey}_AMBIGUOUS', isincomplete)
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
    monthlength = df[monthkey].astype('string').str.len()
    invalidmonth = (~ismissing) & (monthlength > 2)
    df.loc[invalidmonth, monthkey] = pd.NA
    df = create_issue_convertdatetype(df)
    df = modify_issue_convertdatetype(df, f'{basemonthkey}_INVALID', invalidmonth)
    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

def convert_day(df, daykey, drop_empty=True):

    basedaykey = daykey.split('_processedby_')[0].upper()

    # Convert to integers

    df = astype_Int64(df, daykey, drop_empty=drop_empty)

    # Invalid days

    ismissing = pd.isnull(df[daykey])
    daylength = df[daykey].astype('string').str.len()
    invalidday = (~ismissing) & (daylength > 2)
    df.loc[invalidday, daykey] = pd.NA
    df = create_issue_convertdatetype(df)
    df = modify_issue_convertdatetype(df, f'{basedaykey}_INVALID', invalidday)
    if drop_empty:
        df = drop_emptygeneratedcolumn(df, 'issue_convertdatetype')

    return df

#def update_issue_convertdatetype_isinconsistent(issue_yearkey=None, issue_monthkey=None, issue_daykey=None, year=None, month=None, day=None, issue_convertdatetype=None):

#    if (month is None) and (day is None):
#        return None, None, None, None

#    Nyear = len(year)
#    if (month is not None) and (len(month) != Nyear):
#        raise Exception(f'`convertdatetype.py` | `year` and `month` must have the same length (`year`:{Nyear}, `month`:{len(month)})')
#    if (month is None) and (day is not None):
#        raise Exception(f"`convertdatetype.py` | `day` is not None, but `month` is. Please either assign a value to `month` or set `day` to None.")
#    if (day is not None) and (len(day) != Nyear):
#        raise Exception(f'`convertdatetype.py` | `year`, `month` and `day` must have the same length (`year`:{Nyear}, `month`:{len(month)}, `day`:{len(day)})')
#    if (year is not None) and (issue_yearkey is None):
#        raise Exception('`convertdatetype.py` | Please specify a value for `issue_yearkey`')
#    if (month is not None) and (issue_monthkey is None):
#        raise Exception('`convertdatetype.py` | Please specify a value for `issue_monthkey`')
#    if (day is not None) and (issue_daykey is None):
#        raise Exception('`convertdatetype.py` | Please specify a value for `issue_daykey`')

#    if (issue_convertdatetype is None):
#        issue_convertdatetype = pd.Series([pd.NA]*len(year))

#    if month is not None:
#        yearmonth_inconsistency = pd.isnull(year) & (~pd.isnull(month))
#        month[yearmonth_inconsistency] = pd.NA
#        issue_convertdatetype = modify_issue_convertdatetype(issue_convertdatetype, subset=yearmonth_inconsistency, issue=f'{issue_yearkey.upper()}_{issue_monthkey.upper()}_INCONSISTENT')

#    if day is not None:
#        yearday_inconsistency = pd.isnull(year) & (~pd.isnull(day))
#        monthday_inconsistency = pd.isnull(month) & (~pd.isnull(day))
#        day[yearday_inconsistency] = pd.NA
#        day[monthday_inconsistency] = pd.NA
#        issue_convertdatetype = modify_issue_convertdatetype(issue_convertdatetype, yearday_inconsistency, f'{issue_yearkey.upper()}_{issue_daykey.upper()}_INCONSISTENT')
#        issue_convertdatetype = modify_issue_convertdatetype(issue_convertdatetype, monthday_inconsistency, f'{issue_monthkey.upper()}_{issue_daykey.upper()}_INCONSISTENT')

#    issue_convertdatetype = issue_convertdatetype.astype('string')

#    return month, day, issue_convertdatetype

def apply(df, datekey=None, yearkey=None, monthkey=None, daykey=None, format='ISO8601', drop_inconsistent=True, drop_ambiguous=False, drop_empty=False):

    if (datekey is None) and (yearkey is None) and (monthkey is None) and (daykey is None):
        print('            INFO | No column specified, the dataframe is returned as is.')
        # VÉRIFIER CRÉATION COLONNES !!
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

#    # Store available year, month, and day values

#    if yearkey is not None:
#        year = df[yearkey].copy()
#    if monthkey is not None:
#        month = df[monthkey].copy()
#    if daykey is not None:
#        day = df[daykey].copy()
#    else:
#        day = None

    # Verify hierarchical consistency:
    # - if the month is present, the year must also be present
    # - if the day is present, both year and month must be present

#    if (monthkey is not None):

#        params = {
#                  'issue_yearkey' : yearkey,
#                  'issue_monthkey' : monthkey,
#                  'issue_daykey' : daykey,
#                  'year' : year.copy(),
#                  'month' : month.copy(),
#                  'day': day.copy(),
#                 }

#        if (daykey is None):
#            df[monthkey], _, df['issue_convertdatetype'] = update_issue_convertdatetype_isinconsistent(**params)
#        else:
#            df[monthkey], df[daykey], df['issue_convertdatetype'] = update_issue_convertdatetype_isinconsistent(**params)

#    drop_columns = []
#    if yearkey is not None:
#        df[f'{yearkey}_temp'] = df[yearkey].copy()
#        dropcolumns.append(f'{yearkey}_temp')
#    if monthkey is not None:
#        df[f'{monthkey}_temp'] = df[monthkey].copy()
#        dropcolumns.append(f'{monthkey}_temp')

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
#        yearmonth_inconsistency = pd.isnull(df[f'{yearkey}_temp']) & (~pd.isnull(df[f'{monthkey}_temp']))
#        df.loc[yearmonth_inconsistency,monthkey] = pd.NA
#        df = create_issue_convertdatetype(df)
        df = modify_issue_convertdatetype(df, f'{baseyearkey}_{basemonthkey}_INCONSISTENT', yearmonth_inconsistency)
    if daykey is not None:
        yearday_inconsistency = pd.isnull(df[yearkey]) & (~pd.isnull(df[daykey]))
        monthday_inconsistency = pd.isnull(df[monthkey]) & (~pd.isnull(df[daykey]))
#        yearday_inconsistency = pd.isnull(df[f'{yearkey}_temp']) & (~pd.isnull(df[daykey]))
#        monthday_inconsistency = pd.isnull(df[f'{monthkey}_temp']) & (~pd.isnull(df[daykey]))
#        df.loc[yearday_inconsistency,daykey] = pd.NA
#        df.loc[monthday_inconsistency,daykey] = pd.NA
#        df = create_issue_convertdatetype(df)
        df = modify_issue_convertdatetype(df, f'{baseyearkey}_{basedaykey}_INCONSISTENT', yearday_inconsistency)
        df = modify_issue_convertdatetype(df, f'{basemonthkey}_{basedaykey}_INCONSISTENT',  monthday_inconsistency)

    if drop_inconsistent:
        if monthkey is not None:
            df.loc[yearmonth_inconsistency,monthkey] = pd.NA
        if daykey is not None:
            df.loc[yearday_inconsistency,daykey] = pd.NA
            df.loc[monthday_inconsistency,daykey] = pd.NA

#    df.drop(columns=drop_columns, inplace=True)

    # Convert the year, month, and day columns to integers

    if yearkey is not None:
        df = convert_year(df, yearkey, drop_ambiguous=drop_ambiguous, drop_empty=drop_empty)
    if monthkey is not None:
        df = convert_month(df, monthkey, drop_empty=drop_empty)
#        if drop_inconsistent:
#            df.loc[pd.isnull(df[yearkey]),monthkey] = pd.NA
    if daykey is not None:
        df = convert_day(df, daykey, drop_empty=drop_empty)
#        if drop_inconsistent:
#            df.loc[pd.isnull(df[yearkey]),daykey] = pd.NA
#            df.loc[pd.isnull(df[monthkey]),daykey] = pd.NA

   # Ensure hierarchical consistency

    if drop_inconsistent:
       if monthkey is not None:
           df.loc[pd.isnull(df[yearkey]),monthkey] = pd.NA
       if daykey is not None:
           df.loc[pd.isnull(df[yearkey]),daykey] = pd.NA
           df.loc[pd.isnull(df[monthkey]),daykey] = pd.NA

    return df
