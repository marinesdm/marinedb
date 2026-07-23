#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
import numpy as np
import os
import re

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname, modifyissuecolumn
from marinedb.tools.temporal import convertdatetype
from marinedb.tools.temporal import processdateinterval

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

def clean(df, yearkey, monthkey, daykey, datekeyout, issuekey, split, columns_to_drop=None, drop_empty=False, drop_mismatch=True, verbose=True, indent=''):

    # Drop columns

    if columns_to_drop is None:
        columns_to_drop = []

    if drop_empty:
        printv(f'INFO | Only non-empty generated columns will be returned', verbose=verbose, indent=indent)
        # i.e., the dataframe can be returned as is
        if pd.isnull(df[yearkey]).all():
            columns_to_drop += [yearkey]
        if pd.isnull(df[monthkey]).all():
            columns_to_drop += [monthkey]
        if pd.isnull(df[daykey]).all():
            columns_to_drop += [daykey]
        if pd.isnull(df[issuekey]).all():
            columns_to_drop += [issuekey]
        if drop_mismatch and pd.isnull(df[datekeyout]).all():
            columns_to_drop += [datekeyout]

    df.drop(columns=columns_to_drop, inplace=True)

    # Convert dtypes

    try:

        df[yearkey] = df[yearkey].astype('Int64')
        df[monthkey] = df[monthkey].astype('Int64')
        df[daykey] = df[daykey].astype('Int64')

    except ValueError as error:

        if split == 'interval':
            printv(f"INFO | Failed to convert `{yearkey}`, `{monthkey}` and `{daykey}` to integers (type='{split}'). Converting to strings instead.", verbose=verbose, indent=indent)
            df[yearkey] = df[yearkey].astype('string')
            df[monthkey] = df[monthkey].astype('string')
            df[daykey] = df[daykey].astype('string')
        else:
            raise ValueError('`splitdate.py` | ' + error)

    issuekeys = [col for col in df.columns if 'issue' in col]
    df[issuekeys] = df[issuekeys].astype('string')

    return df

def call_processdateinterval(df, datekey, drop_interval, strategy='overlap', maxinterval_number=1, maxinterval_level='years', verbose=True, indent=''):

    # Warning :
    # If the function is applied to a DataFrame that lacks 'flag_{basedatekey}_dateinterval' column,
    # `processdateinterval.py` will be executed, regardless of whether date intervals have already been processed

    basedatekey = datekey.split('_processedby_')[0]

    # Check if the `datekey` column has already been processed by `processdateinterval`

    flagname = f'flag_{basedatekey}_isdateinterval'
    if ('processdateinterval' in datekey) and (flagname not in df.columns):

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
            df[flagname] = processdateinterval.isdateinterval(df, previouscolumnversion)
        else:
            ## No remaining date intervals, with no way to determine prior existence
            df[flagname] = False

    if flagname not in df.columns:

        # Process date intervals

        printv(f'* Apply `processdateinterval` to {basedatekey}', verbose=verbose, indent=indent)

        params = {
                   'drop_interval': drop_interval,
                   'strategy': strategy,
                   'maxinterval_number': maxinterval_number,
                   'maxinterval_level': maxinterval_level,
                   'inplace': False,
                   'flag': True,
                   'verbose': verbose,
                   'indent': indent + '  '
                 }

        df = processdateinterval.apply(df, datekey, **params)

    # Column name for futher processing

    colstart = f'{basedatekey}_processedby'
    datekeyin = [col for col in df.columns if col.startswith(colstart) and ('processdateinterval' in col)]
    if len(datekeyin) > 1:
        raise Exception(f"`splitdate.py` | Mutiple column names contain '{colstart}' and 'processdateinterval': {datekeyin}. An issue may have occurred during execution.")
    elif len(datekeyin) == 1:
        datekeyin = datekeyin[0]
    else:
        # `processdateinterval` has been called with inplace=True
        datekeyin = datekey

    printv('', verbose=verbose)

    return df, datekeyin

@export
def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, split='all', drop_interval=False, drop_mismatch=True, drop_empty=False, inplace_components=False, inplace_date=False, flag=True, strategy='overlap', maxinterval_number=1, maxinterval_level='years', verbose=True, indent=''):
    """Extract and reconcile year, month, and day components from dates.

    Extract temporal components from ``datekey`` and compare them with the values
    stored in any year, month, or day columns already present in the input data.
    Existing component columns are first standardized and validated, including
    checks for invalid values, invalid calendar dates, and hierarchical
    inconsistencies.

    When extracted components disagree with existing values, the function either
    removes the inconsistent components or gives precedence to the values extracted
    from ``datekey``. Detected inconsistencies are recorded in an issue column.

    Date intervals are processed before component extraction. If
    ``processdateinterval`` has already been applied and its interval flag is
    available, the existing results are reused. Otherwise, interval processing is
    performed using ``drop_interval``, ``strategy``, ``maxinterval_number``, and
    ``maxinterval_level``.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        datekey (str):
            Name of the column containing the standardized dates or date intervals
            from which temporal components are extracted.

        yearkey (str, optional):
            Name of an existing year column to compare with the year extracted from
            ``datekey``.

            If omitted, a new ``year_generatedby_splitdate`` column is created.
            ``yearkey`` is required when ``monthkey`` is provided.

        monthkey (str, optional):
            Name of an existing month column to compare with the month extracted
            from ``datekey``.

            If omitted, a new ``month_generatedby_splitdate`` column is created.
            ``monthkey`` is required when ``daykey`` is provided.

        daykey (str, optional):
            Name of an existing day column to compare with the day extracted from
            ``datekey``.

            If omitted, a new ``day_generatedby_splitdate`` column is created.

        split (str, optional):
            Scope of date-component extraction. Accepted values are: 

            - ``"all"`` to extract components from all dates
            - ``"interval"`` to extract components only for records whose original
              date is an interval.

        drop_interval (bool, optional):
            Whether to replace date intervals with missing values instead of
            collapsing them.

            If ``True``, the corresponding year, month, and day values are also set
            to missing.

            If ``False``, intervals are first collapsed according to ``strategy``.

        drop_mismatch (bool, optional):
            Strategy used when components extracted from ``datekey`` disagree with
            corresponding values in existing year, month, or day columns.

            If ``True``, inconsistent components are removed from both the processed
            date and component columns. Dependent components are also removed to
            preserve temporal hierarchy: a year mismatch removes year, month, and
            day; a month mismatch removes month and day; and a day mismatch removes
            only the day.

            If ``False``, the values extracted from ``datekey`` are retained and
            written to the processed component columns, giving precedence to the
            date field.

        inplace_components (bool, optional):
            Whether to overwrite existing year, month, and day columns.

            If ``False``, the processed values are written to new component columns.

        inplace_date (bool, optional):
            Whether to overwrite the date column when mismatches with existing
            year, month, or day values are resolved.

            This argument has an effect only when ``drop_mismatch=True``.

        flag (bool, optional):
            Whether to retain the date-interval flag and interval-width columns
            generated during interval processing.

        strategy (str, optional):
            Strategy used to collapse date intervals before component extraction when
            interval processing is required. Accepted values are ``"start"``, ``"end"``, 
            and ``"overlap"``.

        maxinterval_number (int, optional):
            Maximum interval width allowed with the ``"start"`` and ``"end"``
            strategies.

            Intervals exceeding this limit are replaced with missing values. Use
            ``-1`` to process intervals regardless of their width.

        maxinterval_level (str, optional):
            Unit used with ``maxinterval_number``. Accepted values are
            ``"days"``, ``"months"``, and ``"years"``.

    Returns:
        (pandas.DataFrame):
            Processed DataFrame containing the extracted temporal components,
            reconciled date values, and any retained issue or interval-annotation
            columns.

    Raises:
        ValueError:
            If ``split`` is not ``"all"`` or ``"interval"``.

        Exception:
            If ``monthkey`` is provided without ``yearkey``, or if ``daykey`` is
            provided without ``monthkey``.

        Exception:
            If a generated year, month, or day column name conflicts with an
            existing column.

    Note:
        - Temporal hierarchy is preserved in the output: a month is retained only
        when a year is available, and a day only when both a year and a month are
        available.

        - When ``split="all"``, detected inconsistencies are recorded in
        ``issue_splitdate``. When ``split="interval"``, they are recorded in
        ``issue_splitdateinterval``.

        - Giving precedence to ``datekey`` when ``drop_mismatch=False`` is a
        design choice and does not imply that the date field is inherently
        more reliable than the separate component fields.
    """

#    drop_empty (bool, optional):
#        Whether to remove generated output or issue columns when they contain
#        only missing values.
#
#        Empty component columns are removed only when they were generated by
#        the function rather than supplied as existing columns.

    # Verifications

    if split not in ['all','interval']:
        raise ValueError(f"`splitdate.py` | `split` must be 'all' or 'interval'")

    if (monthkey is not None) and (yearkey is None):
        raise Exception(f"`splitdate.py` | yearkey={yearkey} but monthkey='{monthkey}'. Please assign a value to `yearkey` or set `monthkey` to None.")
    if (daykey is not None) and (monthkey is None):
        raise Exception(f"`splitdate.py` | monthkey={monthkey} but daykey='{daykey}'. Please assign a value to `monthkey` or set `daykey` to None.")

    # Set up

    columns = list(df.columns)
    yearmodulename = 'splitdate'
    monthmodulename = 'splitdate'
    daymodulename = 'splitdate'
    yearinplace = inplace_components
    monthinplace = inplace_components
    dayinplace = inplace_components

    if (yearkey is None):
        yearkey = 'year_generatedby_splitdate'
        yearmodulename = ''
        yearinplace = True
        keyin = [col for col in columns if yearkey in col]
        doeskeyexist = (len(keyin) > 0)
        if doeskeyexist:
            raise Exception(f'`splitdate.py` | {yearkey} found in {",".join(keyin)} columns')
    if (monthkey is None):
        monthkey = 'month_generatedby_splitdate'
        monthmodulename = ''
        monthinplace = True
        keyin = [col for col in columns if monthkey in col]
        doeskeyexist = (len(keyin) > 0)
        if doeskeyexist:
            raise Exception(f'`splitdate.py` | {monthkey} found in {",".join(keyin)} columns')
    if (daykey is None):
        daykey = 'day_generatedby_splitdate'
        daymodulename = ''
        dayinplace = True
        keyin = [col for col in columns if daykey in col]
        doeskeyexist = (len(keyin) > 0)
        if doeskeyexist:
            raise Exception(f'`splitdate.py` | {daykey} found in {",".join(keyin)} columns')

    df, datekey, datekeyout = getcolumnname.apply(df, datekey, '', inplace=True, minimize_columns=False)
    df, yearkey, yearkeyout = getcolumnname.apply(df, yearkey, yearmodulename, inplace=yearinplace)
    df, monthkey, monthkeyout = getcolumnname.apply(df, monthkey, monthmodulename, inplace=monthinplace)
    df, daykey, daykeyout = getcolumnname.apply(df, daykey, daymodulename, inplace=dayinplace)

    issuekey = ('issue_splitdate' if (split == 'all') else 'issue_splitdateinterval')
    df[issuekey] = pd.NA
    columns = list(df.columns)

    processdateinterval_params = {
                                  'drop_interval': drop_interval,
                                  'strategy': strategy,
                                  'maxinterval_number': maxinterval_number,
                                  'maxinterval_level': maxinterval_level
                                  }

    df, datekey = call_processdateinterval(df, datekey, **processdateinterval_params, verbose=verbose, indent=indent)

    if drop_mismatch:
        df, datekey, datekeyout = getcolumnname.apply(df, datekey, 'splitdate', inplace=inplace_date, minimize_columns=False)
        if not inplace_date:
            df[datekeyout] = df[datekey].copy()

    printv(f'* Split into year/month/day when known', verbose=verbose, indent=indent)

    baseyearkey = get_basekey(yearkey, columns)
    basemonthkey = get_basekey(monthkey, columns)
    basedaykey = get_basekey(daykey, columns)
    basedatekey = datekey.split('_processedby_')[0]

    flagcolumn = f'flag_{basedatekey}_isdateinterval'
    assert (flagcolumn in df.columns)
    intervalcolumns = list(set(df.columns) - set(columns))
    intervalcolumns = [col for col in intervalcolumns if ('issue_' not in col)]

    # Select the dates to process
    # split='all': all dates
    # split='interval': date intervals only

    if split == 'interval':
        process = df[flagcolumn]
    else:
        process = pd.Series([True]*len(df), index=df.index)

    # Prepare the columns for storing results
    # inplace_components=True: replace `yearkey`/`monthkey`/`daykey` if the columns already exist
    # inplace_components=False: create new columns to avoid overwriting data in existing columns

    isyear = (yearkey in columns)
    ismonth = (monthkey in columns)
    isday = (daykey in columns)

    ## Preprocess and store available year, month, and day values

    if isyear:

        params = {
                   'yearkey': yearkey,
                   'monthkey': monthkey,
                   'daykey': daykey,
                   'drop_inconsistent': False,
                   'drop_ambiguous': False,
                   'drop_empty': False,
                   'verbose': False,
                   'indent': indent
                 }

        convertdf = convertdatetype.apply(df[[yearkey,monthkey,daykey]].copy(), **params)

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

    if not isyear:
        df[yearkeyout] = pd.NA
    if not ismonth:
        df[monthkeyout] = pd.NA
    if not isday:
        df[daykeyout] = pd.NA

    if isday or ismonth or isyear:

        if inplace_components:

            print_columns = np.array([f"`{daykey.split('_processedby_')[0]}`", f"`{monthkey.split('_processedby_')[0]}`", f"`{yearkey.split('_processedby_')[0]}`"])[[isday, ismonth, isyear]]
            if split == 'all':
                printv(f"WARNING | {', '.join(print_columns)} column(s) already exist(s) and will be overwritten", verbose=verbose, indent=indent)
            if split == 'interval':
                printv(f"WARNING | {', '.join(print_columns)} column(s) already exist(s) and will be overwritten for date intervals", verbose=verbose, indent=indent)

        else:

            if isyear:
                df[yearkeyout] = df[yearkey].copy()
            if ismonth:
                df[monthkeyout] = df[monthkey].copy()
            if isday:
                df[daykeyout] = df[daykey].copy()

    df[yearkeyout] = df[yearkeyout].astype('string')
    df[monthkeyout] = df[monthkeyout].astype('string')
    df[daykeyout] = df[daykeyout].astype('string')

    isoutputcolumnsgenerated = (not inplace_components) or ((not isday) and (not ismonth) and (not isyear))
    drop_empty = (drop_empty and isoutputcolumnsgenerated)

    printv(f"INFO | daykey='{daykeyout}', monthkey='{monthkeyout}', yearkey='{yearkeyout}'", verbose=verbose, indent=indent)

    if (split == 'interval') and (~df[flagcolumn]).all():

        # No date interval

        printv(f"INFO | split='{split}', but no date intervals were found", verbose=verbose, indent=indent)

        if flag:
            columns_to_drop = None
        else:
            columns_to_drop = intervalcolumns

        params = {
                   'split': split,
                   'columns_to_drop': columns_to_drop,
                   'drop_empty': drop_empty,
                   'drop_mismatch': drop_mismatch,
                   'verbose': verbose,
                   'indent': indent
                 }

        df = clean(df, yearkeyout, monthkeyout, daykeyout, datekeyout, issuekey, **params)

        return df

    if (split == 'interval') and drop_interval:

        # Replace year, month and day values with NaN for interval dates

        if isyear:
            df.loc[process,yearkeyout] = pd.NA
        if ismonth:
            df.loc[process,monthkeyout] = pd.NA
        if isday:
            df.loc[process,daykeyout] = pd.NA

        # Clean

        if flag:
            columns_to_drop = None
        else:
            columns_to_drop = intervalcolumns

        params = {
                   'split': split,
                   'columns_to_drop': columns_to_drop,
                   'drop_empty': drop_empty,
                   'drop_mismatch': drop_mismatch,
                   'verbose': verbose,
                   'indent': indent
                 }

        df = clean(df, yearkeyout, monthkeyout, daykeyout, datekeyout, issuekey, **params)

        return df

    # Split date into year, month & day

    date_split = df.loc[process,datekey].str.split('-')

    df.loc[process,yearkeyout] = date_split.str[0][process].astype('string')
    df.loc[process,monthkeyout] = date_split.str[1][process].astype('string')
    df.loc[process,daykeyout] = date_split.str[2][process].astype('string')

    # Handle date intervals

    if drop_interval:
        df.loc[df[flagcolumn],yearkeyout] = pd.NA
        df.loc[df[flagcolumn],monthkeyout] = pd.NA
        df.loc[df[flagcolumn],daykeyout] = pd.NA

    df[yearkeyout] = df[yearkeyout].astype('string')
    df[monthkeyout] = df[monthkeyout].astype('string')
    df[daykeyout] = df[daykeyout].astype('string')

    # Identify mismatches between the extracted components and the existing
    # year, month, and day values

    if isyear:
        ismissing = (pd.isnull(df[yearkeyout]) | pd.isnull(year))
        isfourdigit = (year.str.len() == 4)
        # four-digit years
        condition = (~ismissing) & isfourdigit & process
        isyearmismatch = (df.loc[condition,yearkeyout] != year[condition])
        isyearmismatch = list(isyearmismatch[isyearmismatch].index)
        # one-digit years or two-digit years
        condition = (~ismissing) & (~isfourdigit) & process
        refyear = year[condition].astype('string')
        mapindex = list(refyear.index)
        isyearmismatch += [mapindex[idx] for idx,y in enumerate(refyear) if (y != df.loc[mapindex[idx],yearkeyout][-2:])]
        df = modifyissuecolumn.apply(df, issuekey, f'{baseyearkey}_MISMATCH', subset=isyearmismatch)

    if ismonth:
        ismissing = (pd.isnull(df[monthkeyout]) | pd.isnull(month))
        ismonthmismatch = (df.loc[(~ismissing) & process,monthkeyout] != month[(~ismissing) & process])
        ismonthmismatch = ismonthmismatch[ismonthmismatch].index
        df = modifyissuecolumn.apply(df, issuekey, f'{basemonthkey}_MISMATCH', subset=ismonthmismatch)

    if isday:
        ismissing = (pd.isnull(df[daykeyout]) | pd.isnull(day))
        isdaymismatch = (df.loc[(~ismissing) & process,daykeyout] != day[(~ismissing) & process])
        isdaymismatch = isdaymismatch[isdaymismatch].index
        df = modifyissuecolumn.apply(df, issuekey, f'{basedaykey}_MISMATCH', subset=isdaymismatch)

    if drop_mismatch:

        # Remove mismatched components from both the processed date and the
        # component output columns while preserving temporal hierarchy

        if isyear:
            df.loc[isyearmismatch,[yearkeyout,monthkeyout,daykeyout]] = pd.NA
            df.loc[isyearmismatch,datekeyout] = pd.NA
        if ismonth:
            df.loc[ismonthmismatch,[monthkeyout,daykeyout]] = pd.NA
            df.loc[ismonthmismatch,datekeyout] = df.loc[ismonthmismatch,datekey].str.split('-').str[0]
        if isday:
            df.loc[isdaymismatch,daykeyout] = pd.NA
            df.loc[isdaymismatch,datekeyout] = df.loc[isdaymismatch,datekey].str.split('-').str[:2].str.join('-')

    # Ensure hierarchical consistency:
    # - if year is missing, set month and day to NaN
    # - if month is missing, set day to NaN

    df.loc[process & pd.isnull(df[yearkeyout]),[monthkeyout,daykeyout]] = pd.NA
    df.loc[process & pd.isnull(df[monthkeyout]),daykeyout] = pd.NA

    # Clean

    if flag:
        columns_to_drop = None
    else:
        columns_to_drop = intervalcolumns

    params = {
               'split': split,
               'columns_to_drop': columns_to_drop,
               'drop_empty': drop_empty,
               'drop_mismatch': drop_mismatch,
               'verbose': verbose,
               'indent': indent
             }

    df = clean(df, yearkeyout, monthkeyout, daykeyout, datekeyout, issuekey, **params)

    printv('', verbose=verbose)

    return df
