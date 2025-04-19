#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils.allexport import export
from marinedb.tools import getcolumnname
from marinedb.tools import aligndtypes

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, values, flag=False, flagname_mapping=None, dropna=False, indent=''):

    if (not flag) and (flagname_mapping is not None):
        print(indent + f'INFO | Since `flag` is {flag}, `flagname_mapping` will be ignored')
        flagname_mapping = None

    if (flagname_mapping is not None):
        if not isinstance(flagname_mapping, str | dict):
            raise ValueError('`isin.py` | `flagname_mapping` must be provided as either a dictionary or a JSON file path')
        if isinstance(flagname_mapping, str):
            try:
                with open(flagname_mapping,'r') as file:
                    flagname_mapping = json.load(file)
            except ValueError:
                raise ValueError('`isin.py` | if a string, `flagname_mapping` must be a path to a valid JSON file')

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Ensure that the objects being compared are of the same type

    df, values = aligndtypes.apply(df, key, values)
    if not isinstance(values, list):
        values = [values]

    # Filtering condition

    condition = df[key].isin(values)
    ismissing = pd.isnull(df[key])
    condition[ismissing] = pd.NA

    if flag:

        # Flag rows where `key` values are in `values`

        if flagname_mapping is not None:
            temp = flagname_mapping.copy()
            for k in flagname_mapping.keys():
                temp[str(k)] = temp.pop(k)
            flagname_mapping = temp
            values_str = '-'.join([str(flagname_mapping[str(val)]) for val in values])
        else:
            values_str = '-'.join([str(val) for val in values])

        df[f'flag_{key}_isin_{values_str}'] = condition

        return df

    else:

        # Drop rows where `key` values are NOT in `values`
        # Note: rows with missing values in the `key` column are removed

        condition[ismissing] = (not dropna)

        return df[condition].reset_index(drop=True)
