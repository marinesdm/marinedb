#!/usr/bin/python
# coding: utf-8

# Global variable

__all__ = ['apply']

def apply(dictionary, verbose=True, indent=''):

    if verbose:
        print(indent + '{')
        print('\n'.join(indent + ' ' + '{}: {}'.format(k, v) for k, v in dictionary.items()))
        print(indent + '}')

    return None
