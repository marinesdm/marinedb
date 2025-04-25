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
def apply(df, key, values, flag=False, minimize_flagname=False, flagname_mapping=None, dropna=False, verbose=True, indent='', outputdir='./'):

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
