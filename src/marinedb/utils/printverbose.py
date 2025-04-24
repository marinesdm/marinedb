#!/usr/bin/python
# coding: utf-8

# Global variable

__all__ = ['printv']

def printv(message, verbose, indent=''):
    if verbose:
        print(indent + message)
    return True
