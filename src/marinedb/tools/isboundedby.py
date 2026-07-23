#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

operator_mapping = {
                    '>':'SUP',
                    '>=':'SUPEQ',
                    '<':'INF',
                    '<=':'INFEQ'
                   }


def value_mapping(str_value):

    if '-' in str_value:
        return f'NEG{str_value[1:]}'
    else:
        return f'POS{str_value}'


@export
def apply(df, key, operator, value, flag=False, dropna=False, verbose=True, indent='') -> pd.DataFrame:
    """Flag or exclude records based on a numeric boundary condition.

    !!! warning

        - When ``flag=True``, records that satisfy the boundary condition are
        flagged (i.e. records where the condition is met are flagged).

        - When ``flag=False``, records that do not satisfy the boundary condition
        are excluded (i.e. records where the condition is not met are excluded).

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the column to inspect.

        operator (str):
            Comparison operator defining the boundary condition. Accepted values
            are ``"<"``, ``"<="``, ``">"`` and ``">="``.

        value (int, float or str):
            Numeric boundary value against which values in ``key`` are compared.

        flag (bool, optional):
            If ``True``, add a Boolean column named ``flag_<key>_isboundedby_<condition>`` 
            flagging records that satisfy the boundary condition. 
            If ``False``, exclude records that do not satisfy the condition.

        dropna (bool, optional):
            Defines how missing values in ``key`` are handled.

            When ``flag=True``, missing values are always assigned ``pandas.NA``
            in the flag column, regardless of the value of ``dropna``.

            When ``flag=False``, missing values are excluded if ``True`` and
            retained if ``False``.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and a
            nullable Boolean flag column is added. When ``flag=False``, records that
            do not satisfy the boundary condition are excluded and the index is reset.

    Raises:
        ValueError:
            If ``operator`` is not a supported comparison operator, or if
            the boundary value or column values cannot be converted to a number.
    """

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    if '<' in operator:
        if '=' in operator:
            isboundedby = (df[key].astype('Float64') <= float(value))
        else:
            isboundedby = (df[key].astype('Float64') < float(value))
    elif '>' in operator:
        if '=' in operator:
            isboundedby = (df[key].astype('Float64') >= float(value))
        else:
            isboundedby = (df[key].astype('Float64') > float(value))
    else:
        raise ValueError("`isboundedby.py` | the comparison operator in `value` should be '<', '>', or a combination of '=' and '<' or '>'.")

    isboundedby = isboundedby.astype('boolean')
    ismissing = pd.isnull(df[key])
    isboundedby[ismissing] = pd.NA

    if flag:
        # Flag rows that satisfy the bounding condition
        condition = '-'.join([operator_mapping[operator], value_mapping(str(value))])
        df[f'flag_{key}_isboundedby_{condition}'] = isboundedby
        return df
    else:
        # Drop rows:
        #   - that DO NOT statisfy the bounding condition
        #   - with missing values in `key` if `dropna`
        isboundedby[ismissing] = (not dropna)
        return df[isboundedby].reset_index(drop=True)
