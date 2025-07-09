#!/usr/bin/python
# coding: utf-8

# External import

import os
import time
import argparse
import numpy as np
import pandas as pd
from tqdm import tqdm

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools.marineloc import island

# Global variable

__all__ = [] # populated using the @export decorator

def write(df, txt_filename, sep='\t', init=False):

    sep = sep.encode('utf-8').decode('unicode_escape')

    if init:
        df.to_csv(txt_filename, mode='w', index=False, header=True, sep=sep)
    else:
        df.to_csv(txt_filename, mode='a', index=False, header=False, sep=sep)

    return True

def extract_marine_locations(inputdir, latkey, lonkey, idxkey, controlkey=None, sep='\t', fileslist=None, maskfile=None, outputdir='', store_time=True, parallel=False, cpu=None, verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    params = {
              'fileslist': fileslist,
              'latkey': latkey,
              'lonkey': lonkey,
              'idxkey': idxkey,
              'controlkey': controlkey,
              'sep': sep,
              'maskfile': maskfile,
              'outputdir': outputdir,
              'parallel': parallel,
              'cpu': cpu,
              'store_time': store_time,
              'verbose': verbose,
              'indent': indent
             }

    printv(f'* Extract marine coordinates', verbose=verbose, indent=indent)

    params['indent'] += '  '

    outputdir = island.apply(inputdir, **params)

    return outputdir

def extract_marine_indices(inputdir, controlkey=None, outputfile='marine_filter', sep='\t', verbose=True, indent=''):

    printv(f'* Extract indices corresponding to marine coordinates', verbose=verbose, indent=indent)

    start = time.time()

    sep = sep.encode('utf-8').decode('unicode_escape')

    if 'filter' not in outputfile:
        temp = outputfile.split('.')
        outputfile = temp[0] + '_filter'
        if len(temp) == 2:
            outputfile += f'.{temp[1]}'

    if len(os.path.dirname(outputfile)) == 0:
        outputfile = os.path.join(inputdir,outputfile)

    # If a file has been processed multiple times,
    # consider only one corresponding `island.py` output file

    files = sorted([os.path.join(inputdir,file) for file in os.listdir(inputdir) if os.path.isfile(os.path.join(inputdir,file)) and ('time' not in file) and ('filter' not in file)])
    Nfiles = len(files)

    printv(f'* Deduplicate entries across the {Nfiles} files in {inputdir}', verbose=verbose, indent=indent + '  ')

    files2process = pd.DataFrame(files, columns=['filepath'])
    files2process['basename'] = ['_'.join(os.path.basename(file).split('_')[:-1]) for file in files2process['filepath']] # format: 'inputfilename_device'
    files2process = files2process.drop_duplicates(subset=['basename'], keep='first', ignore_index=True)
    files = files2process['filepath'].tolist()
    del files2process

    # Keep only the indices corresponding to locations not classified as land

    printv(f'* Extract indices from {len(files)} files', verbose=verbose, indent=indent + '  ')

    init_array = True
    init_storage = True
    columns = ['index','mask','latitude','longitude']
    if (controlkey is not None) and (len(controlkey) != 0):
        columns.append(controlkey)

    if verbose:
        process = tqdm(files, total=len(files), desc=indent + '  Progress')
    else:
        process = files
    for file in process:

        df_file = pd.read_csv(file, sep=sep, engine='python')
        df_file = df_file[~df_file['island']]

        if init_array and len(df_file) != 0:

            marinedata = df_file[columns].values
            init_array = False

        elif len(df_file) != 0:
            marinedata = np.append(marinedata, df_file[columns].values, axis=0)

        if (not init_array) and (len(marinedata) >= 1000000):

            marinedata = pd.DataFrame(marinedata, columns=columns)
            marinedata['index'] = marinedata['index'].astype(int)
            write(marinedata, outputfile, init=init_storage, sep=sep)
            init_array = True
            init_storage = False

    if len(marinedata) != 0:
        marinedata = pd.DataFrame(marinedata, columns=columns)
        marinedata['index'] = marinedata['index'].astype(int)
        write(marinedata, outputfile, init=init_storage, sep=sep)

    end = time.time()

    printv(f'TIME : {round(end - start,0)}s', verbose=verbose, indent=indent + '  ')

    return outputfile

@export
def apply(inputdir, latkey, lonkey, idxkey, controlkey=None, sep='\t', fileslist=None, maskfile=None, outputdir='', store_time=True, parallel=False, cpu=None, outputfile='marine_filter', verbose=True, indent=''):

    sep = sep.encode('utf-8').decode('unicode_escape')

    params_marineloc = {
                        'inputdir': inputdir,
                        'fileslist': fileslist,
                        'latkey': latkey,
                        'lonkey': lonkey,
                        'idxkey': idxkey,
                        'controlkey': controlkey,
                        'sep': sep,
                        'maskfile': maskfile,
                        'outputdir': outputdir,
                        'parallel': parallel,
                        'cpu': cpu,
                        'store_time': store_time,
                        'verbose': verbose,
                        'indent': indent
                       }

    outputdir = extract_marine_locations(**params_marineloc)

    printv('', verbose=verbose)

    params_marineidx = {
                        'inputdir': outputdir,
                        'controlkey': controlkey,
                        'outputfile': outputfile,
                        'sep': sep,
                        'verbose': verbose,
                        'indent': indent
                       }

    outputfile = extract_marine_indices(**params_marineidx)

    return outputfile

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Extract indices corresponding to marine occurrences', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputdir-path', type=str, help='directory path containing files to be processed')
    parser.add_argument('--fileslist-path', type=str, help='path to the file that lists the files to be processed', default=None)
    parser.add_argument('--latitude-column', type=str, help='latitude column name', required=True)
    parser.add_argument('--longitude-column', type=str, help='longitude column name', required=True)
    parser.add_argument('--index-column', type=str, help='index column name', required=True)
    parser.add_argument('--control-column', type=str, help='control column name', default=None)
    parser.add_argument('--delimiter', type=str, help='delimiter used in the input files', default='\t')
    # Warning: delimiter must be enclosed in quotation marks
    parser.add_argument('--maskfile-path', type=str, help='path to the .npz file containing the land/sea/coast mask', default=None)
    parser.add_argument('--outputdir-path', type=str, help='path to the directory where output files from `island.py` will be saved', default='./')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='whether to enable parallel processing across multiple CPUs', default=False)
    parser.add_argument('--cpu', type=int, help='number of CPUs to be used', default=None)
    parser.add_argument('--store-time', action=argparse.BooleanOptionalAction, help='whether to store the processing times', default=True)
    parser.add_argument('--outputfile-path', type=str, help='path to the file where the filter will be saved', default='./marine_filter')
    args = parser.parse_args()

    print()
    print(f'`createmarinefilter.py` | Extract the indices of marine occurrences from {args.inputdir_path} files')
    print()

    params = {
              'inputdir': args.inputdir_path,
              'fileslist': args.fileslist_path,
              'latkey': args.latitude_column,
              'lonkey': args.longitude_column,
              'idxkey': args.index_column,
              'controlkey': args.control_column,
              'sep': args.delimiter.encode('utf-8').decode('unicode_escape'),
              'maskfile': args.maskfile_path,
              'outputdir': args.outputdir_path,
              'parallel': args.parallel,
              'cpu': args.cpu,
              'store_time': args.store_time,
              'outputfile': args.outputfile_path
             }

    start = time.time()

    _ = apply(**params)

    end = time.time()

    print()
    print(f'TIME : {round(end - start,0)}s')
