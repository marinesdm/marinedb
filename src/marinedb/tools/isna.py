#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.utils import standardizenan
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, stdnan=True, nan_values=None, stdnan_additional_policy='', flag=False, verbose=True, indent='') -> pd.DataFrame:
    """Flag or exclude records with missing values in a column.

    Missing-value placeholders and uninformative field values can optionally 
    be standardized before records are flagged or excluded.

    !!! warning

        When ``flag=True``, records with missing values are flagged.

        When ``flag=False``, records with missing values are excluded.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the column to inspect.

        stdnan (bool, optional):
            If ``True``, standardize missing-value placeholders to ``pandas.NA``
            before identifying missing values.

            If ``False``, only values already recognized as missing by pandas are
            identified.

        nan_values (str or list, optional):
            Additional values to interpret as missing. These values are added to
            the default list of common missing-value placeholders, such as
            ``"NA"``, ``"NULL"``, ``"NaN"``, ``"None"`` and empty strings.

            Only applies when ``stdnan=True``.

        stdnan_additional_policy (str, optional):
            Minimal content rule used to identify uninformative values as missing. 
            Accepted values are:

            - ``"contains_letters"``: require at least one letter
            - ``"contains_digits"``: require at least one digit
            - ``"contains_letters_or_digits"``: require at least one letter or digit

            Values that do not meet the selected rule are converted to ``pandas.NA``. 
            For example, requiring a digit can retain a value such as ``"10 m"`` 
            while treating ``"?"`` as missing for depth.

            This rule only checks whether the field contains minimal informative
            content; it does not validate the reported value itself. Only applies 
            when ``stdnan=True``.

        flag (bool, optional):
            If ``True``, add a Boolean column named ``flag_<key>_isna`` flagging
            records with missing values. If ``False``, exclude records with
            missing values.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and a
            Boolean flag column is added. When ``flag=False``, records with missing
            values are excluded and the index is reset.

    Raises:
        ValueError:
            If ``stdnan_additional_policy`` is not one of the accepted values.
    """

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    if stdnan:
        df = standardizenan.apply(df, key=key, nan_values=nan_values, additional_policy=stdnan_additional_policy)

    ismissing = pd.isnull(df[key])

    if flag:
        # Flag rows with missing values in the `key` column
        df[f'flag_{key}_isna'] = ismissing
        return df

    else:
        # Drop rows with missing values in the `key` column
        return df[~ismissing].reset_index(drop=True)
