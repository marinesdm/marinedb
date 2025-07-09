#!/usr/bin/python
# coding: utf-8

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(num):
    """
    Convert bytes to bytes, KB, MB, GB or TP
    source: https://stackoverflow.com/questions/2104080/how-do-i-check-file-size-in-python
    """
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0

    return num
