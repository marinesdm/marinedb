#!/usr/bin/python
# coding: utf-8

# from: https://stackoverflow.com/questions/44834/what-does-all-mean-in-python

# External import

import sys

# Global variable

__all__ = ['export']

def export(fn):
    mod = sys.modules[fn.__module__]
    if hasattr(mod, '__all__'):
        mod.__all__.append(fn.__name__)
    else:
        mod.__all__ = [fn.__name__]
    return fn
