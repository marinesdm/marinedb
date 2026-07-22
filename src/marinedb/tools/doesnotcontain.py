#!/usr/bin/python
# coding: utf-8

# External import

import os
import json
import pandas as pd

# Internal import

from marinedb.utils import dictpprint
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, values, flag=False, minimize_flagname=False, flagname_mapping=None, dropna=False, verbose=True, indent='', outputdir='./') -> pd.DataFrame:
    """Flag or exclude records based on values absent from a column.

    !!! warning

        When ``flag=True``, records that do not contain any specified value are
        flagged (i.e. records where the condition is met are flagged).

        When ``flag=False``, records that contain at least one specified value are
        excluded (i.e. records where the condition is not met are excluded).

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
            If ``True``, add a Boolean column flagging records that do not contain
            any specified value. If ``False``, exclude records that contain at
            least one specified value.

        minimize_flagname (bool, optional):
            If ``True``, shorten the generated flag column name. Only applies when
            ``flag=True``.

        flagname_mapping (str or dict, optional):
            Mapping used to shorten the generated flag column name. It can be
            provided as a dictionary or as the path to a JSON file.

            By default, the flag column is named ``flag_<key>_doesnotcontain_<values>``. 
            When ``flagname_mapping`` is provided, searched values used as keys are replaced 
            by their corresponding mapping values in the flag column name.

            This argument is ignored when ``flag=False`` or
            ``minimize_flagname=False``.  When ``minimize_flagname=True`` 
            and no mapping is provided, one is automatically created 
            or updated in ``outputdir``.

        dropna (bool, optional):
            Defines how missing values in ``key`` are handled.

            When ``flag=True``, missing values are always assigned 
            ``pandas.NA`` in the flag column.

            When ``flag=False``, missing values are excluded if ``True`` and
            retained if ``False``.
            
        outputdir (str, optional):
            Directory used to read or save an automatically generated flag-name
            mapping.

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
    """

    if (flagname_mapping is not None) and (len(flagname_mapping) == 0):
        flagname_mapping = None

    if (not flag) and (flagname_mapping is not None):
        printv(f'INFO | Since `flag` is {flag}, `flagname_mapping` will be ignored', verbose=verbose, indent=indent)
        flagname_mapping = None
    if (not minimize_flagname) and (flagname_mapping is not None):
        printv(f'INFO | Since `minimize_flagname` is {minimize_flagname}, `flagname_mapping` will be ignored', verbose=verbose, indent=indent)
        flagname_mapping = None

    if (flagname_mapping is not None):

        if not isinstance(flagname_mapping, str | dict):
            raise ValueError('`doesnotcontain.py` | `flagname_mapping` must be provided as either a dictionary or a JSON file path')

        if isinstance(flagname_mapping, str):
            try:
                with open(flagname_mapping,'r') as file:
                    flagname_mapping = json.load(file)
            except FileNotFoundError:
                raise FileNotFoundError(f"`doesnotcontain.py` | No such file: {flagname_mapping}")
            except json.JSONDecodeError:
                raise ValueError('`doesnotcontain.py` | If a string, `flagname_mapping` must be a path to a valid non-empty JSON file')

    if minimize_flagname and (flagname_mapping is None):

        outputfile = os.path.join(outputdir,f'{key}_doesnotcontain_mapping.json')
        flagname_mapping = {}

        if os.path.isfile(outputfile):

            printv(f'INFO | {outputfile} already exists and will be used', verbose=verbose, indent=indent)

            try:
                with open(outputfile,'r') as file:
                    flagname_mapping = json.load(file)
            except json.JSONDecodeError:
                printv(
                f'WARNING | {outputfile} is empty or invalid JSON, starting from an empty mapping.',
                verbose=verbose,
                indent=indent
                )
                flagname_mapping = {}

        if not flagname_mapping:
            start_idx = 0
        else:
            temp = {}
            num = []
            for k,v in flagname_mapping.items():
                try:
                    temp[str(k)] = int(v)
                    num.append(int(v))
                except:
                    temp[str(k)] = v
            flagname_mapping = temp
            if len(num) != 0:
                start_idx = max(num) + 1
            else:
                start_idx = 0

        value_str = [str(val) for val in values]
        value_update = list(set(value_str) - set(list(flagname_mapping.keys())))
        value_update = {val: (start_idx + idx) for idx, val in enumerate(value_update)}
        if len(value_update) != 0:
            flagname_mapping.update(value_update)
            printv(f'INFO | `flagname_mapping` is set to:', verbose=verbose, indent=indent)
            dictpprint.apply(flagname_mapping, verbose=verbose, indent=indent+'      ')
            printv(f'INFO | Save `flagname_mapping` to {outputfile}', verbose=verbose, indent=indent)
            with open(outputfile, 'w', encoding='utf-8') as file:
                json.dump(flagname_mapping, file, ensure_ascii=False, indent=4)

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Filtering conditions

    if isinstance(values, str):
        values = [values]
        pattern_values = values
    else:
        values = [str(val) for val in values]
        pattern_values = [f'(?:{val})' for val in values]
    searchfor = '|'.join(pattern_values)

    df['tempcol'] = df[key].copy()
    df['tempcol'] = df['tempcol'].astype('string')

    doesnotcontain = (~df['tempcol'].str.contains(rf'{searchfor}', regex=True, na=dropna))
    doesnotcontain = doesnotcontain.astype('boolean')
    ismissing = pd.isnull(df['tempcol'])

    df.drop(columns='tempcol', inplace=True)

    if flag:

        # Flag rows where the `key` column DOES NOT contain values in `values`

        if flagname_mapping is not None:
            temp = flagname_mapping.copy()
            for k in flagname_mapping.keys():
                v = str(temp.pop(k))
                if len(v) != 0:
                    temp[str(k)] = v
            flagname_mapping = temp
            colname_values = '-'.join([flagname_mapping.get(val, val) for val in values])
        else:
            colname_values = '-'.join(values)

        doesnotcontain[ismissing] = pd.NA
        df[f'flag_{key}_doesnotcontain_{colname_values}'] = doesnotcontain

        return df

    else:

        # Drop rows:
        #   - where `key` CONTAINS values in `values`
        #   - with missing values in `key` if `dropna`

        return df[doesnotcontain].reset_index(drop=True)
