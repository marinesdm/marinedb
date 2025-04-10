#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.utils.allexport import export
from marinedb.tools import minfloatprecision as mfp

# Global variable

__all__ = [] # populated using the @export decorato

@export
def apply(df, keylat, keylon, value, flag=False, dropna=False, indent=''):

    df, keylat, _ = getcolumnname.apply(df, keylat, '', inplace=True)
    df, keylon, _ = getcolumnname.apply(df, keylon, '', inplace=True)

    # Apply `minfloatprecision` separately to latitude and longitude

    print(indent + f'* minlatlonprecision | minfloatprecision for {keylat}')
    df = mfp.apply(df, keylat, value, flag=True, dropna=dropna, indent=(indent + '  '))
    print(indent + f'* minlatlonprecision | minfloatprecision for {keylon}')
    df = mfp.apply(df, keylon, value, flag=True, dropna=dropna, indent=(indent + '  '))

    columns = list(df.columns)
    flag_columns = [col for col in columns if ('flag' in col) and ('minfloatprecision' in col)]
    assert len(flag_columns) == 2
    precision_columns = [col for col in columns if ('generatedby' in col) and ('minfloatprecision' in col)]
    assert len(precision_columns) == 2
    dropcolumns = flag_columns + precision_columns

    # Check whether the float precision of latitude and longitude is below `value`

    isbelow_minlatlonprecision = (df[flag_columns[0]] & df[flag_columns[1]])
    ismissing = (pd.isnull(df[keylat]) | pd.isnull(df[keylon]))
    isbelow_minlatlonprecision[ismissing] = pd.NA

    if flag:

        # Flag rows where latitude and longitude precision falls below `value` decimal places

        ## Precision
        precision = df[precision_columns].max(axis=1).astype('Int64')
        precision[ismissing] = pd.NA
        df[f'{keylat}_{keylon}_floatprecision_generatedby_minlatlonprecision'] = precision

        ## Flag
        df[f'flag_{keylat}_{keylon}_minlatlonprecision_{str(value)}'] = isbelow_minlatlonprecision

        ## Clean
        df.drop(columns=dropcolumns, inplace=True)

        return df

    else:

        # Drop rows:
        #   - where latitude and longitude precision falls below `value` decimal places
        #   - with missing latitude and/or longitude when `dropna`

        ## Apply missing data handling strategy
        isbelow_minlatlonprecision[ismissing] = dropna

        ## Clean
        df.drop(columns=dropcolumns, inplace=True)

        return df[~isbelow_minlatlonprecision].reset_index(drop=True)
