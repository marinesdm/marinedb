#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils import regexstrip
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(target):

    # Pre-process strings to prevent quotation mark issues in pandas

    if isinstance(target,str):

        target = regexstrip.apply(target, pattern=r'["\s]+')
        target = regexstrip.apply(target, pattern=r"['\s]+")

    elif isinstance(target, list | tuple | pd.Series): # python >= 3.10

        target = pd.Series(target).str.replace('^["\s]+|["\s]+$','',regex=True)
        target = target.str.replace("^['\s]+|['\s]+$",'',regex=True).tolist()

    else:
        raise ValueError(f'`preprocessquotationmark.py` | Type not recognized: {type(target).__name__}')

    return target
