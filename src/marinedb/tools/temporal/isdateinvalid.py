#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
import warnings

# Internal import

from marinedb.tools import getcolumnname

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

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

def isdatevalid(df, yearkey, monthkey, daykey, flag=False):

    if flag:

        columns = list(df.columns)
        baseyearkey = get_basekey(yearkey, columns)
        basemonthkey = get_basekey(monthkey, columns)
        basedaykey = get_basekey(daykey, columns)

        flags = pd.Series([pd.NA]*len(df), index=df.index)
        flags = flags.astype('string')

    ismissing = (pd.isnull(df[yearkey]) | pd.isnull(df[monthkey])).astype('bool')
    isdatevalid = ismissing

    # Nonexistent month
    ismonthvalid = (df.loc[~ismissing, monthkey] <= 12).astype('bool')
    with warnings.catch_warnings():
        warnings.simplefilter(action='ignore', category=FutureWarning)
        isdatevalid[~ismissing] = ismonthvalid
    if flag:
        flags[ismonthvalid[~ismonthvalid].index] = f'{basemonthkey}_INVALID'

    # Nonexistent date
    maxdaybymonth = pd.Series([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])

    ismissing = (pd.isnull(df[yearkey]) | pd.isnull(df[monthkey]) | pd.isnull(df[daykey])).astype('bool')
    condition = (~ismissing) & ismonthvalid
    isdayvalid = (df.loc[condition,daykey] <= maxdaybymonth[df.loc[condition,monthkey]].set_axis(df.loc[condition,:].index))
    isdatevalid[condition] = isdayvalid
    if flag:
        flags[isdayvalid[~isdayvalid].index] = f'{baseyearkey}_{basemonthkey}_{basedaykey}_COMBINATION_INVALID'

    # Leap years with 29 days in February
    isleapyear = (df[yearkey]%4 == 0) & ((df[yearkey]%100 != 0) | (df[yearkey]%400 == 0))
    condition = (~ismissing) & isleapyear & (df[monthkey] == 2)
    isdayvalid = (df.loc[condition,daykey] <= 29)
    isdatevalid[condition] = isdayvalid
    if flag:
        flags[isdayvalid[~isdayvalid].index] = f'{baseyearkey}_{basemonthkey}_{basedaykey}_COMBINATION_INVALID'
        flags[isdayvalid[isdayvalid].index] = pd.NA

    isdatevalid = isdatevalid.astype('boolean')

    if flag:
        return isdatevalid, flags
    else:
        return isdatevalid

@export
def apply(df, datekey=None, yearkey=None, monthkey=None, daykey=None, flag=False, dropna=False, verbose=True, indent=''):
    """Detect or exclude invalid occurrence dates.

    Validate either a standardized date column or separate year, month, and day
    columns. The function detects incorrectly formatted values, nonexistent
    calendar dates, and hierarchical inconsistencies between separate date
    components.

    When both ``datekey`` and all three component columns are provided, validation
    is performed from the year, month, and day columns and ``datekey`` is ignored.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        datekey (str, optional):
            Name of the column containing dates to validate.

            Non-missing values must follow one of the forms ``YYYY``, ``YYYY-MM``,
            or ``YYYY-MM-DD``.

        yearkey (str, optional):
            Name of the column containing year values.

            To validate separate date components, ``yearkey``, ``monthkey``, and
            ``daykey`` must all be provided.

        monthkey (str, optional):
            Name of the column containing month values.

            To validate separate date components, ``yearkey``, ``monthkey``, and
            ``daykey`` must all be provided.

        daykey (str, optional):
            Name of the column containing day values.

            To validate separate date components, ``yearkey``, ``monthkey``, and
            ``daykey`` must all be provided.

        flag (bool, optional):
            Whether to annotate or exclude invalid records.

            If ``True``, all records are retained and a Boolean flag column is
            created. If ``False``, invalid records are removed.

        dropna (bool, optional):
            Whether to treat missing dates as invalid.

            When separate components are validated, a missing year followed by a
            month or a missing month followed by a day is always considered
            invalid because it breaks temporal hierarchy.

    Returns:
        (pandas.DataFrame):
            Processed DataFrame with invalid records flagged or excluded.

    Raises:
        ValueError:
            If neither ``datekey`` nor all of ``yearkey``, ``monthkey``, and
            ``daykey`` are provided.

    Note:
        - Year-only and year–month values are accepted when their formats and
        available components are valid. Complete dates are checked against the
        calendar, including leap years.

        - When ``flag=True``, the generated column is named
        ``flag_<DATE_COLUMN>_isdateinvalid`` when validating ``datekey``, or
        ``flag_<YEAR_COLUMN>_<MONTH_COLUMN>_<DAY_COLUMN>_isdateinvalid`` when
        validating separate components.

        - Invalid formats trigger a warning recommending the temporal curation
        workflow, which standardizes date values and checks their validity 
        during processing.
    """

    isdate = (datekey is not None)
    isdatecomponents = (yearkey is not None) and (monthkey is not None) and (daykey is not None)
    if (not isdate) and (not isdatecomponents):
        raise ValueError(f'`isdateinvalid.py` | Either `datekey` or `yearkey`, `monthkey` and `daykey` must be specified')
    if isdate and isdatecomponents:
        printv(f"INFO | Since `yearkey`, `monthkey` and `daykey` is provided ('{yearkey}', '{monthkey}', '{daykey}'), `datekey` will be ignored ('{datekey}')", verbose=verbose, indent=indent)
        datekey = None
        isdate = False

    if isdate:
        df, datekey, _ = getcolumnname.apply(df, datekey, '', inplace=True)
    else:
        df, yearkey, _ = getcolumnname.apply(df, yearkey, '', inplace=True)
        df, monthkey, _ = getcolumnname.apply(df, monthkey, '', inplace=True)
        df, daykey, _ = getcolumnname.apply(df, daykey, '', inplace=True)

    # Missing dates

    if isdate:
        ismissing = pd.isnull(df[datekey])
    else:
        ismissing = pd.isnull(df[yearkey])
    ismissing = ismissing.astype('bool')
    isdateinvalid = ismissing.copy()
    isdateinvalid[ismissing] = dropna

    # Incorrectly formatted dates

    if isdate:
        ## Date
        subset = (~ismissing)
        isformatvalid = df.loc[subset, datekey].str.fullmatch(r'[0-9]{4}(-[0-9]{2}){0,2}').astype('bool')
        isdateinvalid.loc[subset & (~isformatvalid)] = True
        if (~isformatvalid).any():
            example = df.loc[subset & (~isformatvalid), datekey].iloc[0]
            nobs = len(df[subset & (~isformatvalid)])
            printv(f"WARNING | Invalid date formats found ({nobs} observations ; e.g., '{example}'). Run `temporal.py` or `parsedate.py` to correct them where possible.", verbose=verbose, indent=indent)
    else:
        ## Year, Month & Day
        isinconsistent = (ismissing & (~pd.isnull(df[monthkey]))) | (pd.isnull(df[monthkey]) & (~pd.isnull(df[daykey])))
        isdateinvalid.loc[isinconsistent] = True
        ## Year
        subset = (~ismissing)
        isformatvalid = df.loc[subset, yearkey].astype('str').str.fullmatch(r'[0-9]{4}(\.0*)?').astype('bool')
        isdateinvalid.loc[subset & (~isformatvalid)] = True
        if (~isformatvalid).any():
            example = df.loc[subset & (~isformatvalid), yearkey].iloc[0]
            nobs = len(df[subset & (~isformatvalid)])
            printv(f"WARNING | Invalid year formats found ({nobs} observations ; e.g., '{example}'). Run `temporal.py` or `convertdatetype.py` to correct them where possible.", verbose=verbose, indent=indent)
        ## Month
        subset = subset & (~pd.isnull(df[monthkey]))
        isformatvalid = df.loc[subset, monthkey].astype('str').str.fullmatch(r'[0-9]{1,2}(\.0*)?').astype('bool')
        isdateinvalid.loc[subset & (~isformatvalid)] = True
        if (~isformatvalid).any():
            example = df.loc[subset & (~isformatvalid), monthkey].iloc[0]
            nobs = len(df[subset & (~isformatvalid)])
            printv(f"WARNING | Invalid month formats found ({nobs} observations ; e.g., '{example}'). Run `temporal.py` or `convertdatetype.py` to correct them where possible.", verbose=verbose, indent=indent)
        ## Day
        subset = subset & (~pd.isnull(df[daykey]))
        isformatvalid = df.loc[subset, daykey].astype('str').str.fullmatch(r'[0-9]{1,2}(\.0*)?').astype('bool')
        isdateinvalid.loc[subset & (~isformatvalid)] = True
        if (~isformatvalid).any():
            example = df.loc[subset & (~isformatvalid), daykey].iloc[0]
            nobs = len(df[subset & (~isformatvalid)])
            printv(f"WARNING | Invalid day formats found ({nobs} observations ; e.g., '{example}'). Run `temporal.py` or `convertdatetype.py` to correct them where possible.", verbose=verbose, indent=indent)


    # Nonexistent dates

    subset = (~ismissing) & (~isdateinvalid)
    yearkeytemp, monthkeytemp, daykeytemp = 'TEMPORARYYEAR','TEMPORARYMONTH','TEMPORARYDAY'
    tempcol = [yearkeytemp, monthkeytemp, daykeytemp]

    if isdate:
        date_split = df.loc[subset, datekey].str.split('-')
        df.loc[subset, yearkeytemp] = date_split.str[0][subset].astype('Float64').astype('Int64')
        df.loc[subset, monthkeytemp] = date_split.str[1][subset].astype('Float64').astype('Int64')
        df.loc[subset, daykeytemp] = date_split.str[2][subset].astype('Float64').astype('Int64')

        isdatecomplete = subset & (date_split.str.len() >= 2)

    else:
        df.loc[subset, yearkeytemp] = df.loc[subset, yearkey].astype('float').astype('int')
        df.loc[subset, monthkeytemp] = df.loc[subset, monthkey].astype('Float64').astype('Int64')
        df.loc[subset, daykeytemp] = df.loc[subset, daykey].astype('Float64').astype('Int64')

        isdatecomplete = subset & (~pd.isnull(df.loc[subset, monthkeytemp]))

    isdateinvalid[isdatecomplete] = (~isdatevalid(df[isdatecomplete], yearkeytemp, monthkeytemp, daykeytemp))

    df.drop(columns=tempcol, inplace=True)

    if flag:
        # Flag rows where dates are:
        #   - missing if `dropna`
        #   - incorrectly formatted
        #   - or invalid
        if isdate:
            flagname = f'flag_{datekey}_isdateinvalid'
        else:
            flagname = f'flag_{yearkey}_{monthkey}_{daykey}_isdateinvalid'
        df[flagname] = isdateinvalid
        df[flagname] = df[flagname].astype('bool')
        return df
    else:
        # Drop rows where dates are:
        #   - missing if `dropna`
        #   - incorrectly formatted
        #   - or invalid
        return df[~isdateinvalid].reset_index(drop=True)
