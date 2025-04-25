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
            raise ValueError('`doesnotcontain.py` | `flagname_mapping` must be provided as either a dictionary or a JSON file path')
        if isinstance(flagname_mapping, str):
            try:
                with open(flagname_mapping,'r') as file:
                    flagname_mapping = json.load(file)
            except ValueError:
                raise ValueError('`doesnotcontain.py` | If a string, `flagname_mapping` must be a path to a valid JSON file')

    if minimize_flagname and (flagname_mapping is None):
        outputfile = os.path.join(outputdir,f'{key}_doesnotcontain_mapping.json')
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
#        value_str = '-'.join([str(val) for val in values])
#        outputfile = os.path.join(outputdir,f'{key}_doesnotcontain_{value_str}_mapping.json')
        printv(f'INFO | Save `flagname_mapping` to {outputfile}', verbose=verbose, indent=indent)
        with open(outputfile, 'w', encoding='utf-8') as file:
            json.dump(flagname_mapping, file, ensure_ascii=False, indent=4)

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    # Filtering conditions

    if isinstance(values, str):
        values = [values]
    else:
        values = [str(val) for val in values]
    searchfor = '|'.join(values)

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
                temp[str(k)] = temp.pop(k)
            flagname_mapping = temp
            value_str = '-'.join([str(flagname_mapping[val]) for val in values])
        else:
            value_str = '-'.join(values)

        doesnotcontain[ismissing] = pd.NA
        df[f'flag_{key}_doesnotcontain_{value_str}'] = doesnotcontain

        return df

    else:

        # Drop rows:
        #   - where `key` contains values in `values`
        #   - with missing values in `key` if `dropna`

        return df[doesnotcontain].reset_index(drop=True)
