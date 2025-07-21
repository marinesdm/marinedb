#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.tools import isin

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, values, key=None, flag=True, dropna=False, verbose=True, indent=''):

    if (key is None) or (len(key) == 0):
        columns = list(df.columns)
        basisofrecord_column = [col for col in columns if ('basisOfRecord' in col)]
        if len(basisofrecord_column) == 0:
            raise Exception(f"`basisofrecordisin.py` | No column containing 'basisOfRecord' was found. Please specify the `key` argument explicitly.")
        if len(basisofrecord_column) > 1:
            basisofrecord_column_min = min(basisofrecord_column, key=len)
            doescontain = [basisofrecord_column_min in col for col in basisofrecord_column]
            doescontain = all(doescontain)
            if not doescontain:
                raise Exception(f"`basisofrecordisin.py` | Multiple columns containing 'basisOfRecord' was found. Please specify the `key` argument explicitly.")
            key = basisofrecord_column_min
        else:
            key = basisofrecord_column[0]
    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    df = isin.apply(df, key, values, flag=flag, dropna=dropna, verbose=verbose, indent=indent)

    return df
