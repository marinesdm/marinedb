import pandas as pd
import numpy as np

from dateutil import relativedelta
from dateutil import parser

import filters.convertdatetype


def display_progress(count, total, subset):

    percentage = np.round((count+1)/total*100,2)
    print(f'                Processing | {count+1}/{total} ({percentage}%) date intervals done: delete={subset}, convert={count + 1 - subset}')

    return True



def apply(df, key, drop=True, inplace=False, flag=False, maxinterval_number=1, maxinterval_level='year', interval_delimiter='/'): 

    #maxinterval_number=-1 keep the start date for all intervals
    #start date : a different strategy could be implemented (e.g. take the median date)
    #drop=True : drop date intervals (flag=False: delete ; flag=True: flag)
    #drop=False : process date intervals (flag=True/False: whether or not to keep the date interval flag column)

    if maxinterval_number<-1:
        raise ValueError("`processdateinterval.py` | `maxinterval_number` must be > -1")
    if maxinterval_level not in ['year','month','day']:
        raise ValueError("`processdateinterval.py` | `maxinterval_level` must be 'year', 'month' or 'day'")

    if inplace:
        colname=key
    else:
        colname=f'{key}_processedby_processdateinterval'
        df[colname]=df[key].values.copy()

    flagname = f'flag_{key}_interval'
    df[flagname]=False

    ## Find intervals

    print(f'            * processdateinterval | find date intervals')

    delimiter_index=df[key].str.find(interval_delimiter).astype('Int64') # interval format: YYYY[-MM[-DD...]]/YYYY[-MM[-DD...]]
    interval_index=list(np.where((~pd.isnull(delimiter_index)) & (delimiter_index>0))[0])
    df.loc[interval_index, flagname]=True

    if drop and not flag:

        ## Delete intervals

        print(f'            * processdateinterval | delete date intervals')

        df = df[~df[flagname]].reset_index(drop=True)
        df.drop(columns=[flagname], inplace=True)
        df = convertdatetype.apply(df,colname)
        return df

    elif drop and flag:

        ## Flag intervals for later deletion or processing

        print(f'            * processdateinterval | flag date intervals')

        df.drop(columns=colname, inplace=True)
        return df

    else:

        ## Convert intervals to date

        print(f'            * processdateinterval | replace date intervals with start date')

        Nintervals=len(interval_index)
        Ntoowide=0

        if Nintervals!=0:

            for count,idx in enumerate(interval_index):

                #print(idx)

                date=df.loc[idx,key]
                start=date[:delimiter_index[idx]]
                end=date[delimiter_index[idx]+1:]

                interval = relativedelta.relativedelta(parser.parse(end, yearfirst=True, dayfirst=False), parser.parse(start, yearfirst=True, dayfirst=False))

                if (interval.years<0) or (interval.months<0) or (interval.days<0):
                    # Error : end < start
                    df.loc[idx,colname]=pd.NA

                else:
                    if maxinterval_number!=-1:

                        # If the date interval is greater than maxinterval_number (default:1) maxinterval_level (default:year),
                        # assign a missing value to the date for later deletion
                        # Else, keep the start date.

                        if maxinterval_level=='year':
                            if (interval.years > maxinterval_number):
                                df.loc[idx,colname]=pd.NA
                                Ntoowide+=1
                            else:
                                df.loc[idx,colname]=start

                        elif maxinterval_level=='month':
                            if (interval.years > 0) or (interval.months > maxinterval_number):
                                df.loc[idx,colname]=pd.NA
                                Ntoowide+=1
                            else:
                                df.loc[idx,colname]=start

                        else: #maxinterval_level=='day'
                            if (interval.years > 0) or (interval.months > 0) or (interval.days > maxinterval_number):
                                df.loc[idx,colname]=pd.NA
                                Ntoowide+=1
                            else:
                                df.loc[idx,colname]=start

                    else:

                        # Always keep the start date

                        df.loc[idx,colname]=start


                if ((count+1)%10000==0):

                    # Display code progress

                    display_progress(count, Nintervals, Ntoowide)

            display_progress(count, Nintervals, Ntoowide)


            if flag:
                return df

            else:
                df.drop(columns=[flagname], inplace=True)
                return df
