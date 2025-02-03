import glob
import os

import argparse
import numpy as np
import pandas as pd
from tqdm import tqdm

def write(df, tsv_filename, sep='\t', init=False):

    sep = sep.encode('utf-8').decode('unicode_escape')

    if init:
        df.to_csv(tsv_filename, mode='w', index=False, header=True, sep=sep)
    else:
        df.to_csv(tsv_filename, mode='a', index=False, header=False, sep=sep)

    return True


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Extract marine occurrence indexes', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('dir', type=str, help='path to the directory containing the files to be processed')
    parser.add_argument('--delimiter', type=str, help='input file delimiter', default='\t')
    parser.add_argument('--output_file', type=str, help='output file path', default='./marine_filter')
    args = parser.parse_args()

    outputfile = args.output_file
    sep = args.delimiter.encode('utf-8').decode('unicode_escape')

    # If a file has been processed several times, consider only one of the island.py output files

    files = sorted(glob.glob(args.dir + '*'))
    Nfiles = len(files)
    files2process = pd.DataFrame(files, columns=['filepath'])
    files2process['basename'] = ['_'.join(os.path.basename(file).split('_')[:-1]) for file in files2process['filepath'].values] # scheme: inputfilename_device
    files2process = files2process.drop_duplicates(subset=['basename'], keep='first', ignore_index=True)
    files = files2process['filepath'].tolist()
    del files2process

   # Keep only the indexes of locations classified as not on land

    print(f'Extracting marine occurrence indexes | {len(files)} unique files (out of {Nfiles}) to be processed (duplicates)')

    init_storage=True
    init_array=True

    for file in tqdm(files, total=len(files)):

        df_file = pd.read_csv(file, header=0, sep=sep, engine='python')
        df_file = df_file[~df_file.is_land]

        if init_array and len(df_file) != 0:

            gbif_ocean = df_file[["index","mask","latitude","longitude"]].values
            init_array = False

        elif len(df_file) != 0:
            gbif_ocean = np.append(gbif_ocean, df_file[["index","mask","latitude","longitude"]].values, axis=0)

        if (not init_array) and (len(gbif_ocean)>=1000000):
            gbif_ocean = pd.DataFrame(gbif_ocean, columns=["index","mask","latitude","longitude"])
            gbif_ocean["index"] = gbif_ocean["index"].astype(int)
            write(gbif_ocean, outputfile, init=init_storage, sep=sep)
            init_array = True
            init_storage = False

    if len(gbif_ocean)!=0:
        gbif_ocean = pd.DataFrame(gbif_ocean, columns=["index","mask","latitude","longitude"])
        gbif_ocean["index"] = gbif_ocean["index"].astype(int)
        write(gbif_ocean, outputfile, init=init_storage, sep=sep)
