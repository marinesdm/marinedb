#!/usr/bin/python
# coding: utf-8

# External import

import os
import time
import shutil
import pandas as pd
from operator import itemgetter

# Internal import

from marinedb.utils import resolvepath
from marinedb.utils import convertbytes
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv
from marinedb.utils import getdefaultoutputfile

from marinedb.tools import getcolumnname
from marinedb.tools.taxonomic import isinworms

# Global variable

__all__ = [] # populated using the @export decorator

CHUNKSIZE = 100000

@export
def apply(inputfile, isinworms_params, matchtype_key='classif_matchtype_generatedby_isinworms', remove_verbatim_keys=None, store_manual_filter=True, outputfile=None, verbose=True, indent=''):

    if (outputfile is None) or (len(outputfile) == 0) or (outputfile == inputfile):
        outputfile = getdefaultoutputfile.apply(inputfile, 'resolvetaxamatch', verbose=verbose, indent=indent)
    input_is_output = (inputfile == outputfile)
    if input_is_output:
        outputfile = outputfile.split('.')[0] + '.temp'

    outputdir = resolvepath.apply(os.path.dirname(inputfile))
    _, _, available_disk_space = shutil.disk_usage(outputdir)
    inputfile_size = os.stat(inputfile).st_size
    if inputfile_size >= available_disk_space:
        raise Exception(f'`resolvetaxamatch.py` | The available disk space at {outputdir} (i.e. {convertbytes.apply(available_disk_space)}) should be at least equal to the size of {inputfile} (i.e {convertbytes.apply(inputfile_size)})')

    if 'rank_mapping' not in isinworms_params:
        raise Exception(f'`resolvetaxamatch.py` | `isinworms_params` is missing the required `rank_mapping` key')

    columns_mapping = isinworms_params['rank_mapping']
    columns_input = list(columns_mapping.keys())
    columns_data = list(itemgetter(*columns_input)(columns_mapping))
    with open(inputfile,'r') as data:
        header = data.readline().strip('\n').split('\t')
    header_df = pd.DataFrame([], columns=header)
    for i,key in enumerate(columns_data):
        _, columns_data[i], _ = getcolumnname.apply(header_df, key, '', inplace=True)

    print('columns_data:',columns_data) #debug
    print('header:',header)
    print(set(columns_data) - set(header))
    assert len(set(columns_data) - set(header)) == 0

    # Retrieve suspect matches

    params = {
              'sep': '\t',
              'chunksize': CHUNKSIZE,
              'skip_blank_lines': False,
              'on_bad_lines': 'error', # avoid `usecols` to ensure `on_bad_lines` error triggers
              'engine': 'python'
             }

    printv('* Retrieve unique taxonomic classifications flagged as suspect matches', verbose=verbose, indent=indent)
    #low-confidence or suspect matche: on pourrait laisser choisir list matchtype_key, et intégrer le code qui va chercher les données originales pour gbif

    start = time.time()
    unique_classification = set()
    before = 0

    with pd.read_csv(inputfile, **params) as reader:

        for i,chunk in enumerate(reader):

            chunk_length = len(chunk)
            before += chunk_length

            chunk = chunk.loc[chunk[matchtype_key] == 'noclassification_suspicious', columns_data]

            if len(chunk) != 0:
                chunk = chunk.values.tolist()
                chunk = [tuple(line) for line in chunk]
                unique_classification.update(chunk)

            if ((i+1)%10 == 0):
                nlines = i*CHUNKSIZE + chunk_length
                printv(f'Progress | {nlines:,d} lines ({round(time.time()-start)}s): {len(unique_classification):,d} unique flagged classifications', verbose=verbose, indent=indent)

    # Manually resolve suspect matches

    if len(unique_classification) == 0:
        printv('INFO | No suspect taxonomic matches', verbose=verbose, indent=indent)
        if input_is_output:
            outputfile = inputfile
        else:
            os.rename(inputfile, outputfile)
        printv(f'resolvetaxamatch | before: {before:,d}, after : {before:,d} (0)', verbose=verbose, indent=indent)
        return outputfile

    classification = pd.DataFrame(list(unique_classification), columns=columns_input)
    classificationByClassification = classification.fillna('_MISSING_').groupby(columns_input)
    assert classificationByClassification.ngroups == len(classification)

    printv('', verbose=verbose, indent=indent)
    printv(f'* Manually resolve questionable taxonomic matches | {len(unique_classification)} matches to be reviewed', verbose=verbose, indent=indent)

    isinworms_params['parallel'] = False
    isinworms_params['store_createwormsfilters'] = False
    if store_manual_filter:
        isinworms_params['store_isinworms'] = True
        isinworms_params['overwrite_isinworms'] = False
        isinworms_params['outputfile'] = 'manual_filter_generatedby_resolvetaxamatch.txt'
        isinworms_params['outputdir_isinworms'] = os.path.dirname(outputfile)
    else:
        isinworms_params['store_isinworms'] = False
    isinworms_params['resume'] = True
    isinworms_params['verbose'] = verbose
    isinworms_params['indent'] = indent + '  '
    isinworms_params['inplace'] = True
    isinworms_params['interactive_mode'] = True
    isinworms_params['stdnan'] = True
    isinworms_params['rank_mapping'] = {
                                        'scientificname':'scientificname',
                                        'genus':'genus',
                                        'family':'family',
                                        'order':'order',
                                        'cls':'cls',
                                        'phylum':'phylum',
                                        'kingdom':'kingdom'
                                        }
    isinworms_params['verbatimcolumn'] = None #à changer
    isinworms_params['verbatimauthorshiponly'] = None #à changer
    isinworms_params['flag_nomatch'] = True
    isinworms_params['flag_uncertain'] = True

    classification = isinworms.apply(classification, **isinworms_params)
    print('columns:', list(classification.columns)) #debug
    keys = list(columns_mapping.keys())
    for key in keys:
        _, new_key, _ = getcolumnname.apply(classification, key, '', inplace=True)
        columns_mapping[new_key] = columns_mapping.pop(key)
    classification = classification.rename(columns=columns_mapping)
    print('columns:', list(classification.columns)) #debug
    columns_output = list(classification.columns)
    flag_columns = [c for c in columns_output if 'flag' in c]
    assert len(flag_columns) == 1

    # Expand resolved taxonomic classifications to full dataset

    printv(f'* Apply resolved taxonomic classifications to full dataset', verbose=verbose, indent=indent)

    check = True
    init = True
    after = 0
    start = time.time()

    with pd.read_csv(inputfile, **params) as reader:

        for i,chunk in enumerate(reader):

            chunk_length = len(chunk)

            if check:
                assert len(set(columns_output) - set(flag_columns) - set(chunk.columns)) == 0
                columns_overwrite = list(set(columns_output).intersection(chunk.columns)) #ERREUR mapping
                nomatch_flag = [c for c in chunk.columns if ('flag_taxamatch' in c) and ('nomatch' in c)]
                assert len(nomatch_flag) <= 1
                isflag = (len(nomatch_flag) == 1)
                check = False

            if remove_verbatim_keys is not None:
                chunk = chunk.drop(columns=remove_verbatim_keys)

            indices = list(chunk[chunk[matchtype_key] == 'noclassification_suspicious'].index)

            # Process

            if len(indices) != 0:

                chunk.loc[indices, columns_data] = chunk.loc[indices, columns_data].fillna('_MISSING_')
                chunkByClassification = chunk.loc[indices, columns_data].groupby(columns_data)

                chunk_classifications = list(chunkByClassification.groups.keys())
                for clsf in chunk_classifications:
                    indices_chunk = chunkByClassification.get_group(clsf).index
                    idx_classification = classificationByClassification.get_group(clsf).index[0]
                    chunk.loc[indices_chunk, columns_overwrite] = classification.loc[idx_classification, columns_overwrite].values

                if isflag:
                    chunk.loc[chunk['taxamatch_generatedby_isinworms'] == 'nomatch', nomatch_flag] = True
                else:
                    chunk = chunk[chunk['taxamatch_generatedby_isinworms'] != 'nomatch']

            after += len(chunk)

            # Store

            if init:
                chunk.to_csv(outputfile, sep='\t', index=False, mode='w')
                init = False
            else:
                chunk.to_csv(outputfile, sep='\t', index=False, mode='a',header=False)

            if ((i+1)%2 == 0): #3
                nlines = i*CHUNKSIZE + chunk_length
                printv(f'Progress | {nlines:,d} lines ({round(time.time()-start)}s): {after:,d} lines remaining', verbose=verbose, indent=indent)

    # Clean

    printv('', verbose=verbose, indent=indent)
    printv(f'* Delete {inputfile}', verbose=verbose, indent=indent)
#    os.remove(inputfile) #debug
#    if input_is_output:
#        os.rename(outputfile, inputfile)

    printv(f'resolvetaxamatch | before: {before:,d}, after : {after:,d} ({after - before:,d})', verbose=verbose, indent=indent)

    return outputfile
