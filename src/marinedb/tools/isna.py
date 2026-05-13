#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.utils import standardizenan
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, stdnan=True, nan_values=None, stdnan_additional_policy='', flag=False, verbose=True, indent=''):

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    if stdnan:
        df = standardizenan.apply(df, key=key, nan_values=nan_values, additional_policy=stdnan_additional_policy)

    ismissing = pd.isnull(df[key])

    if ('species' in key.lower()) or ('scientificname' in key.lower()): #debug
        if any(ismissing):
            print('missing species (isna.py) :')
            print(df.loc[ismissing, [key, 'match_type_generatedby_isinworms', 'taxamatch_generatedby_isinworms']])

    if flag:
        # Flag rows with missing values in the `key` column
        df[f'flag_{key}_isna'] = ismissing
        return df

    else:
        # Drop rows with missing values in the `key` column
        return df[~ismissing].reset_index(drop=True)
