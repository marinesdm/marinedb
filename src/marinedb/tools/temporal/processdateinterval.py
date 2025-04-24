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

    flaginterval = pd.Series([False]*len(df))

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
        df.loc[match_index, key] = year_start[match_index].astype('str')

        ## Month overlap
        ismonthmatch = isyearmatch & (~pd.isnull(month_start)) & (~pd.isnull(month_end)) & (month_start == month_end)
        match_index = ismonthmatch[ismonthmatch].index
        df.loc[match_index, key] = df.loc[match_index, key] + '-' + month_start[match_index]

        ## Day overlap
        isdaymatch = isyearmatch & ismonthmatch & (~pd.isnull(day_start)) & (~pd.isnull(day_end)) & (day_start == day_end)
        match_index = isdaymatch[isdaymatch].index
        df.loc[match_index, key] = df.loc[match_index, key] + '-' + day_start[match_index]

        df[key] = df[key].astype('string')

    else:
        raise ValueError(f"`processdateinterval.py` | `strategy` must be 'start', 'end' or 'overlap'")

    return df

@export
def apply(df, datekey, drop_interval=False, strategy='overlap', maxinterval_number=1, maxinterval_level='years', inplace=False, flag=True, drop_empty=False, verbose=True, indent=''):

    # maxinterval_number=-1 : process all date intervals regardless of width
    # strategy in ['start', 'end', 'overlap'] : a different strategy could be implemented (e.g. take the median date)
    # drop_interval=True : drop date intervals
    # drop_interval=False : process date intervals
    # inplace=True/False: in place or not
    # flag=True/False: whether or not to keep the date interval flag column

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

    df, datekey, outputkey = getcolumnname.apply(df, datekey, 'processdateinterval', inplace=inplace)

    if not inplace:
        df[outputkey] = df[datekey].copy()

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

        df.loc[df[flagname],outputkey] = pd.NA
        df[outputkey] = df[outputkey].astype('string')

        dropcolumns = []
        if drop_empty and pd.isnull(df['issue_processdateinterval']).all():
            dropcolumns += ['issue_processdateinterval']
        if not flag:
            dropcolumns += flagname
        df.drop(columns=dropcolumns, inplace=True)

        return df

    else:

        # Convert intervals to date

        printv(f'* Replace date intervals with {strategy} date', verbose=verbose, indent=indent)

        tempcol = ['start_str','end_str','start','end']
        df.loc[df[flagname],['start_str','end_str']] = df.loc[df[flagname],datekey].astype('string').str.split('/').tolist()
        df[['start','end']] = df[['start_str','end_str']].astype('string').values
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
            df.loc[ismissing,outputkey] = pd.NA
            df.loc[ismissing,'issue_processdateinterval'] = f'{basedatekey.upper()}_INTERVAL_PROCESSING_FAILED'

            tempcol += ['upperbound','flag_isgreater']
            df.loc[~ismissing,'upperbound'] = df.loc[~ismissing,'start'] + pd.DateOffset(**{maxinterval_level:maxinterval_number})
            df['flag_isgreater'] = False
            df.loc[(~ismissing) & df[flagname],'flag_isgreater'] = (df.loc[(~ismissing) & df[flagname],'end'] > df.loc[(~ismissing) & df[flagname],'upperbound'])
            index_delete = df[(~ismissing) & df[flagname] & df['flag_isgreater']].index
            index2process = df[(~ismissing) & df[flagname] & (~df['flag_isgreater'])].index

            df.loc[index_delete,outputkey] = pd.NA
            df.loc[index_delete,'issue_processdateinterval'] = f'{basedatekey.upper()}_INTERVAL_EXCEEDS_LIMIT'
            df = apply_strategy(df, outputkey, index2process, strategy)

        else:

            # Process all date intervals

            index2process = df[flagname].index
            df = apply_strategy(df, outputkey, index2process, strategy)

        if drop_empty and pd.isnull(df['issue_processdateinterval']).all():
            tempcol += ['issue_processdateinterval']

        if flag:

            # Date interval length in days

            with warnings.catch_warnings():
                warnings.simplefilter('ignore', FutureWarning)
                df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval'] = pd.NA
                df.loc[df[flagname],f'{basedatekey}_intervalwidth_generatedby_processdateinterval'] = df.loc[df[flagname],'end'].dt.to_pydatetime() - df.loc[df[flagname],'start'].dt.to_pydatetime()
                df.loc[df[flagname],f'{basedatekey}_intervalwidth_generatedby_processdateinterval'] = df.loc[df[flagname],f'{basedatekey}_intervalwidth_generatedby_processdateinterval'].apply(lambda width: width.days)
                df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval'] = df[f'{basedatekey}_intervalwidth_generatedby_processdateinterval'].astype('Int64')

            # Clean

            df.drop(columns=tempcol, inplace=True)

            return df

        else:

            # Clean

            tempcol += [flagname]
            df.drop(columns=tempcol, inplace=True)

            return df
