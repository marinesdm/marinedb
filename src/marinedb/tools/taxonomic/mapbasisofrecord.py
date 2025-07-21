#!/usr/bin/python
# coding: utf-8

# External import

import yaml
import pandas as pd
from importlib.resources import files

# Internal import

from marinedb.tools import getcolumnname

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variable

__all__ = [] # populated using the @export decorator

BASISOFRECORD_PATH = files('marinedb.tools.data').joinpath('basisOfRecord.yaml')
with open(BASISOFRECORD_PATH,'r') as f:
    file = yaml.safe_load(f)
    BASISOFRECORD = file['basisOfRecord_mapping']

class BasisOfRecordMapping(dict):
    def __missing__(self, key):
        try:
            return super().__missing__(key)
        except AttributeError:
            return 'OCCURRENCE'

BASISOFRECORD = BasisOfRecordMapping(BASISOFRECORD)

@export
def apply(df, key, additional_values=None, inplace=False, verbose=True, indent=''):

#    df, keyin, keyout = getcolumnname.apply(df, key, 'mapbasisofrecord', inplace=inplace)
    df, keyin, _ = getcolumnname.apply(df, key, '', inplace=True)
    if ('basis' not in keyin.lower()) or ('record' not in keyin.lower()):
        _, _, keyout = getcolumnname.apply(df, 'basisOfRecord', 'mapbasisofrecord', inplace=False)
        if inplace:
            printv(f"WARNING | inplace={inplace}, but a new column called '{keyout}' will be added (key={key})", verbose=verbose, indent=indent)
    else:
        df, keyin, keyout = getcolumnname.apply(df, keyin, 'mapbasisofrecord', inplace=inplace)

    if additional_values is not None:

        if isinstance(additional_values, dict):

            additional_values = {k.upper():v.upper() for k,v in additional_values.items()}
            global_values = set(BASISOFRECORD.values())
            option_values = set(additional_values.values())
            values_diff = option_values - global_values
            if len(values_diff) != 0:
                global_values = list(global_values)
                raise ValueError(f"`mapbasisOfRecord.py` | The mapped values must be {', '.join([f'{val}' for val in global_values[:-1]])} or {global_values[-1]}, not {','.join([f'{val}' for val in values_diff])}")

            global_keys = set(BASISOFRECORD.keys())
            option_keys = set(additional_values.keys())
            keys_intersection = list(global_keys.intersection(option_keys))
            if len(keys_intersection) != 0:
                printv(f"WARNING | {', '.join(keys_intersection)} keys will be replaced in the `BASISOFRECORD` dictionary", verbose=verbose, indent=indent)

            BASISOFRECORD.update(additional_values)

        else:
            raise TypeError(f'`mapbasisOfRecord.py` | `additional_values` must be a dictionary, got {type(additional_values).__name__} instead')

    df[keyout] = df[keyin].str.upper()
    df[keyout] = df[keyout].map(BASISOFRECORD)
    df[keyout] = df[keyout].astype('string')

    return df
