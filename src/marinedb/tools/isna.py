#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, flag=False):

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    ismissing = pd.isnull(df[key])

    if flag:
        # Flag rows with missing values in the `key` column
        df[f'flag_{key}_isna'] = ismissing
        return df

    else:
        # Drop rows with missing values in the `key` column
        return df[~ismissing].reset_index(drop=True)
