import pandas as pd
import warnings

from marinedb.tools.temporal import convertdatetype

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

def apply(df, key, drop=False, inplace=False, flag=False, strategy='overlap', maxinterval_number=1, maxinterval_level='years'): #, interval_delimiter='/', date_delimiter='-'):

    # maxinterval_number=-1 keep the start date for all intervals
    # strategy in ['start', 'end', 'overlap'] : a different strategy could be implemented (e.g. take the median date)
    # drop=True : drop date intervals (flag=False: delete ; flag=True: flag)
    # drop=False : process date intervals (flag=True/False: whether or not to keep the date interval flag column)

    # Verifications

    ## Parameters

    if strategy not in ['start','end', 'overlap']:
        raise ValueError(f"`processdateinterval.py` | `strategy` must be 'start', 'end' or 'overlap'")

    maxinterval_number = int(maxinterval_number)

    if (maxinterval_number < -1):
        raise ValueError(f"`processdateinterval.py` | `maxinterval_number` must be > -1, not {maxinterval_number}")
    if maxinterval_level not in ['years','months','days']:
        raise ValueError(f"`processdateinterval.py` | `maxinterval_level` must be 'years', 'months' or 'days', not {maxinterval_level}")

    if (drop and (not flag)) and (not inplace):
        print(f'            WARNING | drop={drop} and flag={flag}, but inplace={inplace}')
        print(f'            The lines containing a date interval will be dropped in-place')
        inplace = True

    if (strategy == 'overlap'):
        print(f'            INFO | If strategy={strategy}, maxinterval_number={maxinterval_number} will not be considered')

    if inplace:
        colname = key
    else:
        colname = f'{key}_processedby_processdateinterval'
        df[colname] = df[key].values.copy()

    ## Date format

    pattern = r'([0-9]{4}(?:-[0-9]{2}){0,2})(?:/([0-9]{4}(?:-[0-9]{2}){0,2}))?'
    isformatrecognized = df[key].str.fullmatch(pattern)
    if not isformatrecognized.all():
        raise ValueError(f"`processdateinterval.py` | All dates should follow the 'YYYY[[-MM[-DD]]/YYYY[-MM[-DD]]]' format. Please use `parsedate.py` upstream to convert date strings to this valid format.")
    issymmetrical = df.loc[(~pd.isnull(df[key])),key].str.extract(pattern)
    issymmetrical = issymmetrical[(~pd.isnull(issymmetrical.iloc[:,1]))]
    issymmetrical = (issymmetrical.iloc[:,0].str.len() == issymmetrical.iloc[:,1].str.len())
    if not issymmetrical.all():
        raise ValueError(f"`processdateinterval.py` | All date intervals should be symmetrical, i.e., both dates must have the same precision")

    flagname = f'flag_{key}_interval'
    df[flagname] = False

    # Find intervals

    print(f'            ** processdateinterval | find date intervals')

    isdatemissing = pd.isnull(df[key])
    df.loc[~isdatemissing,flagname] = df.loc[~isdatemissing,key].astype('string').str.contains('/') # interval format: YYYY[-MM[-DD]]/YYYY[-MM[-DD]]

    if drop and not flag:

        # Delete intervals

        print(f'            ** processdateinterval | delete date intervals')

        df = df[~df[flagname]].reset_index(drop=True)
        df.drop(columns=[flagname], inplace=True)
        df[colname] = df[colname].astype('string')

        return df

    elif drop and flag:

        # Flag intervals for later deletion or processing

        print(f'            ** processdateinterval | flag date intervals')

        if not inplace:
            df.drop(columns=colname, inplace=True)

        return df

    else:

        # Convert intervals to date

        print(f'            ** processdateinterval | replace date intervals with {strategy} date')

        tempcol = ['start_str','end_str','start','end']
        df.loc[df[flagname],['start_str','end_str']] = df.loc[df[flagname],key].astype('string').str.split('/').tolist()
        df[['start','end']] = df[['start_str','end_str']].astype('string').values
        df = convertdatetype.apply(df, 'start', format='ISO8601')
        df = convertdatetype.apply(df, 'end', format='ISO8601')
        # Note: if the month or day is unknown, it is replaced with '01'
        # i.e., the first day of the month or January

        if maxinterval_number == 0:
            # assumption: equivalent to less than 1 maxinterval_level
            maxinterval_number = 1

        if maxinterval_number != -1:

            # If the date interval is greater than maxinterval_number (default:1) maxinterval_level (default:year),
            # assign a missing value to the date for later deletion
            # Else, process date intervals

            tempcol += ['upperbound','flag_isgreater']
            df['upperbound'] = df['start'] + pd.DateOffset(**{maxinterval_level:maxinterval_number})
            df['flag_isgreater'] = False
            df.loc[df[flagname],'flag_isgreater'] = (df.loc[df[flagname],'end'] > df.loc[df[flagname],'upperbound'])
            index_delete = df[df[flagname] & df['flag_isgreater']].index
            index2process = df[df[flagname] & (~df['flag_isgreater'])].index

            df.loc[index_delete,colname] = pd.NA
            df = apply_strategy(df, colname, index2process, strategy)

        else:

            # Process all date intervals

            index2process = df[flagname].index
            df = apply_strategy(df, colname, index2process, strategy)

        if flag:

            # Date interval length in days

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                df[f'{key}_dateinterval_indays'] = pd.NA
                df.loc[df[flagname],f'{key}_dateinterval_indays'] = df.loc[df[flagname],'end'].dt.to_pydatetime() - df.loc[df[flagname],'start'].dt.to_pydatetime()
                df.loc[df[flagname],f'{key}_dateinterval_indays'] = df.loc[df[flagname],f'{key}_dateinterval_indays'].apply(lambda width: width.days)
                df[f'{key}_dateinterval_indays'] = df[f'{key}_dateinterval_indays'].astype('Int64')

            # Clean

            df.drop(columns=tempcol, inplace=True)

            return df

        else:

            # Clean

            tempcol += [flagname]
            df.drop(columns=tempcol, inplace=True)

            return df
