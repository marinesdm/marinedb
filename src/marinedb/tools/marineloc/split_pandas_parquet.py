#!/usr/bin/python
# coding: utf-8

# External import

import re
import os
import time
import argparse
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# Internal import

from marinedb.utils import readfile
from marinedb.utils import cleardirectory
from marinedb.utils.printverbose import printv
from marinedb.utils import preprocessquotationmark

# Global variables

__all__ = ['split_pandas', 'split_parquet', 'apply']

CHUNKSIZE = 100000

def split_pandas(inputfile, columns=None, sep='\t', chunksize=CHUNKSIZE, outputdir='./', verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    if 'split' not in outputdir.split('/')[-2:]:
        outputdir = os.path.join(outputdir, 'split')
    try:
        os.mkdir(outputdir)
    except FileExistsError:
        pass

    params = {
              'sep': sep,
              'chunksize': chunksize,
              'skip_blank_lines': False,
              'on_bad_lines': 'error', # avoid `usecols` to ensure `on_bad_lines` error triggers
              'engine': 'python'
             }

    basename = os.path.basename(inputfile).split('.')[0]
    with pd.read_csv(inputfile, **params) as reader:

        printv(f'* Split {inputfile} into {chunksize}-lines chunks (`split_pandas`)', verbose=verbose, indent=indent)
        printv('', verbose=verbose)

        for i,chunk in enumerate(reader):
            if columns is not None:
                chunk = chunk[columns]
            if 'index' not in chunk.columns:
                chunk = chunk.reset_index()
            chunkpath = os.path.join(outputdir, basename + '_split%05d' % i)
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

    parquet_file = pq.ParquetFile(inputfile)

    printv(f'* Split {inputfile} into {chunksize}-lines chunks (`split_parquet`)', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    for i,batch in enumerate(parquet_file.iter_batches(batch_size=chunksize, columns=columns)):

        batch_df = batch.to_pandas()
        if 'index' not in batch_df.columns:
           batch_df = batch_df.reset_index()
           batch_df['index'] += chunksize*i

        chunkpath = os.path.join(outputdir, basename + '_split%05d' % i)
        printv(f'>>> store {chunkpath}', verbose=verbose, indent=indent + '  ')
        batch_df.to_csv(chunkpath, sep='\t', index=False)

    return outputdir

def split_uncompressed_gzip(inputfile, sep='\t', columns=None, chunksize=CHUNKSIZE, outputdir='./', verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    basename = os.path.basename(inputfile).split('.')[0]

    if 'split' not in outputdir.split('/')[-2:]:
        outputdir = os.path.join(outputdir, 'split')
    try:
        os.mkdir(outputdir)
    except FileExistsError:
        pass

    split_idx = 0

    resume = False
    split_files = sorted([os.path.join(outputdir,file) for file in os.listdir(outputdir)])
    if len(split_files) != 0:
        last_file = pd.read_csv(split_files[-1], sep='\t')
        split_idx = re.findall(r'[0-9]+', split_files[-1].split('/')[-1])
        if len(split_idx) != 1:
            raise Exception(f'`split_pandas_parquet.py` | Unsupported file name: {split_files[-1]}. The file name must contain exactly one split number.')
        split_idx = int(split_idx[0]) + 1
        last_index = int(float(last_file.loc[last_file.index[-1], 'index']))
        del last_file
        resume = True

    open_file, decode_line = readfile.apply(inputfile)

    with open_file(inputfile,'r') as file:

        header = decode_line(file.readline()).strip('\n').split(sep)
        header_length = len(header)
        isindex = ('index' in header)

        if columns is not None:
            diffcol = set(columns) - set(header)
            if len(diffcol) != 0:
                raise Exception(f"`split_pandas_parquet.py` | {','.join(diffcol)} not found in {inputfile} header")
            columns_idx = [idx for idx, col in enumerate(header) if col in columns]
            isindex = ('index' in columns)

        printv(f'* Split {inputfile} into {chunksize}-lines chunks (`split_uncompressed_gzip`)', verbose=verbose, indent=indent)
        printv('', verbose=verbose)
        if resume:
            printv(f'* Restart processing from {outputdir}', verbose=verbose, indent=indent+'  ')

        data = []
        error = []

        for idx, line in enumerate(file):

            if resume:
                if (idx <= last_index):
                    if ((idx + 1) % chunksize) == 0:
                        printv(f'Processing | {idx + 1} lines', verbose=verbose, indent=indent+'    ')
                    continue
                else:
                    resume = False

            # Add observations

            obs = decode_line(line).strip('\n').split(sep)
            obs = [preprocessquotationmark.apply(value) for value in obs]

            if len(obs) != header_length:
                printv(f'WARNING | SplittingError: line n°{idx+2} is replaced with a blank line', verbose=verbose, indent=indent)
                error.append(idx+2)
                obs = [pd.NA] * header_length

            if columns is not None:
                obs = list(np.array(obs)[columns_idx])
            if not isindex:
                obs.insert(0, idx)
            data.append(obs)

            if (len(data) == chunksize):

                chunkpath = os.path.join(outputdir, basename + '_split%05d' % split_idx)
                printv(f'>>> store {chunkpath}', verbose=verbose, indent=indent + '  ')

                if columns is not None:
                    data_columns = columns
                else:
                    data_columns = header
                if not isindex:
                    data_columns = ['index'] + data_columns

                df = pd.DataFrame(data, columns=data_columns)
                df.to_csv(chunkpath, sep=sep, index=False)

                split_idx += 1
                data.clear()

    if len(data) != 0:

        chunkpath = os.path.join(outputdir, basename + '_split%05d' % split_idx)
        printv(f'>>> store {chunkpath}', verbose=verbose, indent=indent + '  ')

        if columns is not None:
            data_columns = columns
        else:
            data_columns = header
        if not isindex:
            data_columns = ['index'] + data_columns

        df = pd.DataFrame(data, columns=data_columns)
        df.to_csv(chunkpath, sep=sep, index=False)

    if len(error) != 0:
        printv(indent + f'ERROR:', verbose=verbose, indent=indent)
        printv(indent + f'SplittingError: {len(error)} observations produced a different number of fields upon splitting compared to {inputfile} header, and were consequently replaced with a blank line', verbose=verbose, indent=indent)
        printv(f'Refer to lines: {error}', verbose=verbose, indent=indent)

    return outputdir

def apply(inputfile, split_type='', columns=None, sep='\t', chunksize=CHUNKSIZE, outputdir='./', verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    if 'split' not in outputdir.split('/')[-2:]:
        outputdir = os.path.join(outputdir, 'split')
    try:
        os.mkdir(outputdir)
    except FileExistsError:
        pass

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
    elif split_type == 'uncompressed_gzip':
        outputdir = split_uncompressed_gzip(inputfile, **params)
    else:
        try:
            outputdir = split_pandas(inputfile, sep=sep, **params)
        except Exception as err1:
            printv('', verbose=verbose, indent=indent)
            printv('INFO | `split_pandas` failed, attempting `split_parquet` as fallback', verbose=verbose, indent=indent)
            printv('', verbose=verbose, indent=indent)
            cleardirectory.apply(outputdir)
            try:
                outputdir = split_parquet(inputfile, **params)
            except Exception as err2:
                printv('', verbose=verbose, indent=indent)
                printv('INFO | `split_parquet` failed, attempting `split_uncompressed_gzip` as fallback', verbose=verbose, indent=indent)
                printv('', verbose=verbose, indent=indent)
                cleardirectory.apply(outputdir)
                try:
                    outputdir = split_uncompressed_gzip(inputfile, sep=sep, **params)
                except Exception as err3:
                    print(f'Exception: `marineloc.py` | {inputfile} must be in a format supported by `pandas.read_csv`, in Parquet format, plain text or gzip-compressed.')
                    print(f'{type(err1).__name__}: {err1}')
                    print(f'{type(err2).__name__}: {err2}')
                    raise err3

    return outputdir

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Partition the parquet file', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputfile', type=str, help='path to the parquet file')
    parser.add_argument('--split-type', type=str, help="splitting method to use, either 'pandas' for files supported by pandas.read_csv, or 'parquet' for Parquet files, or 'uncompressed_gzip' for plain text or gzip-compressed files", default='')
    parser.add_argument('--columns', nargs='*', type=str, help='list containing the columns to retain', default=None)
    parser.add_argument('--delimiter', type=str, help='delimiter used in the input file', default='\t')
    parser.add_argument('--chunksize', type=int, help='number of lines per chunk', default=CHUNKSIZE)
    parser.add_argument('--outputdir', type=str, help='path to the directory where the output files will be saved', default='./')
    args = parser.parse_args()

    start = time.time()

    print()
    _ = apply(args.inputfile, split_type=args.split_type, columns=args.columns, sep=args.delimiter, chunksize=args.chunksize, outputdir=args.outputdir)

    end = time.time()
    print(f'TIME: {round(end - start,0)}s')
