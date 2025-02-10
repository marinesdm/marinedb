#!/usr/bin/env python3

# External imports
import os
import pandas as pd
import numpy as np
import argparse
import gzip
import time

def _store_data(data, outputpath):

    """
    Store extracted data.

    Parameters
    ----------
    data : list of strings

           Data extracted from the GBIF file, each value in the list being a line in the aforementioned file.

    Returns
    -------
    True
    """

    with open(outputpath,"a") as outputfile:
        outputfile.writelines(data)

    return True



if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Retrieve data from a file according to a filter file containing the indices of the data to be retrieved', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('gzip_file', type=str, help='path to the gzip file to be processed (default delimiter: tab)')
    parser.add_argument('filter_file', type=str, help='path to the filter file (must have a sorted "index" column) (default delimiter: tab)')
    parser.add_argument('--gzip_delimiter', type=str, help='gzip file delimiter', default='\t')
    parser.add_argument('--filter_delimiter', type=str, help='filter file delimiter', default='\t')
    parser.add_argument('--output_file', type=str, help='output file path', default='./')
    args = parser.parse_args()

    gzipfile = args.gzip_file
    filterfile = args.filter_file
    filtersep = args.filter_delimiter.encode('utf-8').decode('unicode_escape')
    gzipsep = args.gzip_delimiter.encode('utf-8').decode('unicode_escape')
    outputfile = args.output_file

    if len(os.path.basename(outputfile).split('.'))==1: #not a file or ''
        filename = os.path.basename(gzipfile).split('.')[0]
        outputfilename = os.path.join(outputfile, f'{filename}_marine.txt')
    else:
        outputfilename = args.output_file

    data = []
    count = 1
    error = 0

    start=time.time()

    # Open the filter file
    with open(filterfile, 'r') as filter:

        # Get the index of the "index" column in the filter file
        header = filter.readline().strip('\n').split(filtersep)
        index_idx = header.index('index')

        # Start reading the filter file
        index = int(filter.readline().strip('\n').split(filtersep)[index_idx])

        # Open the gzip file
        with gzip.open(gzipfile, "r") as gbif_data:

            header = gbif_data.readline().decode("utf8").split(gzipsep)
            Ncolumns = len(header)

            # Create output file header

            with open(outputfilename, "w") as outputfile:
                outputfile.write(gzipsep.join(header))

            # Read the gzip file until all data corresponding to the indices contained in the filter file have been retrieved

            print(f"----- Start retrieving data from the gzip file corresponding to the indexes in the filter file -----")
            print(f"gzip file: {gzipfile}")
            print(f"filter file: {filterfile}")

            for idx, line in enumerate(gbif_data):

                if idx==index: #both `idx` and  `index` start at 0

                    obs = line.decode("utf8").split(gzipsep)

                    if len(obs)!=Ncolumns:
                        error+=1
                        print()
                        print(f"    SplittingError: splitting line n°{idx} gives more fields ({len(obs)}) than the header ({Ncolumns}).")
                        print(f"                    line n°{idx} is skipped : {line}")
                        print()
                    else:
                        data.append(gzipsep.join(obs))

                    ## Save data every 50,000 lines
                    if (count%50000)==0:
                        _store_data(data, outputfilename)
                        data.clear()

                    if (count%100000)==0:
                        print(f"Processing | {count} lines done (GBIF: line {idx})")

                    ## Next filter index
                    index = filter.readline()
                    if index == "":
                        # No more data to retrieve
                        break
                    count += 1
                    index = int(index.strip('\n').split(filtersep)[index_idx])

    _store_data(data, outputfilename)
    end=time.time()

    print(f"Number of marine data: {count}")

    if index!="":
        print()
        print(f'WARNING: Not all filter indices have been processed. Something may have gone wrong.')

    print()
    print(f'----- End filtering: {args.gzip_file} -----')
    print(f'TIME : {np.round(end-start,0)}s')

    if error!=0:
        print()
        print(f'SplittingError: For {error} observations, split gave more fields than header fields and the observations have been ignored.')



