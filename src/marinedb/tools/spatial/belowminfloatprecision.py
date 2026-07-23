#!/usr/bin/python
# coding: utf-8

# External import

import numpy as np
import pandas as pd


# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator

def get_floatprecision(series_flt):

    series_flt = series_flt.astype('string')
    series_flt = series_flt.str.strip()
    series_flt = series_flt.str.split(pat='.')
    precision = np.where(series_flt.str.len().eq(1) | series_flt.str[1].eq(''), 0, series_flt.str[1].str.len())

    return pd.Series(precision, index=series_flt.index)

@export
def apply(df, key, value, flag=False, dropna=False, verbose=True, indent='') -> pd.DataFrame:
    """Flag or exclude records with insufficient decimal-place precision.

    Decimal-place precision is measured as the number of digits after the decimal
    point. A value falls below the threshold when it has fewer decimal places than
    the specified minimum.

    !!! info

        - When ``flag=True``, records below the minimum precision are flagged.

        - When ``flag=False``, records below the minimum precision are excluded.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the column to inspect.

        value (int):
            Minimum required number of decimal places.

        flag (bool, optional):
            If ``True``, add a nullable Boolean column named
            ``flag_<key>_belowminfloatprecision_<value>`` flagging records below
            the minimum precision.

            A column named
            ``<key>_floatprecision_generatedby_belowminfloatprecision`` is also
            added, containing the number of decimal places detected for each
            value.

            If ``False``, exclude records below the minimum precision.

        dropna (bool, optional):
            Defines how missing values in ``key`` are handled.

            When ``flag=True``, missing values are assigned ``pandas.NA`` in the
            flag column.

            When ``flag=False``, missing values are excluded if ``True`` and
            retained if ``False``.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and
            precision and flag columns are added. When ``flag=False``, records below
            the minimum precision are excluded, the temporary precision column is
            removed, and the index is reset.

    Raises:
        ValueError:
            If ``value`` is not an integer.
    """

    if not isinstance(value,int):
        raise ValueError(f'`belowminfloatprecision.py` | `value` must be an integer (value={value})')

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Compute the number of digits after the decimal point

    printv(f'* Count the number of decimal places', verbose=verbose, indent=indent)

    precision_column = f'{key}_floatprecision_generatedby_belowminfloatprecision'
    if precision_column in df.columns:
        printv(f'INFO | {precision_column} column already exists and will be used', verbose=verbose, indent=indent)
    else:
        df[precision_column] = get_floatprecision(df[key]).astype('Int64')

    # Check whether the float precision of `key` is below `value`

    is_below_minfloatprecision = (df[precision_column] < value)
    is_below_minfloatprecision = is_below_minfloatprecision.astype('boolean')
    ismissing = pd.isnull(df[key].astype('Float64'))
    is_below_minfloatprecision[ismissing] = pd.NA

    printv(f'* Flag and/or filter', verbose=verbose, indent=indent)

    if flag:

        # Flag rows where the float precision of `key` is below `value`

        df[f'flag_{key}_belowminfloatprecision_{str(value)}'] = is_below_minfloatprecision

        return df

    else:

        # Drop rows:
        #   - where the float precision of `key` is below `value`
        #   - with missing values in `key` if `dropna`

        ## Apply missing data handling strategy
        is_below_minfloatprecision[ismissing] = dropna

        ## Clean
        df.drop(columns=[precision_column], inplace=True)

        return df[~is_below_minfloatprecision].reset_index(drop=True)
