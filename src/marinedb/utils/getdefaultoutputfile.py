#!/usr/bin/python
# coding: utf-8

# External import

import os

# Internal import

from marinedb.utils import resolvepath
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(inputfile, modulename, outputdir=None, add_processedby=True, verbose=True, indent=''):

    if modulename in inputfile:
        printv(f"WARNING | `inputfile` already contains '{modulename}' and will therefore not be modified", verbose=verbose, indent=indent)
        return inputfile

    inputfile_split = inputfile.split('.')

    if (outputdir is None) or (len(outputdir) == 0):
        start = inputfile_split[0]
    else:
        start = os.path.basename(inputfile_split[0])
        start = os.path.join(outputdir, start)

    if len(inputfile_split) > 2:
        raise ValueError(f"`getdefaultoutputfile.py` | `inputfile` must contain only one dot ('.') in its name ({inputfile})")
    elif len(inputfile_split) == 2:
        end = '.' + inputfile_split[1]
    else:
        end = ''

    if ('processedby' in start) or (not add_processedby):
        outputfile = start + f'_{modulename}' + end
    else:
        outputfile = start + f'_processedby_{modulename}' + end

    outputfile = resolvepath.apply(outputfile)

    return outputfile
