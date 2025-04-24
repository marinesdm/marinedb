#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.tools import doesnotcontain
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, values, flag=False, minimize_flagname=False, flagname_mapping=None, dropna=False, verbose=True, indent=''):

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Run `doesnotcontain` on the `key` column

    try:
        df = doesnotcontain.apply(df, key, values, flag=True, minimize_flagname=minimize_flagname, flagname_mapping=flagname_mapping, dropna=False, verbose=verbose, indent=indent)
    except ValueError as err:
        raise ValueError(f"`contains.py` | {str(err).split('|')[-1]}")

    doesnotcontain_flagcolumn = [col for col in df.columns if (f'flag_{key}_doesnotcontain' in col)]
    assert len(doesnotcontain_flagcolumn) == 1
    doesnotcontain_flagcolumn = doesnotcontain_flagcolumn[0]
    value_str = doesnotcontain_flagcolumn.split('_')[-1]

    # Apply missing data handling strategy

    ismissing = pd.isnull(df[doesnotcontain_flagcolumn])
    df.loc[ismissing, doesnotcontain_flagcolumn] = dropna

    doescontain = (~df[doesnotcontain_flagcolumn])

    # Clean

    df.drop(columns=doesnotcontain_flagcolumn, inplace=True)

    if flag:

        # Flag rows where the `key` column contains values in `values`

        doescontain[ismissing] = pd.NA
        df[f'flag_{key}_contains_{value_str}'] = doescontain

        return df

    else:

        # Drop rows:
        #   - where `key` does not contain values in `values`
        #   - with missing values in `key` if `dropna`

        return df[doescontain].reset_index(drop=True)
