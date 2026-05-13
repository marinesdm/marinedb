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
def apply(df, key, flag=False, eps=1e-5, dropna=False, verbose=True, indent=''):

    # flag = True/False: whether to flag or drop observations that do not meet the condition
    # default eps: 1e-5
    #   - GBIF coordinates are rounded to six decimal places
    #   - five decimal places correspond to a precision of 1 meter at the equator (i.e., higher precision elsewhere)

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    iszero = (df[key].astype('Float64').abs() <= eps)
    iszero = iszero.astype('boolean')
    ismissing = pd.isnull(df[key])
    iszero[ismissing] = pd.NA

    if flag:
        # Flag rows with null values in the `key` column
        df[f'flag_{key}_iszero'] = iszero
        return df
    else:
        # Drop rows:
        #   - with null values in `key`
        #   - with missing values in `key` if `dropna`
        iszero[ismissing] = dropna
        return df[~iszero].reset_index(drop=True)
