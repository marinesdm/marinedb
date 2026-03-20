#!/usr/bin/python
# coding: utf-8

# External imports

import os
import time
import bisect
import argparse
import pandas as pd
import pyarrow.parquet as pq

# Internal import

from marinedb.utils import readfile
from marinedb.utils import standardizenan
from marinedb.utils import writedataframe
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv
from marinedb.utils import preprocessquotationmark

# Global variables

__all__ = [] # populated using the @export decorator


def store(data, outputfile, verbose=True, indent=''):

    printv(f'>>> save {len(data)} marine data to {outputfile}', verbose=verbose, indent=indent)

    with open(outputfile, 'a') as file:
        file.writelines(data)

    return True

def readfirstlast(inputfile):

    with open(inputfile,'rb') as f:

        first_line = f.readline().decode()

        try:
            f.seek(-2,2)
            while f.read(1) != b'\n':
                f.seek(-2,1)
        except OSError:
           f.seek(0)

        last_line = f.readline().decode()

    return first_line, last_line

def nextchunk(filter_TextIOWrapper, filter_sep, index_idx, field_idx=None, chunksize=100000):

    lines = [next(filter_TextIOWrapper, '_END_').strip('\n').split(filter_sep) for _ in range(chunksize)]
    lines = [line for line in lines if (line[0] != '_END_')]

    index = [int(line[index_idx]) for line in lines]
    if field_idx is None:
        field = None
    else:
        field = [line[field_idx] for line in lines]

    return index, field

def filter_parquet(inputfile, filterfile, controlkey=None, filter_sep='\t', outputfile='', verbose=True, indent=''):

    printv(f'* Filter marine location (`filter_parquet`)', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    filter_sep = filter_sep.encode('utf-8').decode('unicode_escape')
    doublecheck = (controlkey is not None) and (len(controlkey) != 0)
    resume = False

    if os.path.isfile(outputfile):
        if doublecheck:
            resume = True
            first_line, last_line = readfirstlast(outputfile)
            header_outputfile = first_line.strip('\n').split('\t')
            controlkey_idx = header_outputfile.index(controlkey)
            start_value = last_line.strip('\n').split('\t')[controlkey_idx]
            try:
                start_value = int(float(start_value))
            except (TypeError, ValueError):
                pass
        else:
            printv(f'WARNING | {outputfile} exists and will be overwritten (to prevent this, specify `controlkey`)', verbose=verbose, indent=indent)

    # Open the filter file

    count = 0
    init = True
    init_storage = True
    isendfile = False

    with open(filterfile, 'r') as filter:

        ## Retrieve the index of the 'index' column in the filter file

        header_filterfile = next(filter).strip('\n').split(filter_sep)
        index_idx = header_filterfile.index('index')

        ## Retrieve the index of the `controlkey` column from the filter file, if specified

        if doublecheck:
            filter_controlkey_idx = header_filterfile.index(controlkey)
        else:
            filter_controlkey_idx = None

        # Restart processing if interruption

        if resume:
            printv(f'* Restart processing from {outputfile}', verbose=verbose, indent=indent+'  ')
            nlines = 0
            while resume:
                controlkey_value = next(filter, '_END_')
                if controlkey_value == '_END_':
                    return count
                else:
                    controlkey_value = controlkey_value.strip('\n').split(filter_sep)[filter_controlkey_idx]
                    try:
                        controlkey_value = int(float(controlkey_value))
                    except (TypeError, ValueError):
                        pass
                    if controlkey_value == start_value:
                        resume = False
                    else:
                        nlines += 1
                if (nlines % 100000) == 0:
                    printv(f'Processing | {nlines} lines', verbose=verbose, indent=indent+'    ')
            init_storage = False

        # Read the filter file

        index, validation = nextchunk(filter, filter_sep=filter_sep, index_idx=index_idx, field_idx=filter_controlkey_idx)
        validation = pd.Series(validation)

        # Open the input file

        parquet_file = pq.ParquetFile(inputfile)

        # Read the input file until all entries matching the indices from the filter file have been retrieved

        for i,batch in enumerate(parquet_file.iter_batches(batch_size=10000)):

            batch_df = batch.to_pandas().convert_dtypes()
            isindex = True
            if 'index' not in batch_df.columns:
                isindex = False
                batch_df = batch_df.reset_index()
                batch_df['index'] += 10000*i
                batch_df['index'] = batch_df['index'].astype('int')
            max_batch_index = batch_df.loc[batch_df.index[-1],'index']

            if max_batch_index >= index[0]:

                ## Extract rows corresponding to filter indices

                cutoff_index = bisect.bisect_right(index,max_batch_index)
                subset_index = index[:cutoff_index]
                if doublecheck:
                    assert subset_index == sorted(subset_index)
                batch_df = batch_df.set_index('index').loc[subset_index,:].reset_index()
                batch_df = standardizenan.apply(batch_df, additional_policy='contains_letters_or_digits')

                if doublecheck:

                    assert len(batch_df) == len(subset_index)

                    subset_validation = standardizenan.apply(validation[:cutoff_index], additional_policy='contains_letters_or_digits')
                    ismissing = pd.isnull(batch_df[controlkey]) & pd.isnull(subset_validation)
                    ismismatch = (~ismissing) & (batch_df[controlkey] != subset_validation)
                    if any(ismismatch):
                        mismatch_original = batch_df.loc[ismismatch, controlkey]
                        mismatch_filter = validation[ismismatch]
                        mismatch_index = list(ismismatch[ismismatch].index)
                        raise Exception(f"`filtermarineslocations.py` | Value mismatch at line(s) {','.join(mismatch_index)} between original (e.g {mismatch_original[mismatch_index[0]]}) and filter file (e.g. {mismatch_index[mismatch_index[0]]}). This may indicate a processing error.")

                if not isindex:
                    batch_df.drop(columns=['index'],inplace=True)
                if init:
                    data = batch_df.copy(deep=True)
                    if init_storage:
                        header_outputfile = list(data.columns)
                    init = False
                else:
                    data = pd.concat([data, batch_df[header_outputfile].copy(deep=True)], axis=0)

                count += len(batch_df)

                ## Save data every 1,000,000 lines

                if len(data) > 100000:
                    printv(f'>>> save {len(data)} marine data to {outputfile}', verbose=verbose, indent=indent)
                    writedataframe.to_txt(data, outputfile, init=init_storage, verbose=False)
                    init_storage = False
                    init = True
                    del data

                if (max_batch_index%1000000) == 0:
                    printv(f'Processing | {count} lines done (input file: line {max_batch_index})', verbose=verbose, indent=indent)

                ## Next filter indices

                index = index[cutoff_index:]
                if doublecheck:
                    validation = validation[cutoff_index:]
                if (not isendfile) and (len(index) < 10000):
                    chunksize = (100000 - len(index))
                    index_add, validation_add = nextchunk(filter, filter_sep=filter_sep, index_idx=index_idx, field_idx=filter_controlkey_idx, chunksize=chunksize)
                    isendfile = (len(index_add) != chunksize)
                    index = index + index_add
                    if doublecheck:
                        validation = pd.Series(list(validation) + validation_add)
                    if doublecheck:
                        assert len(validation) == len(index)
                if isendfile and (len(index) == 0):
                    break

    if 'data' in locals():
        printv(f'>>> save {len(data)} marine data to {outputfile}', verbose=verbose, indent=indent)
        writedataframe.to_txt(data, outputfile, init=init_storage, verbose=False)

    return count

def filter_uncompressed_gzip(inputfile, filterfile, controlkey=None, inputfile_sep='\t', filter_sep='\t', outputfile='', verbose=True, indent='', keep_mask=False):

    printv(f'* Filter marine location (`filter_uncompressed_gzip`)', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    inputfile_sep = inputfile_sep.encode('utf-8').decode('unicode_escape')
    filter_sep = filter_sep.encode('utf-8').decode('unicode_escape')
    doublecheck = (controlkey is not None) and (len(controlkey) != 0)

    data = []
    count = 0
    error = 0

    # Open the filter file

    with open(filterfile, 'r') as filter:

        ## Retrieve the index of the 'index' column in the filter file

        header = filter.readline().strip('\n').split(filter_sep)
        index_idx = header.index('index')

        if doublecheck:

            ## Retrieve the index of the `controlkey` column in the filter file

            filter_controlkey_idx = header.index(controlkey)

        if keep_mask:
            mask_idx = header.index('mask')

        # Read the filter file

        lines = filter.readline().strip('\n').split(filter_sep)
        index = int(lines[index_idx])

        # Open the input file

        open_file, decode_line = readfile.apply(inputfile)

        with open_file(inputfile, 'r') as inputdata:

            header = decode_line(inputdata.readline()).split(inputfile_sep)
            Ncolumns = len(header)

            if doublecheck:

                ## Retrieve the index of the `controlkey` column in the data file

                data_controlkey_idx = header.index(controlkey)

            ## Create the header for the output file

            if keep_mask:
                header.insert(0,'marinedb_mask')

            with open(outputfile, 'w') as file:
                file.write(inputfile_sep.join(header))

            # Read the input file until all entries matching the indices from the filter file have been retrieved

            printv(f'--- Start filtering marine locations ---', verbose=verbose, indent=indent)
            printv(f'input file: {inputfile}', verbose=verbose, indent=indent)
            printv(f'filter file: {filterfile}', verbose=verbose, indent=indent)
            printv('', verbose=verbose)

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

                        if doublecheck:
                            original_value = preprocessquotationmark.apply(obs[data_controlkey_idx])
                            original_value = standardizenan.stdnan(original_value, additional_policy='contains_letters_or_digits')
                            filter_value = preprocessquotationmark.apply(lines[filter_controlkey_idx])
                            filter_value = standardizenan.stdnan(filter_value, additional_policy='contains_letters_or_digits')
                            try:
                                original_value = int(float(original_value))
                                filter_value = int(float(filter_value))
                            except (TypeError, ValueError):
                                pass
                            ismissing = pd.isnull(filter_value) and pd.isnull(original_value)
                            if (not ismissing) and (original_value != filter_value):
                                raise Exception(f'`filtermarineslocations.py` | Value mismatch at line n°{idx} between original ({original_value}) and filter file ({filter_value}). This may indicate a processing error.')

                        if keep_mask:
                            obs.insert(0,str(int(float(lines[mask_idx]))))

                        data.append(inputfile_sep.join(obs))

                        count += 1

                    ## Save data every 100,000 lines

                    if (count%100000) == 0:
                        store(data, outputfile, verbose=verbose, indent=indent)
                        data.clear()

                    if (count%1000000) == 0:
                        printv(f'Processing | {count} lines done (input file: line {idx})', verbose=verbose, indent=indent)

                    ## Next filter index

                    lines = filter.readline()
                    if lines == '':
                        # no more data to retrieve
                        break
                    lines = lines.strip('\n').split(filter_sep)
                    index = int(lines[index_idx])

    if len(data) != 0:
        store(data, outputfile, verbose=verbose, indent=indent)

    return error, count

@export
def apply(inputfile, filterfile, inputfile_format='uncompressed_gzip', controlkey=None, keep_mask=False, inputfile_sep='\t', filter_sep='\t', outputfile='', cleanup=True, verbose=True, indent=''):

    inputfile_sep = inputfile_sep.encode('utf-8').decode('unicode_escape')
    filter_sep = filter_sep.encode('utf-8').decode('unicode_escape')

    if len(outputfile) == 0:
        temp = inputfile.split('.')
        assert len(temp) <= 2
        outputfile = temp[0] + '_marine'
        if len(temp) == 2:
            outputfile += f'.{temp[1]}'

    start = time.time()

    if inputfile_format == 'parquet':
        count = filter_parquet(inputfile, filterfile, controlkey=controlkey, filter_sep=filter_sep, outputfile=outputfile, verbose=verbose, indent=indent)
    elif (inputfile_format == 'uncompressed_gzip') or (inputfile_format == 'pandas'):
        error, count = filter_uncompressed_gzip(inputfile, filterfile, controlkey=controlkey, inputfile_sep=inputfile_sep, filter_sep=filter_sep, keep_mask=keep_mask, outputfile=outputfile, verbose=verbose, indent=indent)
        if error != 0:
            printv(f'ERROR:', verbose=verbose, indent=indent)
            printv(f'SplittingError: {error} observations produced a different number of fields upon splitting compared to the header, and were consequently ignored.', verbose=verbose, indent=indent)
    else:
        raise ValueError(f"`filtermarinelocations.py` | '{inputfile_format}' not supported for `inputfile_format`. Must be either 'parquet' or 'uncompressed_gzip'")

    end = time.time()

    if cleanup: # NEW NEW NEW
        printv('* Cleaning up intermediate files', verbose=verbose, indent=indent)
        printv(f'  >>> {filterfile}', verbose=verbose, indent=indent)
        os.remove(filterfile)

    printv(f'TIME : {round(end-start,0)}s', verbose=verbose, indent=indent)
    printv(f'COUNT: {count} marine data', verbose=verbose, indent=indent)

    return outputfile

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Retrieve data from a file based on a filter file containing the indices of the data to be extracted', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputfile-path', type=str, help='path to the file to be processed (default delimiter: tab)')
    parser.add_argument('filterfile-path', type=str, help="path to the filter file, which must contain a sorted 'index' column (default delimiter: tab)")
    parser.add_argument('--inputfile-format', type=str, help="file format, either 'pandas' for formats supported by pandas.read_csv, 'parquet' for Parquet files, or 'uncompressed_gzip' for plain text or gzip-compressed files", default='uncompressed_gzip')
    parser.add_argument('--inputfile-delimiter', type=str, help='input file delimiter', default='\t')
    parser.add_argument('--filter-delimiter', type=str, help='filter file delimiter', default='\t')
    parser.add_argument('--control-column', type=str, help='control column name', default=None)
    parser.add_argument('--outputfile-path', type=str, help='output file path', default='')
    args = parser.parse_args()

    inputfile = args.inputfile_path
    filterfile = args.filterfile_path
    inputfile_sep = args.inputfile_delimiter.encode('utf-8').decode('unicode_escape')
    filter_sep = args.filter_delimiter.encode('utf-8').decode('unicode_escape')
    inputfile_format = args.inputfile_format
    controlkey = args.control_column
    outputfile = args.outputfile_path

    print()
    print(f'`filtermarinelocations.py` | Retrieve data from the input file corresponding to the indices in the filter file')
    print()

    _ = apply(inputfile, filterfile, inputfile_format=inputfile_format, controlkey=controlkey, inputfile_sep=inputfile_sep, filter_sep=filter_sep, outputfile=outputfile)

