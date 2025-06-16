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
def apply(df, key, flag=False, dropna=False, verbose=True, indent=''):

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    df[key] = df[key].astype('string')

    pattern=r'[^a-zA-Z\s\-]'
    islettersonly = (~df[key].str.contains(pattern, na=False))
    islettersonly = islettersonly.astype('boolean')
    ismissing = pd.isnull(df[key])
    islettersonly[ismissing] = pd.NA

    if not islettersonly.all(): #debug
        print('islettersonly')
        print('key:', key)
        print(df.loc[(~ismissing) & (~islettersonly), key]) #debug

    if flag:
        # Flag rows where the `key` column contains only letters
        df[f'flag_{key}_lettersonly'] = islettersonly
        return df
    else:
        # Drop rows:
        #   - where `key` contains non-letter characters
        #   - with missing values in `key` if `dropna`
        islettersonly[ismissing] = (not dropna)
        return df[islettersonly]
