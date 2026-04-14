#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
from unidecode import unidecode

# Internal import

from marinedb.utils.allexport import export
from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, flag=False, dropna=False, verbose=True, indent=''):

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    df[key] = df[key].astype('string')

    # Flag or exclude rank names containing non-letter characters
    # e.g., GWE2-31-10, UBA1177, and JACPGU01 classes (typically DNA-derived observations, or microbial groups)
    # Note: some edge cases may be incorrectly flagged or excluded,
    # e.g., "Hexabothrium (incertae sedis)" (aphiaID=719046)
    # e.g., "[non-Uristidae]" (aphiaID=875566) genera

    pattern=r'[^a-zA-Z\s\-]'
    tempkey = 'TEMPORARYLETTERSONLY_{key}'
    df[tempkey] = df[key]
    ismissing = pd.isnull(df[key])
    df.loc[~ismissing, tempkey] = df.loc[~ismissing, tempkey].apply(unidecode) # e.g., "Terpsinoë" and "Naïs" genera
    islettersonly = (~df[tempkey].str.contains(pattern, na=False))
    islettersonly = islettersonly.astype('boolean')
    islettersonly[ismissing] = pd.NA

    df.drop(columns=[tempkey], inplace=True)

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
        return df[islettersonly].reset_index(drop=True)
