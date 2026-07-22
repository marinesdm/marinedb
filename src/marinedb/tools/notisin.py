#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
import re

# Internal import

from marinedb.utils.allexport import export
from marinedb.tools import getcolumnname
from marinedb.tools import isin

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, values, flag=False, minimize_flagname=False, flagname_mapping=None, dropna=False, verbose=True, indent='', outputdir='./')  -> pd.DataFrame:
    """Flag or exclude records based on exact values absent from a column.

    !!! warning

        When ``flag=True``, records that do not match any specified value are
        flagged (i.e. records where the condition is met are flagged).

        When ``flag=False``, records matching one of the specified values are
        excluded (i.e. records where the condition is not met are excluded).

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the column to inspect.

        values (str or list):
            Value or values to search for. When several values are provided, a
            record is considered a match if its value equals any of them.

        flag (bool, optional):
            If ``True``, add a Boolean column flagging records that do not match
            any specified value. If ``False``, exclude records that match one of
            the specified values.

        minimize_flagname (bool, optional):
            If ``True``, shorten the generated flag column name. Only applies when
            ``flag=True``.

        flagname_mapping (str or dict, optional):
            Mapping used to shorten the generated flag column name. It can be
            provided as a dictionary or as the path to a JSON file.

            By default, the flag column is named
            ``flag_<key>_notisin_<values>``. When ``flagname_mapping`` is provided,
            searched values used as keys are replaced by their corresponding
            mapping values in the flag column name.

            This argument is ignored when ``flag=False`` or
            ``minimize_flagname=False``. When ``minimize_flagname=True`` and no
            mapping is provided, one is automatically created or updated in
            ``outputdir/<key>_isin_mapping.json``. See Note below.

        dropna (bool, optional):
            Defines how missing values in ``key`` are handled.

            When ``flag=True``, missing values are always assigned ``pandas.NA``
            in the flag column.

            When ``flag=False``, missing values are excluded if ``True`` and
            retained if ``False``.

        outputdir (str, optional):
            Directory containing the automatically generated
            ``<key>_isin_mapping.json`` file.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and a
            nullable Boolean flag column is added. When ``flag=False``, records
            matching one of the specified values are excluded and the index is reset.

    Raises:
        Exception:
            If the underlying ``isin`` operation fails.

    !!! note
        ``isin`` and ``notisin`` share the same flag-name mapping file.
    """

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Run `isin` on the `key` column

    params = {
              'flag': True,
              'minimize_flagname': minimize_flagname,
              'flagname_mapping': flagname_mapping,
              'dropna': False,
              'verbose': verbose,
              'indent': indent,
              'outputdir': outputdir
             }

    columns_before = set(df.columns)

    try:
        df = isin.apply(df, key, values, **params)
    except Exception as err:
        raise Exception(f"`notisin.py` | {str(err).split('|')[-1]}")

    diff_columns = list(set(df.columns) - columns_before)
    flagcolumn = [col for col in diff_columns if (f'flag_{key}_isin' in col)]
    assert len(flagcolumn) == 1
    flagcolumn = flagcolumn[0]
    values_str = re.sub(f'flag_{key}_isin_', '', flagcolumn)

    # Apply missing data handling strategy

    ismissing = pd.isnull(df[flagcolumn])
    df.loc[ismissing, flagcolumn] = dropna

    notisin = (~df[flagcolumn]).copy()

    # Clean

    df.drop(columns=flagcolumn, inplace=True)

    if flag:

        # Flag rows where `key` values ARE NOT in `values`

        notisin[ismissing] = pd.NA
        df[f'flag_{key}_notisin_{values_str}'] = notisin

        return df

    else:

        # Drop rows:
        #   - where `key` values ARE in `values`
        #   - with missing values in `key` if `dropna`

        return df[notisin].reset_index(drop=True)


