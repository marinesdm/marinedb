#!/usr/bin/python
# coding: utf-8

# External import

import os

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(input_path):
    return os.path.realpath(os.path.expanduser(input_path))
