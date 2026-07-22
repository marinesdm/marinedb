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
def apply(df, latkey, lonkey, flag=False, dropna=True, verbose=True, indent='') -> pd.DataFrame:
    """Flag or exclude records with invalid geographic coordinates.

    Valid latitude values range from -90 to 90 degrees, and 
    valid longitude values from -180 to 180 degrees, with boundary values included.

    !!! warning

        When ``flag=True``, records with invalid coordinates are flagged.

        When ``flag=False``, records with invalid coordinates are excluded.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        latkey (str):
            Name of the column containing latitude values.

        lonkey (str):
            Name of the column containing longitude values.

        flag (bool, optional):
            If ``True``, add a Boolean column named
            ``flag_<latkey>_<lonkey>_islatloninvalid`` flagging records whose
            latitude or longitude falls outside the valid range. If ``False``,
            exclude these records.

        dropna (bool, optional):
            Defines how missing latitude or longitude values are handled.

            When ``True``, records with at least one missing coordinate are
            considered invalid and are therefore flagged or excluded.

            When ``False``, missing coordinates are not considered invalid and are
            retained, unless the other coordinate, if any, falls outside its valid range.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and a
            Boolean flag column is added. When ``flag=False``, records with invalid
            coordinates are excluded and the index is reset.

    Raises:
        ValueError:
            If ``value`` is not an integer.
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
