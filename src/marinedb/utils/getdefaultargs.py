#!/usr/bin/python
# coding: utf-8

# from: https://stackoverflow.com/questions/12627118/get-a-function-arguments-default-value

# External import

import inspect

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(func):

    signature = inspect.signature(func)

    default_args = {k : v.default for k,v in signature.parameters.items() if v.default is not inspect.Parameter.empty}

    return default_args
