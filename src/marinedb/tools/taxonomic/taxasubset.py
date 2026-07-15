#!/usr/bin/python
# coding: utf-8

# External import

import os
import json
import shutil
import psutil
import subprocess
import pandas as pd
import dask.dataframe as dd
from collections import deque
from importlib.resources import files

# Internal import

from marinedb.utils import resolvepath
from marinedb.utils import convertbytes
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv
from marinedb.utils import getdefaultoutputfile

from marinedb.tools import getcolumnname
from marinedb.tools.taxonomic import taxasubset_lowerbound
from marinedb.tools.taxonomic import taxasubset_upperbound

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(inputfile, sep='\t', lowerbound=-1, upperbound=-1, flag=False, dropna=False, force_distributed=False, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, latkey=None, lonkey=None, resolution=8, cleanup=False, dtypesfile=None, outputdir='./', outputfile=None, export_process=False, export_type='both', verbose=True, verbose_level=2, indent=''):

    if (upperbound <= 0) and (lowerbound <= 0):

        # Do not filter taxa based on their number of occurrences in the dataset

        outputfile = inputfile

        return outputfile

    outputdir = resolvepath.apply(outputdir)
    if (outputfile is None) or (len(outputfile) == 0) or (inputfile == outputfile):
        outputfile = getdefaultoutputfile.apply(inputfile, 'taxasubset', outputdir=outputdir, verbose=verbose, indent=indent)

    if lowerbound > 0:

        # Filter taxa with less than `lowerbound` occurrences in the dataset

        printv('* lowerbound', verbose=verbose, indent=indent)

        params = {
                  'inputfile': inputfile,
                  'sep': sep,
                  'limit': lowerbound,
                  'flag': flag,
                  'dropna': dropna,
                  'force_distributed': force_distributed,
                  'speciesidkey': speciesidkey,
                  'specieskey': specieskey,
                  'genuskey': genuskey,
                  'familykey': familykey,
                  'orderkey': orderkey,
                  'classkey': classkey,
                  'phylumkey': phylumkey,
                  'kingdomkey': kingdomkey,
                  'dtypesfile': dtypesfile,
                  'outputdir': outputdir,
                  'outputfile': outputfile,
                  'verbose': verbose,
                  'indent': indent + '  '
                 }

        outputfile, speciesidkey = taxasubset_lowerbound.apply(**params)
        printv('', verbose=verbose, indent=indent)

    if upperbound > 0:

        # Limit the number of observations per taxon to `upperbound`

        printv('* upperbound', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        if latkey is None:
            raise ValueError(f'`taxasubset.py` | `latkey` must be provided')
        if lonkey is None:
            raise ValueError(f'`taxasubset.py` | `lonkey` must be provided')

        params = {
                   'sep': sep,
                   'limit': upperbound,
                   'latkey': latkey,
                   'lonkey': lonkey,
                   'speciesidkey':speciesidkey,
                   'specieskey':specieskey,
                   'genuskey':genuskey,
                   'familykey':familykey,
                   'orderkey':orderkey,
                   'classkey':classkey,
                   'phylumkey':phylumkey,
                   'kingdomkey':kingdomkey,
                   'resolution': resolution,
                   'cleanup': cleanup,
                   'dtypesfile': dtypesfile,
                   'outputdir': outputdir,
                   'outputfile': outputfile,
                   'export_process': export_process,
                   'export_type': export_type,
                   'verbose': verbose,
                   'verbose_level': verbose_level,
                   'indent': indent + '  '
                 }

        outputfile = taxasubset_upperbound.apply(inputfile, **params)
        printv('', verbose=verbose, indent=indent)

    return outputfile

