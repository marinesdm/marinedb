#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import isboundedby
from marinedb.tools import getcolumnname

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

    # Latitude
    df = isboundedby.apply(df, latkey, operator='>=', value=-90, **params)
    df = isboundedby.apply(df, latkey, operator='<=', value=90, **params)

    # Longitude
    df = isboundedby.apply(df, lonkey, operator='>=', value=-180, **params)
    df = isboundedby.apply(df, lonkey, operator='<=', value=180, **params)

    columns_isboundedby = list(set(df.columns) - columns_before)

    df[columns_isboundedby] = df[columns_isboundedby].fillna(not dropna)

    if flag:
        assert len(columns_isboundedby) == 4
        flagname = f'flag_{latkey}_{lonkey}_islatloninvalid'
        df[flagname] = (df[columns_isboundedby].sum(axis=1) != len(columns_isboundedby))

    df.drop(columns=columns_isboundedby, inplace=True)

    return df
