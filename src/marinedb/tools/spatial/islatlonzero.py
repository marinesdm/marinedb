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
def apply(df, latkey, lonkey, flag=False, dropna=True, verbose=True, indent='') -> pd.DataFrame:
    """Flag or exclude records with zero-valued geographic coordinates.

    Latitude or longitude values whose absolute value is less than or equal to
    ``1e-5`` are treated as zero.

    !!! info

        - When ``flag=True``, records with at least one zero-valued coordinate are
        flagged.

        - When ``flag=False``, records with at least one zero-valued coordinate are
        excluded.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        latkey (str):
            Name of the column containing latitude values.

        lonkey (str):
            Name of the column containing longitude values.

        flag (bool, optional):
            If ``True``, add a Boolean column named
            ``flag_<latkey>_<lonkey>_islatlonzero`` flagging records whose
            latitude or longitude is zero. If ``False``, exclude these records.

        dropna (bool, optional):
            Defines how missing latitude or longitude values are handled.

            When ``flag=True``, records with no zero-valued coordinate are assigned
            ``pandas.NA`` in the flag column if either coordinate is missing.
            Records with one zero-valued coordinate are flagged even if the other
            coordinate is missing.

            When ``flag=False``, records with missing coordinates are excluded if
            ``True`` and retained if ``False``.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and a
            nullable Boolean flag column is added. When ``flag=False``, records with
            at least one zero-valued coordinate are excluded and the index is reset.
    """

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

