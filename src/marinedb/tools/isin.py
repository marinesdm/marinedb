#!/usr/bin/python
# coding: utf-8

# External import

import os
import json
import pandas as pd

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname
from marinedb.tools import aligndtypes

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, values, flag=False, minimize_flagname=False, flagname_mapping=None, dropna=False, verbose=True, indent='', outputdir='./') -> pd.DataFrame:
    """Flag or exclude records based on exact values in a column.

    !!! warning

        - When ``flag=True``, records matching one of the specified values are
        flagged (i.e. records where the condition is met are flagged).

        - When ``flag=False``, records that do not match any specified value are
        excluded (i.e. records where the condition is not met are excluded).

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the column to inspect.

        values (Any or list):
            Value or values to search for. When several values are provided, a
            record is considered a match if its value equals any of them.

        flag (bool, optional):
            If ``True``, add a Boolean column flagging records that match one of
            the specified values. If ``False``, exclude records that do not match
            any specified value.

        minimize_flagname (bool, optional):
            If ``True``, shorten the generated flag column name. Only applies when
            ``flag=True``.

        flagname_mapping (str or dict, optional):
            Mapping used to shorten the generated flag column name. It can be
            provided as a dictionary or as the path to a JSON file.
    
            By default, the flag column is named ``flag_<key>_isin_<values>``. 
            When ``flagname_mapping`` is provided, searched values used as keys are replaced 
            by their corresponding mapping values in the flag column name.

            This argument is ignored when ``flag=False`` or
            ``minimize_flagname=False``.  When ``minimize_flagname=True`` 
            and no mapping is provided, one is automatically created 
            or updated in ``outputdir/<key>_isin_mapping.json``.

        dropna (bool, optional):
            Defines how missing values in ``key`` are handled.

            When ``flag=True``, missing values are always assigned 
            ``pandas.NA`` in the flag column.

            When ``flag=False``, missing values are excluded if ``True`` and
            retained if ``False``.
            
        outputdir (str, optional):
            Directory containing the automatically generated
            ``<key>_isin_mapping.json`` file.

    Returns:
        Processed DataFrame. When ``flag=True``, all records are retained and
            a nullable Boolean flag column is added. When ``flag=False``, records that
            do not match any specified value are excluded and the index is reset.

    Raises:
        ValueError:
            If ``flagname_mapping`` has an invalid type or contains invalid JSON.

        FileNotFoundError:
            If the path provided through ``flagname_mapping`` does not exist.
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
            raise ValueError('`isin.py` | `flagname_mapping` must be provided as either a dictionary or a JSON file path')
        if isinstance(flagname_mapping, str):
            try:
                with open(flagname_mapping,'r') as file:
                    flagname_mapping = json.load(file)
            except ValueError:
                raise ValueError('`isin.py` | if a string, `flagname_mapping` must be a path to a valid JSON file')

    if minimize_flagname and (flagname_mapping is None):
        outputfile = os.path.join(outputdir,f'{key}_isin_mapping.json')
        if os.path.isfile(outputfile):
            printv(f'INFO | {outputfile} already exists and will be used', verbose=verbose, indent=indent)
            with open(outputfile,'r') as file:
                flagname_mapping = json.load(file)
            temp = {}
            for k,v in flagname_mapping.items():
                temp[str(k)] = int(v)
            flagname_mapping = temp
            start_idx = max(list(flagname_mapping.values())) + 1
        else:
            flagname_mapping = {}
            start_idx = 0
        value_str = [str(val) for val in values]
        value_update = list(set(value_str) - set(list(flagname_mapping.keys())))
        value_update = {val: (start_idx + idx) for idx, val in enumerate(value_update)}
        flagname_mapping.update(value_update)
        printv(f'INFO | `flagname_mapping` is set to {flagname_mapping}', verbose=verbose, indent=indent)
        printv(f'INFO | Save `flagname_mapping` to {outputfile}', verbose=verbose, indent=indent)
        with open(outputfile, 'w', encoding='utf-8') as file:
            json.dump(flagname_mapping, file, ensure_ascii=False, indent=4)

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Ensure that the objects being compared are of the same type

    df, values = aligndtypes.apply(df, key, values)
    if not isinstance(values, list):
        values = [values]

    # Filtering condition

    condition = df[key].isin(values)
    condition = condition.astype('boolean')
    ismissing = pd.isnull(df[key])
    condition[ismissing] = pd.NA

    if flag:

        # Flag rows where `key` values are in `values`

        if flagname_mapping is not None:
            temp = flagname_mapping.copy()
            for k in flagname_mapping.keys():
                temp[str(k)] = temp.pop(k)
            flagname_mapping = temp
            values_str = '-'.join([str(flagname_mapping[str(val)]) for val in values])
        else:
            values_str = '-'.join([str(val) for val in values])

        df[f'flag_{key}_isin_{values_str}'] = condition

        return df

    else:

        # Drop rows where `key` values are NOT in `values`
        # Note: rows with missing values in the `key` column are removed

        condition[ismissing] = (not dropna)

        return df[condition].reset_index(drop=True)
