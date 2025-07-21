#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.tools.spatial import iszero

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, latkey, lonkey, flag=False, dropna=True, verbose=True, indent=''):

    df, latkey, _ = getcolumnname.apply(df, latkey, '', inplace=True)
    df, lonkey, _ = getcolumnname.apply(df, lonkey, '', inplace=True)

    columns_before = set(df.columns)

    params = {
              'flag': flag,
              'dropna': dropna,
              'verbose': verbose,
              'indent': indent
              }

    df = iszero.apply(df, latkey, **params)
    df = iszero.apply(df, lonkey, **params)

    columns_iszero = list(set(df.columns) - columns_before)

    df[columns_iszero] = df[columns_iszero].fillna(False)

    if flag:
        assert len(columns_iszero) == 2
        flagname = f'flag_{latkey}_{lonkey}_islatlonzero'
        df[flagname] = (df[columns_iszero].sum(axis=1) > 0)
        ismissing = (pd.isnull(df[latkey]) | pd.isnull(df[lonkey]))
        df.loc[(~df[flagname]) & ismissing, flagname] = pd.NA

    df.drop(columns=columns_iszero, inplace=True)

    return df

