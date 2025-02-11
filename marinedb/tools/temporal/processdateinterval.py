import pandas as pd
import numpy as np

import tools.convertdatetype as convertdatetype


def apply(df, key, drop=False, inplace=False, flag=False, maxinterval_number=1, maxinterval_level='years', interval_delimiter='/'):

    #maxinterval_number=-1 keep the start date for all intervals
    #start date : a different strategy could be implemented (e.g. take the median date)
    #drop=True : drop date intervals (flag=False: delete ; flag=True: flag)
    #drop=False : process date intervals (flag=True/False: whether or not to keep the date interval flag column)

    maxinterval_number=int(maxinterval_number)

    if maxinterval_number<-1:
        raise ValueError(f"`processdateinterval.py` | `maxinterval_number` must be > -1, not {maxinterval_number}")
    if maxinterval_level not in ['years','months','days']:
        raise ValueError(f"`processdateinterval.py` | `maxinterval_level` must be 'years', 'months' or 'days', not {maxinterval_level}")

    if inplace:
        colname=key
    else:
        colname=f'{key}_processedby_processdateinterval'
        df[colname]=df[key].values.copy()

    flagname = f'flag_{key}_interval'
    df[flagname]=False

    ## Find intervals

    print(f'            ** processdateinterval | find date intervals')

    delimiter_index=df[key].astype('string').str.find(interval_delimiter).astype('Int64') # interval format: YYYY[-MM[-DD...]]/YYYY[-MM[-DD...]]
    interval_index=list(np.where((~pd.isnull(delimiter_index)) & (delimiter_index>0))[0])
    df.loc[interval_index, flagname]=True

    if drop and not flag:

        ## Delete intervals

        print(f'            ** processdateinterval | delete date intervals')

        df = df[~df[flagname]].reset_index(drop=True)
        df.drop(columns=[flagname], inplace=True)
        df = convertdatetype.apply(df,colname)
        return df

    elif drop and flag:

        ## Flag intervals for later deletion or processing

        print(f'            ** processdateinterval | flag date intervals')

        df.drop(columns=colname, inplace=True)
        return df

    else:

        ## Convert intervals to date

        print(f'            ** processdateinterval | replace date intervals with start date')

        tempdf = pd.DataFrame(df.loc[df[flagname],key].astype('string').str.split('/').tolist(), columns=['start','end'], index=df[df[flagname]].index)
        tempdf = convertdatetype.apply(tempdf,'start')
        tempdf = convertdatetype.apply(tempdf,'end')
        tempdf.loc[tempdf['end'] < tempdf['start'],'start'], tempdf.loc[tempdf['end'] < tempdf['start'],'end'] = tempdf.loc[tempdf['end'] < tempdf['start'],'end'], tempdf.loc[tempdf['end'] < tempdf['start'],'start']

        if maxinterval_number==0:
            #assumption: equivalent to less than 1 maxinterval_level
            maxinterval_number=1

        if maxinterval_number!=-1:

            # If the date interval is greater than maxinterval_number (default:1) maxinterval_level (default:year),
            # assign a missing value to the date for later deletion
            # Else, keep the start date.

            tempdf['upperbound'] = tempdf['start'] + pd.DateOffset(**{maxinterval_level:maxinterval_number})
            tempdf['flag_isgreater'] = tempdf['end'] > tempdf['upperbound']

            indexes_delete=tempdf[tempdf['flag_isgreater']].index
            indexes_convert=tempdf[~tempdf['flag_isgreater']].index

            df.loc[indexes_delete,colname]=pd.NA
            df.loc[indexes_convert,colname]=tempdf.loc[indexes_convert,'start']

        else:

            # Always keep the start date

            df.loc[tempdf.index,colname]=tempdf.loc[:'start']


        if flag:

            tempdf['dateinterval'] = tempdf['end'].dt.to_pydatetime() - tempdf['start'].dt.to_pydatetime()
            tempdf['dateinterval'] = tempdf['dateinterval'].apply(lambda width: width.days)
            colname=f'{key}_intervalwidth'
            df[colname]=pd.NA
            df.loc[tempdf.index,colname]=tempdf['dateinterval']
            df[colname]=df[colname].astype('Int64')

            return df

        else:

            df.drop(columns=[flagname], inplace=True)

            return df
