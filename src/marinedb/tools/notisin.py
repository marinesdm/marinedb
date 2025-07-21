#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

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
    isin_flagcolumn = [col for col in diff_columns if (f'flag_{key}_isin' in col)]
    assert len(isin_flagcolumn) == 1
    isin_flagcolumn = isin_flagcolumn[0]
    values_str = isin_flagcolumn.split('_')[-1]

    # Apply missing data handling strategy

    ismissing = pd.isnull(df[isin_flagcolumn])
    df.loc[ismissing, isin_flagcolumn] = dropna

    notisin = (~df[isin_flagcolumn]).copy()

    # Clean

    df.drop(columns=isin_flagcolumn, inplace=True)

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


