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

    def copy(self):
        return type(self)(self)

BASISOFRECORD = BasisOfRecordMapping(BASISOFRECORD)

@export
def apply(df, key, additional_values=None, inplace=False, verbose=True, indent=''):
    """Standardize basis-of-record values.

    Maps values from a user-specified column to standardized Darwin Core 
    basis-of-record categories using the mappings provided by `marinedb`. 
    The source values may already describe a basis of record or may come 
    from another field, such as a sampling protocol, when an appropriate 
    mapping is provided. Matching is case-insensitive. Values absent from 
    the mapping are assigned to `OCCURRENCE`.

    The default mapping can be extended or modified through `additional_values`. 
    User-provided keys are matched case-insensitively and must map to one of the 
    standardized categories already supported by `marinedb`.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the input column containing values to map to standardized
            basis-of-record categories. The source column may contain existing
            basis-of-record values or other information from which a basis of
            record can be inferred, such as sampling protocols.

        additional_values (dict, optional):
            Additional mappings from input values to standardized
            basis-of-record categories. Matching is case-insensitive. 
            Mapped values must be one of the supported Darwin Core
            basis-of-record categories: `OCCURRENCE`, `HUMAN_OBSERVATION`, 
            `MACHINE_OBSERVATION`, `MATERIAL_SAMPLE`, `MATERIAL_CITATION`, 
            `FOSSIL_SPECIMEN`, `LIVING_SPECIMEN`, or `PRESERVED_SPECIMEN`. 
            Entries whose keys already occur in the default mapping replace 
            the corresponding mappings.

        inplace (bool, optional):
            Whether to replace the input column. When `False`, the
            standardized values are stored in a new column with a
            provenance suffix. When `True`, the input column is replaced
            when its name identifies it as a basis-of-record column.
            Otherwise, a new `basisOfRecord` column is created instead.

    Returns:
        (pandas.DataFrame):
            DataFrame containing the standardized basis-of-record
            column.

    Raises:
        TypeError:
            If `additional_values` is not a dictionary.
        ValueError:
            If an entry in `additional_values` maps to an unsupported
            standardized category.

    Notes:
        Values not present in either the default or user-provided mapping
        are classified as `OCCURRENCE`.

        When defining a custom mapping, users may also use `OCCURRENCE`
        for source values that do not provide enough information to assign
        a more specific Darwin Core basis-of-record category.

        Advanced users may modify the default mapping directly in
        `marinedb/tools/data/basisOfRecord.yaml`. Changes made to this
        package data file affect subsequent uses of the module but may be
        overwritten when `marinedb` is updated or reinstalled.
    """

    basisofrecord_mapping = BASISOFRECORD.copy()

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
            global_values = set(basisofrecord_mapping.values())
            option_values = set(additional_values.values())
            values_diff = option_values - global_values
            if len(values_diff) != 0:
                global_values = list(global_values)
                raise ValueError(f"`mapbasisOfRecord.py` | The mapped values must be {', '.join([f'{val}' for val in global_values[:-1]])} or {global_values[-1]}, not {','.join([f'{val}' for val in values_diff])}")

            global_keys = set(basisofrecord_mapping.keys())
            option_keys = set(additional_values.keys())
            keys_intersection = list(global_keys.intersection(option_keys))
            if len(keys_intersection) != 0:
                printv(f"WARNING | {', '.join(keys_intersection)} keys will be replaced in the corresponding default mapping dictionary", verbose=verbose, indent=indent)

            basisofrecord_mapping.update(additional_values)

        else:
            raise TypeError(f'`mapbasisOfRecord.py` | `additional_values` must be a dictionary, got {type(additional_values).__name__} instead')

    df[keyout] = df[keyin].str.upper()
    df[keyout] = df[keyout].map(basisofrecord_mapping)
    df[keyout] = df[keyout].astype('string')

    return df
