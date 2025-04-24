#!/usr/bin/python
# coding: utf-8

# External import

import os
import pandas as pd
import argparse
import pyarrow.parquet as pq

# Internal import

from marinedb.utils.printverbose import printv

# Global variables

__all__ = ['split_pandas', 'split_parquet', 'apply']

CHUNKSIZE = 100000

def split_pandas(inputfile, columns=None, sep='\t', chunksize=CHUNKSIZE, outputdir='./', verbose=True, indent=''):

    if 'split' not in outputdir.split('/')[-2:]:
        outputdir = os.path.join(outputdir, 'split')
    try:
        os.mkdir(outputdir)
    except FileExistsError:
        pass

    params = {
              'sep': sep,
              'chunksize': chunksize,
              'on_bad_lines': 'warn'
             }
    if columns is not None:
        params['usecols'] = columns

    printv(f'* Split {inputfile} into {chunksize}-lines chunks', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    basename = os.path.basename(inputfile).split('.')[0]
    with pd.read_csv(inputfile, **params) as reader:
        for i,chunk in enumerate(reader):
            chunk = chunk.reset_index()
            chunkpath = os.path.join(outputdir, basename + '_split%04d' % i)
            printv(f'>>> store {chunkpath}', verbose=verbose, indent=indent + '  ')
            chunk.to_csv(chunkpath, sep=sep, index=False)

    return outputdir

def split_parquet(inputfile, columns=None, chunksize=CHUNKSIZE, outputdir='./', verbose=True, indent=''):

    basename = os.path.basename(inputfile).split('.')[0]

    if 'split' not in outputdir.split('/')[-2:]:
        outputdir = os.path.join(outputdir, 'split')
    try:
        os.mkdir(outputdir)
    except FileExistsError:
        pass

    printv(f'* Split {inputfile} into {chunksize}-lines chunks', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    parquet_file = pq.ParquetFile(inputfile)

    for i,batch in enumerate(parquet_file.iter_batches(batch_size=chunksize, columns=columns)):

        batch_df = batch.to_pandas()
        if 'index' not in batch_df.columns:
           batch_df = batch_df.reset_index()
           batch_df['index'] += chunksize*i

        chunkpath = os.path.join(outputdir, basename + '_split%04d' % i)
        printv(f'>>> store {chunkpath}', verbose=verbose, indent=indent + '  ')
        batch_df.to_csv(chunkpath, sep='\t', index=False)

    return outputdir

def apply(inputfile, split_type='', columns=None, sep='\t', chunksize=CHUNKSIZE, outputdir='./', verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    params = {
              'columns': columns,
              'chunksize': chunksize,
              'outputdir': outputdir,
              'verbose': verbose,
              'indent': indent
             }

    if split_type == 'pandas':
        params['sep'] = sep
        outputdir = split_pandas(inputfile, **params)
    elif split_type == 'parquet':
        outputdir = split_parquet(inputfile, **params)
    else:
        try:
            outputdir = split_pandas(inputfile, sep=sep, **params)
        except Exception as err1:
            outputdir = split_parquet(inputfile, **params)
        except Exception as err2:
            print(f'Exception: `marineloc.py` | {intputfile} must be in a format supported by `pandas.read_csv` or in Parquet format.')
            print(f'{type(err1).__name__}: {err1}')
            raise err2

    return outputdir

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Partition the parquet file', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputfile', type=str, help='path to the parquet file')
    parser.add_argument('--split_type', type=str, help="splitting method to use, either 'pandas' for files supported by pandas.read_csv, or 'parquet' for Parquet files", default='')
    parser.add_argument('--columns', nargs='*', type=str, help='list containing the columns to retain', default=None)
    parser.add_argument('--delimiter', type=str, help='delimiter used in the input file', default='\t')
    parser.add_argument('--chunksize', type=int, help='number of lines per chunk', default=CHUNKSIZE)
    parser.add_argument('--outputdir', type=str, help='path to the directory where the output files will be saved', default='./')
    args = parser.parse_args()

    print()
    _ = apply(args.inputfile, split_type=args.split_type, columns=args.columns, sep=args.delimiter, chunksize=args.chunksize, outputdir=args.outputdir)
