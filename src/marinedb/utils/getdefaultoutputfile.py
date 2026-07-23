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

    filename = os.path.basename(inputfile)
    name, ext = os.path.splitext(filename)

    if '.' in name:
        raise ValueError(f"{filename}: multi-part extensions are not supported (e.g. '.tar.gz')")

    if modulename in name.split('_'):
        printv(
            f"WARNING | '{filename}' already contains '{modulename}' and will therefore not be modified",
            verbose=verbose,
            indent=indent
        )
        return inputfile

#    inputfile_split = inputfile.split('.')

    if (outputdir is None) or (len(outputdir) == 0):
        outputdir = os.path.dirname(inputfile)

    if ('processedby' in name) or (not add_processedby):
#        outputfile = start + f'_{modulename}' + end
        outputname = f"{name}_{modulename}{ext}"
    else:
#        outputfile = start + f'_processedby_{modulename}' + end
        outputname = f"{name}_processedby_{modulename}{ext}"

#    outputfile = resolvepath.apply(outputfile)
    outputfile = os.path.join(outputdir, outputname)

    return outputfile
