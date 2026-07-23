#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname
from marinedb.tools.spatial import belowminfloatprecision as mfp

# Global variable

__all__ = [] # populated using the @export decorato

@export
def apply(df, latkey, lonkey, value, flag=False, dropna=False, verbose=True, indent='') -> pd.DataFrame:
    """Flag or exclude records with insufficient decimal-place coordinate precision.

    Decimal-place precision is measured as the number of digits after the decimal
    point, retaining the higher precision when latitude and longitude differ. 
    A record falls below the threshold when both coordinates have
    fewer decimal places than the specified minimum.

    !!! info

        - When ``flag=True``, records where both coordinates fall below the minimum
        precision are flagged.

        - When ``flag=False``, records where both coordinates fall below the minimum
        precision are excluded.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        latkey (str):
            Name of the column containing latitude values.

        lonkey (str):
            Name of the column containing longitude values.

        value (int):
            Minimum required number of decimal places.

            A record meets the condition only when both latitude and longitude
            contain fewer than ``value`` decimal places.

        flag (bool, optional):
            If ``True``, add a nullable Boolean column named
            ``flag_<latkey>_<lonkey>_belowminlatlonprecision_<value>`` flagging
            records where both coordinates fall below the minimum precision.

            A column named
            ``<latkey>_<lonkey>_floatprecision_generatedby_belowminlatlonprecision``
            is also added, containing the highest number of decimal places found
            between latitude and longitude.

            If ``False``, exclude records where both coordinates fall below the
            minimum precision.

        dropna (bool, optional):
            Defines how missing latitude or longitude values are handled.

            When ``flag=True``, records with at least one missing coordinate are
            assigned ``pandas.NA`` in the generated flag and precision columns.

            When ``flag=False``, records with at least one missing coordinate are
            excluded if ``True`` and retained if ``False``.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and
            nullable flag and precision columns are added. When ``flag=False``,
            records where both coordinates fall below the minimum precision are
            excluded and the index is reset.
    """

    df, latkey, _ = getcolumnname.apply(df, latkey, '', inplace=True)
    df, lonkey, _ = getcolumnname.apply(df, lonkey, '', inplace=True)

    # Apply `belowminfloatprecision` separately to latitude and longitude

    printv('', verbose=verbose)
    printv(f"* Apply `belowminfloatprecision` to '{latkey}'", verbose=verbose, indent=indent)
    df = mfp.apply(df, latkey, value, flag=True, dropna=dropna, verbose=verbose, indent=(indent + '  '))
    printv('', verbose=verbose)
    printv(f"* Apply `belowminfloatprecision` to '{lonkey}'", verbose=verbose, indent=indent)
    df = mfp.apply(df, lonkey, value, flag=True, dropna=dropna, verbose=verbose, indent=(indent + '  '))
    printv('', verbose=verbose)

    columns = list(df.columns)
    flag_columns = [col for col in columns if ('flag' in col) and ('belowminfloatprecision' in col)]
    assert len(flag_columns) == 2
    precision_columns = [col for col in columns if ('generatedby' in col) and ('belowminfloatprecision' in col)]
    assert len(precision_columns) == 2
    dropcolumns = flag_columns + precision_columns

    # Check whether the float precision of latitude and longitude is below `value`

    is_below_minlatlonprecision = (df[flag_columns[0]] & df[flag_columns[1]])
    is_below_minlatlonprecision = is_below_minlatlonprecision.astype('boolean')
    ismissing = (pd.isnull(df[latkey]) | pd.isnull(df[lonkey]))
    is_below_minlatlonprecision[ismissing] = pd.NA

    printv(f'* Flag and/or filter', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    if flag:

        # Flag rows where latitude and longitude precision falls below `value` decimal places

        ## Precision
        precision = df[precision_columns].max(axis=1).astype('Int64')
        precision[ismissing] = pd.NA
        df[f'{latkey}_{lonkey}_floatprecision_generatedby_belowminlatlonprecision'] = precision

        ## Flag
        df[f'flag_{latkey}_{lonkey}_belowminlatlonprecision_{str(value)}'] = is_below_minlatlonprecision

        ## Clean
        df.drop(columns=dropcolumns, inplace=True)

        return df

    else:

        # Drop rows:
        #   - where latitude and longitude precision falls below `value` decimal places
        #   - with missing latitude and/or longitude when `dropna`

        ## Apply missing data handling strategy
        is_below_minlatlonprecision[ismissing] = dropna

        ## Clean
        df.drop(columns=dropcolumns, inplace=True)

        return df[~is_below_minlatlonprecision].reset_index(drop=True)
