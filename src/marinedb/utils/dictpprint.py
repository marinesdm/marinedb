#!/usr/bin/python
# coding: utf-8

# Global variable

__all__ = ['apply']

def apply(dictionary, key_order=None, verbose=True, indent=''):

    if not key_order:
        key_order = dictionary.keys()

    if verbose:
        print(indent + '{')
        print('\n'.join(indent + ' ' + '{}: {}'.format(k, dictionary[k]) for k in key_order))
        print(indent + '}')

    return None
