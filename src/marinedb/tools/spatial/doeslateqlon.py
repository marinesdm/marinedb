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
def apply(df, latkey, lonkey, flag=False, eps=1e-5, dropna=False, verbose=True, indent='') -> pd.DataFrame:
    """Flag or exclude records with equal latitude and longitude values.

    Latitude and longitude are considered equal when their absolute difference is
    less than or equal to ``eps``.

    !!! info

        - When ``flag=True``, records with equal latitude and longitude values are
        flagged.

        - When ``flag=False``, records with equal latitude and longitude values are
        excluded.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        latkey (str):
            Name of the column containing latitude values.

        lonkey (str):
            Name of the column containing longitude values.

        flag (bool, optional):
            If ``True``, add a nullable Boolean column named
            ``flag_<latkey>_<lonkey>_doeslateqlon`` flagging records with equal
            latitude and longitude values. If ``False``, exclude these records.

        eps (float, optional):
            Maximum absolute difference for latitude and longitude to be treated as
            equal. A record meets the condition when
            ``abs(latitude - longitude) <= eps``. Defaults to ``1e-5``.

        dropna (bool, optional):
            Defines how missing latitude or longitude values are handled.

            When ``flag=True``, records with at least one missing coordinate are
            assigned ``pandas.NA`` in the flag column.

            When ``flag=False``, records with at least one missing coordinate are
            excluded if ``True`` and retained if ``False``.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and a
            nullable Boolean flag column is added. When ``flag=False``, records with
            equal latitude and longitude values are excluded and the index is reset.
    """

    # default eps: 1e-5
    #   - GBIF coordinates are rounded to six decimal places
    #   - 5 decimal places = 1 meter precision at the equator

    df, latkey, _ = getcolumnname.apply(df, latkey, '', inplace=True)
    df, lonkey, _ = getcolumnname.apply(df, lonkey, '', inplace=True)

    isequal = (df[latkey].astype('Float64') - df[lonkey].astype('Float64')).abs() <= eps
    isequal = isequal.astype('boolean')
    ismissing = (pd.isnull(df[latkey]) | pd.isnull(df[lonkey]))
    isequal[ismissing] = pd.NA

    if flag:
        # Flag rows where latitude and longitude are equal
        df[f'flag_{latkey}_{lonkey}_doeslateqlon'] = isequal
        return df
    else:
        # Drop rows:
        #   - where latitude and longitude are equal
        #   - with missing latitude and/or longitude when `dropna`
        isequal[ismissing] = dropna
        return df[~isequal].reset_index(drop=True)
