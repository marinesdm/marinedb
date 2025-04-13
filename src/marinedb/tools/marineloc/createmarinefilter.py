#!/usr/bin/python
# coding: utf-8

# External import

import os
import glob
import argparse
import numpy as np
import pandas as pd
from tqdm import tqdm

def write(df, txt_filename, sep='\t', init=False):

    sep = sep.encode('utf-8').decode('unicode_escape')

    if init:
        df.to_csv(txt_filename, mode='w', index=False, header=True, sep=sep)
    else:
        df.to_csv(txt_filename, mode='a', index=False, header=False, sep=sep)

    return True

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Extract indices corresponding to marine occurrences', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputdir_path', type=str, help='path to the directory where the files to be processed are stored')
    parser.add_argument('--delimiter', type=str, help='delimiter used in the input files', default='\t')
    parser.add_argument('--outputfile_path', type=str, help='file path where the output will be saved', default='./marine_filter')
    args = parser.parse_args()

    print(f'`createmarinefilter.py` | Extract the indices of marine occurrences from {args.inputdir_path} files')

    outputfile = args.outputfile_path
    sep = args.delimiter.encode('utf-8').decode('unicode_escape')

    # If a file has been processed multiple times,
    # consider only one corresponding `island.py` output file

    files = sorted(glob.glob(args.inputdir_path + '*'))
    Nfiles = len(files)

    print(f'* Deduplicate entries across the {Nfiles} files in the folder')

    files2process = pd.DataFrame(files, columns=['filepath'])
    files2process['basename'] = ['_'.join(os.path.basename(file).split('_')[:-1]) for file in files2process['filepath']] # format: 'inputfilename_device'
    files2process = files2process.drop_duplicates(subset=['basename'], keep='first', ignore_index=True)
    files = files2process['filepath'].tolist()
    del files2process

    # Keep only the indices corresponding to locations not classified as land

    print(f'* Process {len(files)} files')

    init_array = True
    init_storage = True

    for file in tqdm(files, total=len(files)):

        df_file = pd.read_csv(file, header=0, sep=sep, engine='python')
        df_file = df_file[~df_file['island']]

        if init_array and len(df_file) != 0:

            marinedata = df_file[['index','mask','latitude','longitude']].values
            init_array = False

        elif len(df_file) != 0:
            marinedata = np.append(marinedata, df_file[['index','mask','latitude','longitude']].values, axis=0)

        if (not init_array) and (len(marinedata) >= 1000000):

            marinedata = pd.DataFrame(marinedata, columns=['index','mask','latitude','longitude'])
            marinedata['index'] = marinedata['index'].astype(int)
            write(marinedata, outputfile, init=init_storage, sep=sep)
            init_array = True
            init_storage = False

    if len(marinedata) != 0:
        marinedata = pd.DataFrame(marinedata, columns=['index','mask','latitude','longitude'])
        marinedata['index'] = marinedata['index'].astype(int)
        write(marinedata, outputfile, init=init_storage, sep=sep)
