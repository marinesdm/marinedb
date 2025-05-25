#!/usr/bin/python
# coding: utf-8

# External import

import numpy as np
import pandas as pd
import re

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

STR_NAN_VALUES = ['-1.#IND',
                  '1.#QNAN',
                  '1.#IND',
                  '-1.#QNAN',
                  '#N/A N/A',
                  '#N/A',
                  '#n/a',
                  'N/A',
                  'n/a',
                  'NA',
                  '<NA>',
                  '#NA',
                  'NULL',
                  'null',
                  'NaN',
                  '-NaN',
                  'nan',
                  '-nan',
                  '',
                  'None']

def isnan(value, nan_values=None, letters_only=False):

    try:
        if pd.isnull(float(value)): #NaN, nan, 'nan', 'NaN', None ...
            return True
    except (ValueError,TypeError):
        if pd.isnull(value): #NaT
            return True

    if nan_values is None:
        nan_values = []
    elif isinstance(nan_values,str):
        nan_values = [nan_values]
    nan_values = nan_values + STR_NAN_VALUES
    nan_values = [v.lower() for v in nan_values]
    nan_values = list(set(nan_values))

    if str(value).lower() in nan_values:
        return True

    if letters_only:
        pattern=r'[a-zA-Z]'
    else:
        pattern=r'[a-zA-Z0-9]'

    if not re.search(pattern,str(value)):
        return True

    return False

def stdnan(value, nan_values=None, letters_only=False):
    if isnan(value, nan_values=nan_values, letters_only=letters_only):
        return pd.NA
    return value

@export
def apply(df, key=None, nan_values=None, letters_only=False):

    visnan = np.vectorize(isnan)

    if (key is None) or (len(key) == 0):

        # Convert all missing values to pd.NA

        if isinstance(df, pd.Series):
            df = pd.Series(np.where(visnan(df, nan_values=nan_values, letters_only=letters_only), pd.NA, df))
        elif isinstance(df, pd.DataFrame):
            df = pd.DataFrame(np.where(visnan(df, nan_values=nan_values, letters_only=letters_only), pd.NA, df), columns=df.columns)
        else:
            raise TypeError(f"`standardizenan.py` | '{type(df).__name__}' type not supported")

    else:

        # Convert all missing values in `key` columns to pd.NA

        df[key] = np.where(visnan(df[key], nan_values=nan_values, letters_only=letters_only), pd.NA, df[key])

    return df
