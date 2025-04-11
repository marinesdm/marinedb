#!/usr/bin/python
# coding: utf-8

# External imports

import gzip
import time
import argparse
import numpy as np


def store(data, outputpath):

    """
    Store the extracted data in the specified location.

    Parameters
    ----------
    data : list of strings

           Data to be stored

    outputpath : string

           Path to the output file

    Returns
    -------
    True
    """

    with open(outputpath, 'a') as outputfile:
        outputfile.writelines(data)

    return True


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Retrieve data from a file based on a filter file containing the indices of the data to be extracted', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('gzip_file', type=str, help='path to the gzip file to be processed (default delimiter: tab)')
    parser.add_argument('filter_file', type=str, help="path to the filter file, which must contain a sorted 'index' column (default delimiter: tab)")
    parser.add_argument('--gzip_delimiter', type=str, help='gzip file delimiter', default='\t')
    parser.add_argument('--filter_delimiter', type=str, help='filter file delimiter', default='\t')
    parser.add_argument('--output_file', type=str, help='output file path', default='./')
    args = parser.parse_args()

    gzipfile = args.gzip_file
    filterfile = args.filter_file
    filtersep = args.filter_delimiter.encode('utf-8').decode('unicode_escape')
    gzipsep = args.gzip_delimiter.encode('utf-8').decode('unicode_escape')
    outputfile = args.output_file

    data = []
    count = 1
    error = 0

    start=time.time()

    # Open the filter file

    with open(filterfile, 'r') as filter:

        # Retrieve the index of the 'index' column in the filter file

        header = filter.readline().strip('\n').split(filtersep)
        index_idx = header.index('index')

        # Start reading the filter file

        index = int(filter.readline().strip('\n').split(filtersep)[index_idx])

        # Open the gzip file

        with gzip.open(gzipfile, 'r') as gzipdata:

            header = gzipdata.readline().decode('utf8').split(gzipsep)
            Ncolumns = len(header)

            # Create the header for the outputfile

            with open(outputfile, 'w') as outputfile:
                outputfile.write(gzipsep.join(header))

            # Read the gzip file until all entries matching the indices from the filter file have been retrieved

            print(f'--- Retrieve data from the gzip file corresponding to the indices in the filter file ---')
            print(f'gzip file: {gzipfile}')
            print(f'filter file: {filterfile}')

            for idx, line in enumerate(gzipdata):

                if idx == index:

                    obs = line.decode('utf8').split(gzipsep)

                    if len(obs) != Ncolumns:
                        error+=1
                        print()
                        print(f'SplittingError: splitting line n°{idx} yields a different number of fields ({len(obs)}) than the header ({Ncolumns}).')
                        print(f'                line n°{idx} is skipped : {line}')
                        print()
                    else:
                        data.append(gzipsep.join(obs))

                    ## Save data every 50,000 lines

                    if (count%50000) == 0:
                        store(data, outputfile)
                        data.clear()

                    if (count%100000) == 0:
                        print(f'Processing | {count} lines done (gzip file: line {idx})')

                    ## Next filter index

                    index = filter.readline()
                    if index == '':
                        # no more data to retrieve
                        break
                    index = int(index.strip('\n').split(filtersep)[index_idx])
                    count += 1

    store(data, outputfile)
    end = time.time()

    print(f'Number of marine data: {count}')

    if index != '':
        print()
        print(f'WARNING | Some filter indices remain unprocessed. An issue may have occurred.')

    print()
    print(f'--- End filtering: {args.gzip_file} ---')
    print(f'TIME : {np.round(end-start,0)}s')

    if error != 0:
        print()
        print(f'SplittingError: {error} observations produced a different number of fields upon splitting compared to the header, and were consequently ignored.')



