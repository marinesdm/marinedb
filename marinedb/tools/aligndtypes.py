#!/usr/bin/python
# coding: utf-8

# External import

import re

# Internal import

from marinedb.utils.allexport import export

# Global variables

__all__ = [] # populated using the @export decorator

def boolean(value):

    if isinstance(value,str):
        if value in ['True','False']:
            value = (value == 'True')
        else:
            raise ValueError(f"`aligndtypes.py` | `value` must be True or False, but value='{value}'")
    else:
        value = bool(value)

    return value

TYPE_CONVERSION = {
                    'int': int,
                    'float': float,
                    'bool': boolean,
                    'string': str
                  }

@export
def apply(df, key, values):

    dtype = str(df[key].dtypes)
    if dtype == 'object':
        df[key] = df[key].convert_dtypes()
        dtype = str(df[key].dtypes)

    try:
        astype = TYPE_CONVERSION[re.match(r'int|float|bool',dtype.lower()).group()]
        column_dtype = dtype
    except AttributeError:
        astype = TYPE_CONVERSION['string']
        column_dtype = 'string'

    df[key] = df[key].astype(column_dtype)

    if isinstance(values, tuple | list):
        values = [astype(v) for v in values]
    else:
        values = astype(values)

#    print('value:',values) #DEBUG
#    print('df dtype:',df[key].dtypes) #DEBUG
#    print('dtype:',dtype) #DEBUG

    return df, values
