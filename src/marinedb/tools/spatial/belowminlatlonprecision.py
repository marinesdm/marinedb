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
def apply(df, latkey, lonkey, value, flag=False, dropna=False, verbose=True, indent=''):

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
