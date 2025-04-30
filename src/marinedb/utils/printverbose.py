#!/usr/bin/python
# coding: utf-8

# External import

import numpy as np

# Global variable

__all__ = ['printv']

def printv(message, verbose, indent='', width=150):

    if verbose:

        width = width - len(indent)
        message_split = np.array(message.split(' '))
        while len(message_split) > 0:
            message_cumlength = np.cumsum([len(string) for string in message_split])
            condition = (message_cumlength <= width)
            if not condition.any():
                condition = np.array([True] + [False]*(len(message_cumlength) - 1))
            print(indent + ' '.join(message_split[condition]))
            message_split = message_split[~condition]

    return True
