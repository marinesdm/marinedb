#!/usr/bin/python
# coding: utf-8

# External imports

import time
import argparse
import numpy as np

# Internal import

from marinedb.utils import readfile
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variables

__all__ = [] # populated using the @export decorator


def store(data, outputfile, verbose=True, indent=''):

    printv(f'>>> save {len(data)} marine data to {outputfile}', verbose=verbose, indent=indent)

    with open(outputfile, 'a') as file:
        file.writelines(data)

    return True

@export
def apply(inputfile, filterfile, inputfile_sep='\t', filter_sep='\t', outputfile='', verbose=True, indent=''):

    inputfile_sep = inputfile_sep.encode('utf-8').decode('unicode_escape')
    filter_sep = filter_sep.encode('utf-8').decode('unicode_escape')

    if len(outputfile) == 0:
        temp = inputfile.split('.')
        assert len(temp) <= 2
        outputfile = temp[0] + '_marine'
        if len(temp) == 2:
            outputfile += f'.{temp[1]}'

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

            with open(outputfile, 'w') as file:
                file.write(inputfile_sep.join(header))

            # Read the input file until all entries matching the indices from the filter file have been retrieved

            printv(f'--- Start filtering marine locations ---', verbose=verbose, indent=indent)
            printv(f'input file: {inputfile}', verbose=verbose, indent=indent)
            printv(f'filter file: {filterfile}', verbose=verbose, indent=indent)

            for idx, line in enumerate(inputdata):

                if idx == index:

                    obs = decode_line(line).split(inputfile_sep)

                    if len(obs) != Ncolumns:
                        error += 1
                        printv('', verbose=verbose)
                        printv(f'SplittingError: splitting line n°{idx + 2} yields a different number of fields ({len(obs)}) than the header ({Ncolumns}).', verbose=verbose, indent=indent)
                        printv(f'line n°{idx + 2} is skipped : {line}', verbose=verbose, indent=indent)
                        printv('', verbose=verbose)
                    else:
                        data.append(inputfile_sep.join(obs))

                    ## Save data every 50,000 lines

                    if (count%100000) == 0:
                        store(data, outputfile, verbose=verbose, indent=indent)
                        data.clear()

                    if (count%1000000) == 0:
                        printv(f'Processing | {count} lines done (input file: line {idx})', verbose=verbose, indent=indent)

                    ## Next filter index

                    index = filter.readline()
                    if index == '':
                        # no more data to retrieve
                        break
                    index = int(index.strip('\n').split(filter_sep)[index_idx])
                    count += 1

    store(data, outputfile, verbose=verbose, indent=indent)
    end = time.time()

    if index != '':
        printv(f'WARNING | Some filter indices remain unprocessed. An issue may have occurred.', verbose=verbose, indent=indent)

    printv(f'--- End filtering marine location ---', verbose=verbose, indent=indent)

    printv(f'TIME : {np.round(end-start,0)}s', verbose=verbose, indent=indent)
    printv(f'COUNT: {count} marine data', verbose=verbose, indent=indent)
    if error != 0:
        printv(f'ERROR:', verbose=verbose, indent=indent)
        printv(f'SplittingError: {error} observations produced a different number of fields upon splitting compared to the header, and were consequently ignored.', verbose=verbose, indent=indent)

    return outputfile

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
    outputfile = args.output_file

    print(f'`filtermarinelocations.py` | Retrieve data from the input file corresponding to the indices in the filter file')

    _ = apply(inputfile, filterfile, inputfile_sep=inputfile_sep, filter_sep=filter_sep, outputfile=outputfile)
