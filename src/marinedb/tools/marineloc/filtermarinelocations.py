#!/usr/bin/python
# coding: utf-8

# External imports

import time
import argparse
import numpy as np

# Internal import

from marinedb.utils import readfile
from marinedb.utils.allexport import export

# Global variables

__all__ = [] # populated using the @export decorator


def store(data, outputpath, indent=''):

    print(indent + f'>>> save {len(data)} marine data to {outputpath}')

    with open(outputpath, 'a') as outputfile:
        outputfile.writelines(data)

    return True

@export
def apply(inputfile, filterfile, inputfile_sep='\t', filter_sep='\t', outputpath='', indent=''):

    inputfile_sep = inputfile_sep.encode('utf-8').decode('unicode_escape')
    filter_sep = filter_sep.encode('utf-8').decode('unicode_escape')

    if len(outputpath) == 0:
        outputpath = inputfile.split('.')[:-1][0]
        outputpath = outputpath + '_marine'

    data = []
    count = 1
    error = 0

    start = time.time()

    # Open the filter file

    with open(filterfile, 'r') as filter:

        # Retrieve the index of the 'index' column in the filter file

        header = filter.readline().strip('\n').split(filter_sep)
        index_idx = header.index('index')

        # Start reading the filter file

        index = int(filter.readline().strip('\n').split(filter_sep)[index_idx])

        # Open the input file

        open_file, decode_line = readfile.apply(inputfile)

        with open_file(inputfile, 'r') as inputdata:

            header = decode_line(inputdata.readline()).split(inputfile_sep)
            Ncolumns = len(header)

            # Create the header for the outputfile

            with open(outputpath, 'w') as outputfile:
                outputfile.write(inputfile_sep.join(header))

            # Read the input file until all entries matching the indices from the filter file have been retrieved

            #print()
            print(indent + f'--- Start filtering marine locations ---')
            print(indent + f'input file: {inputfile}')
            print(indent + f'filter file: {filterfile}')
            #print()

            for idx, line in enumerate(inputdata):

                if idx == index:

                    obs = decode_line(line).split(inputfile_sep)

                    if len(obs) != Ncolumns:
                        error += 1
                        print()
                        print(indent + f'SplittingError: splitting line n°{idx + 2} yields a different number of fields ({len(obs)}) than the header ({Ncolumns}).')
                        print(indent + f'                line n°{idx + 2} is skipped : {line}')
                        print()
                    else:
                        data.append(inputfile_sep.join(obs))

                    ## Save data every 50,000 lines

                    if (count%50000) == 0:
                        store(data, outputpath, indent=indent)
                        data.clear()

                    if (count%100000) == 0:
                        print(indent + f'Processing | {count} lines done (input file: line {idx})')

                    ## Next filter index

                    index = filter.readline()
                    if index == '':
                        # no more data to retrieve
                        break
                    index = int(index.strip('\n').split(filter_sep)[index_idx])
                    count += 1

    store(data, outputpath, indent=indent)
    end = time.time()

    if index != '':
        #print()
        print(indent + f'WARNING | Some filter indices remain unprocessed. An issue may have occurred.')

    #print()
    print(indent + f'--- End filtering marine location ---')
    #print()
    print(indent + f'TIME : {np.round(end-start,0)}s')
    print(indent + f'COUNT: {count} marine data')

    if error != 0:
        print(indent + f'ERROR:')
        print(indent + f'SplittingError: {error} observations produced a different number of fields upon splitting compared to the header, and were consequently ignored.')

    return outputpath

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Retrieve data from a file based on a filter file containing the indices of the data to be extracted', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('input_file', type=str, help='path to the file to be processed (default delimiter: tab)')
    parser.add_argument('filter_file', type=str, help="path to the filter file, which must contain a sorted 'index' column (default delimiter: tab)")
    parser.add_argument('--inputfile_delimiter', type=str, help='input file delimiter', default='\t')
    parser.add_argument('--filter_delimiter', type=str, help='filter file delimiter', default='\t')
    parser.add_argument('--output_file', type=str, help='output file path', default='')
    args = parser.parse_args()

    inputfile = args.input_file
    filterfile = args.filter_file
    inputfile_sep = args.inputfile_delimiter.encode('utf-8').decode('unicode_escape')
    filter_sep = args.filter_delimiter.encode('utf-8').decode('unicode_escape')
    outputpath = args.output_file

    print(f'`filtermarinelocations.py` | Retrieve data from the input file corresponding to the indices in the filter file')

    _ = apply(inputfile, filterfile, inputfile_sep=inputfile_sep, filter_sep=filter_sep, outputpath=outputpath)
