#import datetime3_11 as datetime
import pandas as pd

def apply(df, key):

    #Warning : If the function is applied to a column containing unprocessed date intervals,
    #          the result may be unexpected:
    #          - date intervals may be replaced by missing values (errors='coerce')
    #          - pd.datetime() may interpret the second date as the time (e.g. 2021-03-02/2021-06-02 becomes '2021-03-02 20:21:00-02:00')
    #          - other special cases may arise that we haven't observed

    df[key] = pd.to_datetime(df[key].astype('string'), format='ISO8601', errors='coerce') #format='mixed', yearfirst=True, dayfirst=False, errors='coerce', utc=True)
    #errors='coerce':
    #    invalid parsing set as NaT (Not a Time)
    #    e.g. NaT if date < 1677-09-22 or date > 2262-04-11 (Timestamp limitations)
    #    Remark : time span can been wider with unit > ns (ms, s ...)
    #    https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timestamp-limitations
    #    https://numpy.org/doc/stable/reference/arrays.datetime.html#datetime-units
    #    Warning : there may be other parsing issues and they may be mask

    # SUPPRESS ?
    #utc=True:
    #    https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html
    #    localized as or converted to UTC
    #    mixed time zones (e.g. issued from a timezone with daylight savings, such as Europe/Paris) raise an error unless utc=True
    #format='mixed':
    #    infer the format for each element individually

    df[key]=df[key].dt.tz_localize(None) # remove the time zone information (and preserve local time)

    return df
