#!/usr/bin/python
# coding: utf-8

# External import

import numpy as np
import pandas as pd


# Internal import

from marinedb.utils.allexport import export

from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator


def get_floatprecision(series_flt):

    series_flt = series_flt.astype('string')
    series_flt = series_flt.str.strip()
    series_flt = series_flt.str.split(pat='.')
    precision = np.where(series_flt.str.len().eq(1) | series_flt.str[1].eq(''), 0, series_flt.str[1].str.len())

    return pd.Series(precision)

@export
def apply(df, key, value, flag=False, dropna=False, indent=''):

    if not isinstance(value,int):
        raise ValueError(f'`isbelow_minfloatprecision.py` | `value` must be an integer (value={value})')

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Compute the number of digits after the decimal point

    print(indent + f'* isbelow_minfloatprecision | count the number of decimal places')

    precision_column = f'{key}_floatprecision_generatedby_isbelow_minfloatprecision'
    if precision_column in df.columns:
        print(indent + f'INFO | {precision_column} column already exists and will be used')
    else:
        df[precision_column] = get_floatprecision(df[key]).astype('Int64')

    # Check whether the float precision of `key` is below `value`

    isbelow_minfloatprecision = (df[precision_column] < value)
    ismissing = pd.isnull(df[key].astype('Float64'))
    isbelow_minfloatprecision[ismissing] = pd.NA

    print(indent + f'* isbelow_minfloatprecision | flag and/or filter')

    if flag:

        # Flag rows where the float precision of `key` is below `value`

        df[f'flag_{key}_isbelow_minfloatprecision_{str(value)}'] = isbelow_minfloatprecision

        return df

    else:

        # Drop rows:
        #   - where the float precision of `key` is below `value`
        #   - with missing values in `key` if `dropna`

        ## Apply missing data handling strategy
        isbelow_minfloatprecision[ismissing] = dropna

        ## Clean
        df.drop(columns=[precision_column], inplace=True)

        return df[~isbelow_minfloatprecision].reset_index(drop=True)
