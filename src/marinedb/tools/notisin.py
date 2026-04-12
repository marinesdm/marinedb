#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
import re

# Internal import

from marinedb.utils.allexport import export
from marinedb.tools import getcolumnname
from marinedb.tools import isin

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, values, flag=False, minimize_flagname=False, flagname_mapping=None, dropna=False, verbose=True, indent='', outputdir='./'):

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Run `isin` on the `key` column

    params = {
              'flag': True,
              'minimize_flagname': minimize_flagname,
              'flagname_mapping': flagname_mapping,
              'dropna': False,
              'verbose': verbose,
              'indent': indent,
              'outputdir': outputdir
             }

    columns_before = set(df.columns)

    try:
        df = isin.apply(df, key, values, **params)
    except Exception as err:
        raise Exception(f"`notisin.py` | {str(err).split('|')[-1]}")

    diff_columns = list(set(df.columns) - columns_before)
    flagcolumn = [col for col in diff_columns if (f'flag_{key}_isin' in col)]
    assert len(flagcolumn) == 1
    flagcolumn = flagcolumn[0]
    values_str = re.sub(f'flag_{key}_isin_', '', flagcolumn)
#    values_str = '_'.join(flagcolumn.split('_')[3:])

    # Apply missing data handling strategy

    ismissing = pd.isnull(df[flagcolumn])
    df.loc[ismissing, flagcolumn] = dropna

    notisin = (~df[flagcolumn]).copy()

    # Clean

    df.drop(columns=flagcolumn, inplace=True)

    if flag:

        # Flag rows where `key` values are not in `values`

        notisin[ismissing] = pd.NA
        df[f'flag_{key}_notisin_{values_str}'] = notisin

        return df

    else:

        # Drop rows:
        #   - where `key` values are not in `values`
        #   - with missing values in `key` if `dropna`

        return df[notisin].reset_index(drop=True)


