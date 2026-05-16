#!/usr/bin/python
# coding: utf-8

# External import

import os
import argparse
import subprocess
from importlib.resources import files

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils import resolvepath
from marinedb.utils import getdefaultoutputfile

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(inputfile, sep='\t', column_names=None, column_indices=None, outputdir='./', outputfile=None):

    if (column_names is None) and (column_indices is None):
        raise Exception(f'`extractcolumns.py` | Either `column_names` or `column_indices` must be provided')

    if (outputfile is None) or (len(outputfile) == 0):
        outputfile = getdefaultoutputfile.apply(inputfile, 'extractcolumns', outputdir=outputdir)
    if len(os.path.dirname(outputfile)) == 0:
        outputfile = resolvepath.apply(os.path.join(outputdir, outputfile))

    if (column_names is not None) and (column_indices is not None):
        print(f'INFO | Since `column_indices` is provided, `column_names` will be ignored')
        column_names = None

    with open(inputfile,'r') as data:
        header = data.readline().strip('\n').split(sep)

    if (column_indices is not None):

        if isinstance(column_indices, int | float):
            column_indices = [int(column_indices)]

        column_names = [header[idx] for idx in column_indices]


    if column_names is not None:

        if isinstance(column_names, str):
            column_names = [column_names]

        column_indices = [str(header.index(col) + 1) for col in column_names]

    column_indices = ','.join(column_indices)
    column_names = ','.join([f"'{col}'" for col in column_names])

    print(f"* Generate {outputfile} containing only the {column_names} column(s) from {inputfile}")

    extract_columns_algorithm = files('marinedb.utils').joinpath('extractcolumns.sh')
    cmd = ['bash', extract_columns_algorithm, '-f', inputfile, '-c', column_indices, '-o', outputfile,'-d', sep]
    p = subprocess.run(cmd)

    return outputfile

if __name__ == '__main__':

   parser = argparse.ArgumentParser(description='Create a new file containing a subset of columns from the input file')
   parser.add_argument('inputfile', type=str, help='path to the input file from which to extract columns')
   parser.add_argument('--delimiter', type=str, help="delimiter used in the input file (default: '\t')", default='\t')
   parser.add_argument('--column-names', nargs='*', type=str, help='names of the columns to extract', default=None)
   parser.add_argument('--column-indices', nargs='*', type=str, help='indices (starting at 1) of the columns to extract', default=None)
   parser.add_argument('--outputdir', type=str, help='directory where the output file will be saved', default='./')
   parser.add_argument('--outputfile', type=str, help='name or full path of the output file', default=None)
   args = parser.parse_args()

   apply(args.inputfile, sep=args.delimiter, column_names=args.column_names, column_indices=args.column_indices, outputdir=args.outputdir, outputfile=args.outputfile)
