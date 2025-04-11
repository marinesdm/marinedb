#!/usr/bin/python
# coding: utf-8

# External import

import re

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(string, pattern=None):

    if pattern is None:
        # by default, remove leading and trailing whitespace
        pattern = r'^\s+|\s+$'
    elif pattern[0] != '^':
        pattern = fr'^{pattern}|{pattern}$'

    return re.sub(fr'{pattern}','',string)

