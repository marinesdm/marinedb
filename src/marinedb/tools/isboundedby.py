#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

operator_mapping = {
                    '>':'SUP',
                    '>=':'SUPEQ',
                    '<':'INF',
                    '<=':'INFEQ'
                   }


def value_mapping(str_value):

    if '-' in str_value:
        return f'NEG{str_value[1:]}'
    else:
        return f'POS{str_value}'


@export
def apply(df, key, operator, value, flag=False, dropna=False, indent=''):

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    if '<' in operator:
        if '=' in operator:
            isboundedby = (df[key].astype('Float64') <= float(value))
        else:
            isboundedby = (df[key].astype('Float64') < float(value))
    elif '>' in operator:
        if '=' in operator:
            isboundedby = (df[key].astype('Float64') >= float(value))
        else:
            isboundedby = (df[key].astype('Float64') > float(value))
    else:
        raise ValueError("`isboundedby.py` | the comparison operator in `value` should be '<', '>', or a combination of '=' and '<' or '>'.")

    ismissing = pd.isnull(df[key])
    isboundedby[ismissing] = pd.NA

    if flag:
        # Flag rows that satisfy the bounding condition
        condition = '-'.join([operator_mapping[operator], value_mapping(str(value))])
        df[f'flag_{key}_isboundedby_{condition}'] = isboundedby
        return df
    else:
        # Drop rows:
        #   - that DO NOT statisfy the bounding condition
        #   - with missing values in `key` if `dropna`
        isboundedby[ismissing] = (not dropna)
        return df[isboundedby].reset_index(drop=True)
