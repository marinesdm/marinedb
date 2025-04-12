#!/usr/bin/python
# coding: utf-8

# from: https://stackoverflow.com/questions/3703276/how-to-tell-if-a-file-is-gzip-compressed

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(filepath):
    with open(filepath, 'rb') as test:
        return (test.read(2) == b'\x1f\x8b')
