#!/usr/bin/python
# coding: utf-8

# Internal import

from marinedb.utils import isgzip
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(filepath):

    if isgzip.apply(filepath):
        open_file = gzip.open
        decode_line = lambda line: line.decode('utf8')
    else:
        open_file = open
        decode_line = lambda line: line

    return open_file, decode_line

