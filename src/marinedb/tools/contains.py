#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.tools import doesnotcontain
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, values, flag=False, minimize_flagname=False, flagname_mapping=None, dropna=False, verbose=True, indent='', outputdir='./') -> pd.DataFrame:
    """Flag or exclude records based on values found in a column.

    !!! warning

        When ``flag=True``, records that contain at least one specified value are
        flagged (i.e. records where the condition is met are flagged).

        When ``flag=False``, records that do not contain any specified value are
        excluded (i.e records where the condition is not met are excluded).

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the column to inspect.

        values (str or list):
            Value or values to search for. When several values are provided, a
            record is considered a match if it contains at least one of them.

            Values are interpreted as regular-expression patterns. Special
            characters such as ``.``, ``*``, ``+``, ``?``, ``(``, ``)``, 
            ```[```, ```]``` and ``|`` must be escaped with a backslash when 
            they are intended as literal characters. For example, use ``\\.`` 
            to search for a literal period. See *Advanced usage* below.

        flag (bool, optional):
            If ``True``, add a Boolean column flagging records that contain
            at least one specified value. If ``False``, exclude records that
            do not contain any specified value.

        minimize_flagname (bool, optional):
            If ``True``, shorten the generated flag column name.
            Only applies when ``flag=True``.

        flagname_mapping (str or dict, optional):
            Mapping used to shorten the generated flag column name. It can be
            provided as a dictionary or as the path to a JSON file.

            By default, the flag column is named ``flag_<key>_contains_<values>``. 
            When ``flagname_mapping`` is provided, searched values used as keys are replaced 
            by their corresponding mapping values in the flag column name.

            This argument is ignored when ``flag=False`` or
            ``minimize_flagname=False``.  When ``minimize_flagname=True`` 
            and no mapping is provided, one is automatically created 
            or updated in ``outputdir/<key>_doesnotcontain_mapping.json``.
            See Note 2 below.

        dropna (bool, optional):
            Defines how missing values in ``key`` are handled.

            When ``flag=True``, missing values are always assigned 
            ``pandas.NA`` in the flag column.

            When ``flag=False``, missing values are excluded if ``True`` and
            retained if ``False``.
            
        outputdir (str, optional):
            Directory containing the automatically generated 
            ``<key>_doesnotcontain_mapping.json`` file.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and
            a nullable Boolean flag column is added. When ``flag=False``, matching
            records are excluded and the index is reset.

    Raises:
        ValueError:
            If ``flagname_mapping`` has an invalid type or contains invalid JSON.

        FileNotFoundError:
            If the path provided through ``flagname_mapping`` does not exist.

    !!! tip "Advanced usage"
        Regular expressions can be used for advanced searches. See Python's
        regular-expression documentation for the supported syntax.
    
    !!! note "Note"
        ``contains`` and ``doesnotcontain`` share the same flag-name mapping file.
    """

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Run `doesnotcontain` on the `key` column

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
        df = doesnotcontain.apply(df, key, values, **params)
    except Exception as err:
        raise type(err)(f"`contains.py` | {str(err).split('|')[-1]}") from err

    diff_columns = list(set(df.columns) - columns_before)
    doesnotcontain_flagcolumn = [col for col in diff_columns if (f'flag_{key}_doesnotcontain' in col)]
    assert len(doesnotcontain_flagcolumn) == 1
    doesnotcontain_flagcolumn = doesnotcontain_flagcolumn[0]
    value_str = '_'.join(doesnotcontain_flagcolumn.split('_')[3:])

    # Apply missing data handling strategy

    ismissing = pd.isnull(df[doesnotcontain_flagcolumn])
    df.loc[ismissing, doesnotcontain_flagcolumn] = dropna

    doescontain = (~df[doesnotcontain_flagcolumn])

    # Clean

    df.drop(columns=doesnotcontain_flagcolumn, inplace=True)

    if flag:

        # Flag rows where the `key` column contains values in `values`

        doescontain[ismissing] = pd.NA
        df[f'flag_{key}_contains_{value_str}'] = doescontain

        return df

    else:

        # Drop rows:
        #   - where `key` DOES NOT contain values in `values`
        #   - with missing values in `key` if `dropna`

        return df[doescontain].reset_index(drop=True)
