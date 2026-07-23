#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
import warnings

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname
from marinedb.tools.temporal import convertdatetype

# Global variable

__all__ = [] # populated using the @export decorator

@export
def isdateinterval(df, datekey):

    flaginterval = pd.Series([False]*len(df), index=df.index)

    isdatemissing = pd.isnull(df[datekey])
    flaginterval[~isdatemissing] = df.loc[~isdatemissing,datekey].astype('string').str.contains('/')

    return flaginterval

def apply_strategy(df, key, index, strategy):

    if strategy == 'start':

        # Keep the start date

        df.loc[index,key] = df.loc[index,'start_str']

    elif strategy == 'end':

        # Keep the end date

        df.loc[index,key] = df.loc[index,'end_str']

    elif strategy == 'overlap':

        # Keep the overlapping portion

        df.loc[index,key] = pd.NA

        start_split = df.loc[index,'start_str'].str.split('-')
        end_split =  df.loc[index,'end_str'].str.split('-')

        year_start = start_split.str[0]
        month_start = start_split.str[1]
        day_start = start_split.str[2]

        year_end = end_split.str[0]
        month_end = end_split.str[1]
        day_end = end_split.str[2]

        ## Year overlap
        isyearmatch = (~pd.isnull(year_start)) & (~pd.isnull(year_end)) & (year_start == year_end)
        match_index = isyearmatch[isyearmatch].index
        df.loc[match_index, key] = year_start[match_index].astype(str)

        ## Month overlap
        ismonthmatch = isyearmatch & (~pd.isnull(month_start)) & (~pd.isnull(month_end)) & (month_start == month_end)
        match_index = ismonthmatch[ismonthmatch].index
        df.loc[match_index, key] = df.loc[match_index, key].astype(str) + '-' + month_start[match_index].astype(str)

        ## Day overlap
        isdaymatch = isyearmatch & ismonthmatch & (~pd.isnull(day_start)) & (~pd.isnull(day_end)) & (day_start == day_end)
        match_index = isdaymatch[isdaymatch].index
        df.loc[match_index, key] = df.loc[match_index, key].astype(str) + '-' + day_start[match_index].astype(str)

        df[key] = df[key].astype('string')

    else:
        raise ValueError(f"`processdateinterval.py` | `strategy` must be 'start', 'end' or 'overlap'")

    return df

@export
def apply(df, datekey, drop_interval=False, strategy='overlap', maxinterval_number=1, maxinterval_level='years', inplace=False, flag=True, drop_empty=False, verbose=True, indent=''):
    """Process occurrence-date intervals.

    Identify ISO 8601 date intervals in ``datekey`` and either replace them with
    missing values or collapse them to a single temporal value.

    Intervals can be collapsed by retaining their start date, retaining their end
    date, or preserving only the date components shared by both bounds. For the
    start and end strategies, processing can be restricted to intervals whose
    duration does not exceed a user-defined threshold. Intervals exceeding this
    limit are replaced with missing values.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        datekey (str):
            Name of the column containing the dates or date intervals to process.

            Values must follow the ISO 8601 forms ``YYYY``, ``YYYY-MM``, or
            ``YYYY-MM-DD``. Intervals must contain two bounds of equal precision
            separated by ``"/"``.

        drop_interval (bool, optional):
            Whether to replace all date intervals with missing values instead of
            collapsing them.

            When ``True``, ``strategy``, ``maxinterval_number``,
            ``maxinterval_level``, and ``flag`` are ignored.

        strategy (str, optional):
            Strategy used to collapse date intervals. Accepted values are:

            - ``"start"`` to retain the interval start;
            - ``"end"`` to retain the interval end;
            - ``"overlap"`` to retain only the date components shared by both
            bounds.

            For example, an interval whose bounds fall within the same year but
            different months is reduced to that year with ``"overlap"``.

            The interval-width limit is ignored when ``strategy="overlap"``.

        maxinterval_number (int, optional):
            Maximum interval width allowed with the ``"start"`` and ``"end"``
            strategies.

            Intervals exceeding this limit are replaced with missing values. Use
            ``-1`` to process intervals regardless of their width. A value of
            ``0`` is treated as ``1``.

        maxinterval_level (str, optional):
            Unit used with ``maxinterval_number``. Accepted values are
            ``"days"``, ``"months"``, and ``"years"``.

            This argument is ignored when ``strategy="overlap"`` or
            ``maxinterval_number=-1``.

        inplace (bool, optional):
            Whether to replace ``datekey`` with the processed values. If
            ``False``, the results are written to a new processed column.

        flag (bool, optional):
            Whether to retain the date-interval flag and interval-width columns.

            The flag column identifies records whose original date was an
            interval. Interval width is expressed in days.

            This argument is ignored when ``drop_interval=True``.

        drop_empty (bool, optional):
            Whether to remove generated annotation columns when they contain no
            values.

    Returns:
        (pandas.DataFrame):
            Processed DataFrame containing the resulting dates and any retained
            interval annotations.

    Raises:
        ValueError:
            If ``strategy`` is not ``"start"``, ``"end"``, or ``"overlap"``.

        ValueError:
            If ``maxinterval_number`` is less than ``-1``.

        ValueError:
            If ``maxinterval_level`` is not ``"days"``, ``"months"``, or
            ``"years"``.

        ValueError:
            If non-missing values in ``datekey`` do not follow the expected ISO
            8601 date or date-interval format.

        ValueError:
            If the two bounds of an interval do not have the same temporal
            precision.

    Note:
        - Partial interval bounds are converted internally to complete dates when
        calculating interval widths. Missing months and days are interpreted as
        January and the first day of the month, respectively.

        - Detected intervals are annotated in
        ``flag_<DATE_COLUMN>_isdateinterval``. When retained, their widths are
        stored in
        ``<DATE_COLUMN>_intervalwidth_generatedby_processdateinterval``.

        - Intervals that cannot be processed or exceed the selected limit are
        replaced with missing values and annotated in
        ``issue_processdateinterval``.
    """

    # a different strategy could be implemented (e.g. take the median date)

    # Verifications

    ## Parameters

    if strategy not in ['start','end', 'overlap']:
        raise ValueError(f"`processdateinterval.py` | `strategy` must be 'start', 'end' or 'overlap'")

    maxinterval_number = int(maxinterval_number)

    if (maxinterval_number < -1):
        raise ValueError(f'`processdateinterval.py` | `maxinterval_number` must be > -1, not {maxinterval_number}')
    if maxinterval_level not in ['years','months','days']:
        raise ValueError(f"`processdateinterval.py` | `maxinterval_level` must be 'years', 'months' or 'days', not '{maxinterval_level}'")

    if (strategy == 'overlap'):
        printv(f"INFO | Since strategy='{strategy}', maxinterval_number={maxinterval_number} and maxinterval_level='{maxinterval_level}' will be ignored", verbose=verbose, indent=indent)

    if drop_interval:
        flag = False
        printv(f"INFO | As drop_interval='{drop_interval}', `flag` will be ignored", verbose=verbose, indent=indent)

    df, datekey, datekeyout = getcolumnname.apply(df, datekey, 'processdateinterval', inplace=inplace, minimize_columns=False)
    if not inplace:
        df[datekeyout] = df[datekey].copy()

    basedatekey = datekey.split('_processedby_')[0]

    ## Date format

    pattern = r'([0-9]{4}(?:-[0-9]{2}){0,2})(?:/([0-9]{4}(?:-[0-9]{2}){0,2}))?'
    isformatrecognized = df[datekey].str.fullmatch(pattern)
    if not isformatrecognized.all():
        raise ValueError(f"`processdateinterval.py` | all dates should follow the 'YYYY[[-MM[-DD]]/YYYY[-MM[-DD]]]' format. Please use `parsedate.py` upstream to convert date strings to this valid format.")

    issymmetrical = df.loc[(~pd.isnull(df[datekey])),datekey].str.extract(pattern)
    issymmetrical = issymmetrical[(~pd.isnull(issymmetrical.iloc[:,1]))]
    issymmetrical = (issymmetrical.iloc[:,0].str.len() == issymmetrical.iloc[:,1].str.len())
    if not issymmetrical.all():
        raise ValueError(f'`processdateinterval.py` | all date intervals should be symmetrical, i.e., both dates must have the same precision')

    # Find intervals

    printv('', verbose=verbose)
    printv(f'* Find date intervals', verbose=verbose, indent=indent)

    flagname = f'flag_{basedatekey}_isdateinterval'
    df[flagname] = False
    df[flagname] = df[flagname].astype('boolean')

    isdatemissing = pd.isnull(df[datekey])
    df.loc[~isdatemissing,flagname] = df.loc[~isdatemissing,datekey].astype('string').str.contains('/') # interval format: YYYY[-MM[-DD]]/YYYY[-MM[-DD]]

    df['issue_processdateinterval'] = pd.NA

    if (~df[flagname]).all() and (not drop_interval):

        # No interval

        drop_interval = True

    if drop_interval:

        # Delete date intervals

        df.loc[df[flagname],datekeyout] = pd.NA
        df[datekeyout] = df[datekeyout].astype('string')

        dropcolumns = []

        if flag:
            df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval'] = pd.NA
        else:
            dropcolumns += [flagname]

        if drop_empty:
            if pd.isnull(df['issue_processdateinterval']).all():
                dropcolumns += ['issue_processdateinterval']
            if pd.isnull(df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval']).all():
                dropcolumns += [f'{basedatekey}_intervalwidth_generatedby_processdateinterval']

        df.drop(columns=dropcolumns, inplace=True)

        return df

    else:

        # Convert intervals to date

        printv('', verbose=verbose)
        printv(f'* Replace date intervals with {strategy} date', verbose=verbose, indent=indent)

        tempcol = ['start_str','end_str','start','end']
        df.loc[df[flagname],['start_str','end_str']] = df.loc[df[flagname],datekey].astype('string').str.split('/').tolist()
        df[['start','end']] = df[['start_str','end_str']].astype('string')
        df = convertdatetype.apply(df, datekey='start', format='ISO8601', verbose=verbose, indent=indent)
        df = convertdatetype.apply(df, datekey='end', format='ISO8601', verbose=verbose, indent=indent)
        # Note: unknown month and day are replaced with '01'
        # i.e., the first day of the known month or January

        if maxinterval_number == 0:
            # assumption: equivalent to less than 1 `maxinterval_level`
            maxinterval_number = 1

        if maxinterval_number != -1:

            # If the date interval is greater than `maxinterval_number` (default:1) `maxinterval_level` (default:year),
            # assign a missing value to the date for later deletion
            # Else, process date intervals

            ismissing = (pd.isnull(df['start']) & (~pd.isnull(df['end']))) | (pd.isnull(df['end']) & (~pd.isnull(df['start'])))
            df.loc[ismissing,datekeyout] = pd.NA
            df.loc[ismissing,'issue_processdateinterval'] = f'{basedatekey.upper()}_INTERVAL_PROCESSING_FAILED'

            tempcol += ['upperbound','flag_isgreater']
            df.loc[~ismissing,'upperbound'] = df.loc[~ismissing,'start'] + pd.DateOffset(**{maxinterval_level:maxinterval_number})
            df['flag_isgreater'] = False
            df.loc[(~ismissing) & df[flagname],'flag_isgreater'] = (df.loc[(~ismissing) & df[flagname],'end'] > df.loc[(~ismissing) & df[flagname],'upperbound'])
            index_delete = df[(~ismissing) & df[flagname] & df['flag_isgreater']].index
            index2process = df[(~ismissing) & df[flagname] & (~df['flag_isgreater'])].index

            df.loc[index_delete,datekeyout] = pd.NA
            df.loc[index_delete,'issue_processdateinterval'] = f'{basedatekey.upper()}_INTERVAL_EXCEEDS_LIMIT'
            df = apply_strategy(df, datekeyout, index2process, strategy)

        else:

            # Process all date intervals

            index2process = df[flagname].index
            df = apply_strategy(df, datekeyout, index2process, strategy)

        if drop_empty and pd.isnull(df['issue_processdateinterval']).all():
            tempcol += ['issue_processdateinterval']

        if flag:

            # Date interval length in days

            with warnings.catch_warnings():
                warnings.simplefilter('ignore', FutureWarning)
                df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval'] = pd.NA
                df.loc[df[flagname],f'{basedatekey}_intervalwidth_generatedby_processdateinterval'] = (df.loc[df[flagname],'end'] - df.loc[df[flagname],'start']).dt.days
                df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval'] = df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval'].astype('Int64')

            if drop_empty and pd.isnull(df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval']).all():
                tempcol += [f'{basedatekey}_intervalwidth_generatedby_processdateinterval']

            # Clean

            df.drop(columns=tempcol, inplace=True)

            return df

        else:

            # Clean

            tempcol += [flagname]
            df.drop(columns=tempcol, inplace=True)

            return df
