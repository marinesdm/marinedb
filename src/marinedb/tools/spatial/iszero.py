#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils.allexport import export

from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, flag=False, eps=1e-5, dropna=False, verbose=True, indent='') -> pd.DataFrame:
    """Flag or exclude records with values equal or close to zero.

    Values whose absolute value is less than or equal to ``eps`` are treated as
    zero.

    !!! info

        - When ``flag=True``, records with zero-valued entries are flagged.

        - When ``flag=False``, records with zero-valued entries are excluded.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the column to inspect.

        flag (bool, optional):
            If ``True``, add a nullable Boolean column named
            ``flag_<key>_iszero`` flagging records with values equal or close to
            zero. If ``False``, exclude these records.

        eps (float, optional):
            Maximum absolute value treated as zero. A record meets the condition
            when ``abs(value) <= eps``. Defaults to ``1e-5``.

        dropna (bool, optional):
            Defines how missing values in ``key`` are handled.

            When ``flag=True``, missing values are always assigned ``pandas.NA``
            in the flag column, regardless of the value of ``dropna``.

            When ``flag=False``, missing values are excluded if ``True`` and
            retained if ``False``.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and a
            nullable Boolean flag column is added. When ``flag=False``, records with
            values equal or close to zero are excluded and the index is reset.
    """

    # default eps: 1e-5
    #   - GBIF coordinates are rounded to six decimal places
    #   - 5 decimal places = 1 meter precision at the equator 

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    iszero = (df[key].astype('Float64').abs() <= eps)
    iszero = iszero.astype('boolean')
    ismissing = pd.isnull(df[key])
    iszero[ismissing] = pd.NA

    if flag:
        # Flag rows with null values in the `key` column
        df[f'flag_{key}_iszero'] = iszero
        return df
    else:
        # Drop rows:
        #   - with null values in `key`
        #   - with missing values in `key` if `dropna`
        iszero[ismissing] = dropna
        return df[~iszero].reset_index(drop=True)
