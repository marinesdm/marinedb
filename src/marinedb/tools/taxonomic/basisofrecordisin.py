#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import isin
from marinedb.tools import getcolumnname
from marinedb.tools.taxonomic import mapbasisofrecord

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key=None, values=None, dropna=False, std=False, std_additional_values=None, std_inplace=False, flag=True, verbose=True, indent=''):
    print(std_additional_values)
    if values is None:
        raise ValueError(f"`basisofrecordisin.py` | `values` must be specified")

    if (key is None) or (len(key) == 0):

        if std:
            raise ValueError(f"`basisofrecordisin.py` | `key` must be specified when `std=True` to standardize basis of record values")

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

    if std:
        columns_before = set(df.columns)
        df = mapbasisofrecord.apply(df, key, additional_values=std_additional_values, inplace=std_inplace, verbose=verbose, indent=indent)
        columns_after = set(df.columns)
        keyout = columns_after - columns_before
        assert len(keyout) == 1
        key = list(keyout)[0]

    df = isin.apply(df, key, values, flag=flag, dropna=dropna, verbose=verbose, indent=indent)

    return df
