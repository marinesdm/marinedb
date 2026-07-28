#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import isin
from marinedb.tools import getcolumnname
from marinedb.tools.taxonomic import mapbasisofrecord

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key=None, values=None, dropna=False, std=False, std_additional_values=None, std_inplace=False, flag=True, verbose=True, indent=''):
    """Flag or remove records based on basis-of-record categories.

    Compares values in a basis-of-record column against a user-specified
    set of categories. The source column can be selected explicitly or, 
    when possible, detected automatically among columns whose names contain 
    `basisOfRecord`.

    Optionally, source values can first be standardized with
    `mapbasisofrecord`. This allows the function to operate on existing
    basis-of-record values or on other fields, such as sampling protocols,
    when an appropriate mapping is available.

    !!! warning

        - When `flag=True`, records matching one of the specified values are
        flagged (i.e. records where the condition is met are flagged).

        - When `flag=False`, records that do not match any specified value are
        excluded (i.e. records where the condition is not met are excluded).

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str, optional):
            Name of the column to evaluate. When omitted, the function
            attempts to identify an unambiguous column whose name contains
            `basisOfRecord`. This argument is required when `std=True`.

        values (str or collection of str):
            Basis-of-record category or categories against which the evaluated
            values are compared. 

        dropna (bool, optional):
            Whether to exclude records with missing values when `flag=False`.
            When `dropna=False`, missing values are retained. This parameter 
            has no effect when `flag=True`.

        std (bool, optional):
            Whether to standardize the source values with `mapbasisofrecord` 
            before evaluating them. 

        std_additional_values (dict, optional):
            Additional mappings passed to `mapbasisofrecord` when
            `std=True`. Matching is case-insensitive, and mapped values must
            be supported Darwin Core basis-of-record categories.

        std_inplace (bool, optional):
            Whether to retain the original source column when standardizing
            values. When `False`, the original column is retained. When `True`,
            it is replaced by the processed column. The processed column name
            records the `mapbasisofrecord` step in both cases.

        flag (bool, optional):
            Whether to add a Boolean flag instead of removing records. When
            `True`, all records are retained and the generated flag is `True` 
            for values included in `values`. When `False`, only records whose 
            values are included in `values` are retained, together with missing 
            values when `dropna=False`.

    Returns:
        (pandas.DataFrame):
            Processed DataFrame. When `flag=True`, all records are retained
            and a Boolean flag identifies values included in `values`. When 
            `flag=False`, only records matching one of the specified values
            are retained, together with missing values when `dropna=False`.

    Raises:
        ValueError:
            If `values` is not specified, or if `key` is omitted when
            `std=True`.
        Exception:
            If `key` is omitted and no unambiguous `basisOfRecord` column
            can be identified.

    Notes:
        Standardization is performed before category testing when
        `std=True`. Values not recognized by either the default or
        user-provided mapping are standardized to `OCCURRENCE` before the
        requested categories are evaluated.
    """

    if values is None:
        raise ValueError(f"`basisofrecordisin.py` | `values` must be specified")

    if (key is None) or (len(key) == 0):

        if std:
            raise ValueError(f"`basisofrecordisin.py` | `key` must be specified when `std=True` to standardize basis of record values")

        columns = list(df.columns)
        basisofrecord_column = [col for col in columns if ('basisOfRecord' in col)]

        if len(basisofrecord_column) == 0:
            raise Exception(f"`basisofrecordisin.py` | No column containing 'basisOfRecord' was found. Please specify the `key` argument explicitly.")

        if len(basisofrecord_column) > 1:

            basisofrecord_column_min = min(basisofrecord_column, key=len)
            doescontain = [basisofrecord_column_min in col for col in basisofrecord_column]
            doescontain = all(doescontain)

            if not doescontain:
                raise Exception(f"`basisofrecordisin.py` | Multiple columns containing 'basisOfRecord' was found. Please specify the `key` argument explicitly.")

            key = basisofrecord_column_min

        else:

            key = basisofrecord_column[0]

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    if std:
        columns_before = set(df.columns)
        df = mapbasisofrecord.apply(df, key, additional_values=std_additional_values, inplace=std_inplace, verbose=verbose, indent=indent)
        columns_after = set(df.columns)
        keyout = columns_after - columns_before
        assert len(keyout) == 1
        key = list(keyout)[0]

    df = isin.apply(df, key, values, flag=flag, dropna=dropna, verbose=verbose, indent=indent)

    return df
