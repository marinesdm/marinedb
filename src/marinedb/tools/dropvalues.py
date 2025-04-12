#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
import re

# Internal import

from marinedb.utils.allexport import export
from marinedb.tools import getcolumnname
from marinedb.tools import aligndtypes

# Global variables

__all__ = [] # populated using the @export decorator


@export
def apply(df, dropna=False, **conditions):

    OR_condition = None

    for key, value in conditions.items():
        print('key,value:',key,value) #DEBUG

        df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

        # Ensure that the objects being compared are of the same type

        df, value = aligndtypes.apply(df, key, value)
        if not isinstance(value, list):
            value = [value]

        # Filtering conditions

        if dropna:
            condition = (pd.isnull(df[key]) | df[key].isin(value))
        else:
            condition = ((~pd.isnull(df[key])) & df[key].isin(value))

        if OR_condition is None:
            OR_condition = condition
        else:
            OR_condition = (OR_condition | condition)

    # Drop rows satisfying any of the specified conditions
    # Note: rows with missing values in the filter columns are removed

    df = df[~OR_condition].reset_index(drop=True)

    return df
