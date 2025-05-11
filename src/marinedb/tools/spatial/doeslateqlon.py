#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils.allexport import export

from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, latkey, lonkey, flag=False, eps=1e-5, dropna=False, verbose=True, indent=''):

    # flag = True/False: whether to flag or drop observations that do not meet the condition
    # default eps: 1e-5
    #   - GBIF coordinates are rounded to six decimal places
    #   - five decimals places correspond to a precision of 1 meter at the equator (i.e., higher precision elsewhere)

    df, latkey, _ = getcolumnname.apply(df, latkey, '', inplace=True)
    df, lonkey, _ = getcolumnname.apply(df, lonkey, '', inplace=True)

    isequal = (df[latkey].astype('Float64') - df[lonkey].astype('Float64')).abs() <= eps
    isequal = isequal.astype('boolean')
    ismissing = (pd.isnull(df[latkey]) | pd.isnull(df[lonkey]))
    isequal[ismissing] = pd.NA

    if flag:
        # Flag rows where latitude and longitude are equal
        df[f'flag_{latkey}_{lonkey}_doeslateqlon'] = isequal
        return df
    else:
        # Drop rows:
        #   - where latitude and longitude are equal
        #   - with missing latitude and/or longitude when `dropna`
        isequal[ismissing] = dropna
        return df[~isequal]
