#!/usr/bin/python
# coding: utf-8

# External import

import re
import numpy as np
import pandas as pd
from unidecode import unidecode

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
                  'nd',
                  'None',
                  'Unknown',
                  '#VALUE!']

def isnan(value, nan_values=None, additional_policy=''):

    if len(additional_policy) != 0:
        if additional_policy not in ['contains_letters', 'contains_digits', 'contains_letters_or_digits']:
            raise ValueError(f"`standardizenan.py | `additional_policy` must be either 'contains_letters' or 'contains_letters_or_digits', but received '{additional_policy}'")

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
    nan_values = [str(v).lower() for v in nan_values]
    nan_values = list(set(nan_values))

    if str(value).lower() in nan_values:
        return True

    if additional_policy:

        value_to_check = str(value)

        if additional_policy == 'contains_letters':
            pattern = r'[a-zA-Z]'
            value_to_check = unidecode(value_to_check)
        elif additional_policy == 'contains_digits':
            pattern = r'[0-9]'
        else:
            pattern = r'[a-zA-Z0-9]'
            value_to_check = unidecode(value_to_check)

        if not re.search(pattern, value_to_check):
            return True

    return False

def stdnan(value, nan_values=None, additional_policy=''):

    if isnan(value, nan_values=nan_values, additional_policy=additional_policy):
        return pd.NA

    return value

@export
def apply(df, key=None, nan_values=None, additional_policy=''):

    if len(df) == 0:
        return df

    visnan = np.vectorize(isnan, excluded={1, 'nan_values'})

    if (key is None) or (len(key) == 0):

        # Convert all missing values to pd.NA

        if isinstance(df, pd.Series):
            df = pd.Series(np.where(visnan(df, nan_values=nan_values, additional_policy=additional_policy), pd.NA, df))
        elif isinstance(df, pd.DataFrame):
            df = pd.DataFrame(np.where(visnan(df, nan_values=nan_values, additional_policy=additional_policy), pd.NA, df), columns=df.columns)
        else:
            raise TypeError(f"`standardizenan.py` | '{type(df).__name__}' type not supported")

    else:

        # Convert all missing values in `key` columns to pd.NA

        df[key] = np.where(visnan(df[key], nan_values=nan_values, additional_policy=additional_policy), pd.NA, df[key])

    return df
