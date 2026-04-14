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
def apply(inputfile, isinworms_params, matchtype_key='classif_matchtype_generatedby_isinworms', remove_verbatim_keys=True, manual_filter_file='manual_filter_generatedby_resolvetaxamatch.txt', resume=True, store_manual_filter=True, outputfile=None, verbose=True, indent=''):

    # Output file name

    if (outputfile is None) or (len(outputfile) == 0):
        outputfile = getdefaultoutputfile.apply(inputfile, 'resolvetaxamatch', verbose=verbose, indent=indent)
    input_is_output = (inputfile == outputfile)
    if input_is_output:
        outputfile = outputfile.split('.')[0] + '.temp'

    # Manual filter file path

    if resume and (len(os.path.dirname(manual_filter_file)) == 0):
        outputdir = os.path.dirname(outputfile)
        manual_filter_file = os.path.join(outputdir, manual_filter_file)
    if resume and not os.path.isfile(manual_filter_file):
        printv(f'INFO | {manual_filter_file} not found (resume={resume}). Restarting from scratch.', verbose=verbose, indent=indent)
        resume = False

    # Check that enough disk space is available

    outputdir = resolvepath.apply(os.path.dirname(inputfile))
    _, _, available_disk_space = shutil.disk_usage(outputdir)
    inputfile_size = os.stat(inputfile).st_size
    required_space = inputfile_size + inputfile_size // 10
    if available_disk_space < required_space:
        raise Exception(
                f"`resolvetaxamatch.py` | Not enough disk space in {outputdir}: "
                f"{convertbytes.apply(available_disk_space)} available, "
                f"at least {convertbytes.apply(required_space)} required."
             )

    if 'rank_mapping' not in isinworms_params:
        raise Exception(f'`resolvetaxamatch.py` | `isinworms_params` is missing the required `rank_mapping` key')

    # Handle verbatim columns

    is_verbatim = ('verbatimcolumn' in isinworms_params.keys())
    remove_verbatim_keys = remove_verbatim_keys and is_verbatim
    if is_verbatim:
        if isinstance(isinworms_params['verbatimcolumn'], str):
            isinworms_params['verbatimcolumn'] = [isinworms_params['verbatimcolumn']]

    # Select columns

    columns_mapping = isinworms_params['rank_mapping']
    columns_input = list(columns_mapping.keys())
    columns_data = [columns_mapping[c] for c in columns_input]

    if is_verbatim:
        # some verbatim columns may also be used as rank columns
        verbatim_columns = list(set(isinworms_params['verbatimcolumn']) - set(columns_data))
        columns_input += verbatim_columns
        columns_data += verbatim_columns
        # reverse `columns_mapping`
        reversed_columns_mapping = {v:k for k,v in columns_mapping.items()}
        for idx, col in enumerate(isinworms_params['verbatimcolumn']):
            try:
                isinworms_params['verbatimcolumn'][idx] = reversed_columns_mapping[col]
            except KeyError:
                pass

    with open(inputfile,'r') as data:
        header = data.readline().strip('\n').split('\t')
    assert len(set(columns_data) - set(header)) == 0

    # Use previous manual filter if specified

    manual_filter_keys = set()

    if resume:

        printv(f"INFO | Loading manual filter from previous run: {manual_filter_file}", verbose=verbose, indent=indent)

        manual_filter = pd.read_csv(manual_filter_file, sep='\t')

        # Align manual filter column names with those in the input file

        keys = list(columns_mapping.keys())
        columns_mapping_filter = {}
        for key in keys:
            _, new_key, _ = getcolumnname.apply(manual_filter, key, '', inplace=True)
            columns_mapping_filter[new_key] = columns_mapping[key]
        manual_filter = manual_filter.rename(columns=columns_mapping_filter)

        # Ensure input file columns match those of the manual filter

        missing_columns = set(columns_input + columns_data) - set(manual_filter.columns)
        if missing_columns:
            printv(f"WARNING | Missing columns in the manual filter: {', '.join(missing_columns)}. Ignoring it and restarting from scratch.", verbose=verbose, indent=indent)
            resume = False
        else:
            manual_filter_by_classification = manual_filter.fillna('_MISSING_').groupby(columns_input)
            manual_filter_keys = set(manual_filter_by_classification.groups.keys())

    # Retrieve suspicious mismatches

    params = {
              'sep': '\t',
              'chunksize': CHUNKSIZE,
              'skip_blank_lines': False,
              'on_bad_lines': 'error', # avoid `usecols` to ensure `on_bad_lines` error triggers
              'engine': 'python'
             }

    printv('* Retrieve unique taxonomic classifications flagged as uncertain mismatches', verbose=verbose, indent=indent)
    #low-confidence or suspect matches: on pourrait laisser choisir list matchtype_key, et intégrer le code qui va chercher les données originales pour gbif

    start = time.time()
    unique_classification = set()
    before = 0
    nuncertain = 0

    with pd.read_csv(inputfile, **params) as reader:

        for i,chunk in enumerate(reader):

            chunk_length = len(chunk)
            before += chunk_length

            # Select records flagged as uncertain mismatches (potential taxonomic changes)

            chunk = chunk.loc[chunk[matchtype_key] == 'noclassification_suspicious', columns_data]
            chunk = chunk.astype('string')
#            chunk = chunk.fillna('_MISSING_')

            if len(chunk) != 0:

                # Add unique classifications linked to these mismatches,
                # excluding those already handled by the manual filter

                chunk = chunk.drop_duplicates()
                nuncertain += len(chunk)
                unique_classification.update(
                    t
                    for t in chunk.itertuples(index=False, name=None)
                    if t not in manual_filter_keys
                )


            if ((i+1)%10 == 0):
                nlines = i*CHUNKSIZE + chunk_length
                printv(f'Progress | {nlines:,d} lines ({round(time.time()-start)}s): {len(unique_classification):,d} unique flagged classifications', verbose=verbose, indent=indent)

    # Manually resolve suspicious mismatches

    if nuncertain == 0:
        printv('INFO | No suspicious taxonomic mismatches', verbose=verbose, indent=indent)
        if input_is_output:
            outputfile = inputfile
        else:
            os.rename(inputfile, outputfile)
        printv(f'resolvetaxamatch | before: {before:,d}, after : {before:,d} (0)', verbose=verbose, indent=indent)
        return outputfile


    printv('', verbose=verbose, indent=indent)
    printv(f'* Manually resolve questionable taxonomic matches | {nuncertain} matches to be reviewed', verbose=verbose, indent=indent)

    if len(unique_classification) != 0:

        classification = pd.DataFrame(list(unique_classification), columns=columns_input)
        classification = classification.astype('string')
        classificationByClassification = classification.fillna('_MISSING_').groupby(columns_input)

        assert classificationByClassification.ngroups == len(classification)

        # Set parameters

        isinworms_params['parallel'] = False
        isinworms_params['store_createwormsfilters'] = False
        if store_manual_filter:
            isinworms_params['store_isinworms'] = True
            isinworms_params['overwrite_isinworms'] = (not resume)
            isinworms_params['outputfile'] = manual_filter_file
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

        isinworms_params['flag_nomatch'] = True
        isinworms_params['flag_uncertain'] = True

        # Resolve suspicious mismatches

        classification = isinworms.apply(classification, **isinworms_params)

        keys = list(columns_mapping.keys())
        for key in keys:
            _, new_key, _ = getcolumnname.apply(classification, key, '', inplace=True)
            columns_mapping[new_key] = columns_mapping.pop(key)
        classification = classification.rename(columns=columns_mapping)

    else:

        printv(f"INFO | All uncertain taxonomic matches already resolved in {manual_filter_file}. Processing automatically without user interaction.", verbose=verbose, indent=indent)


    if len(unique_classification) != 0:
        columns_output = list(classification.columns)
        flag_columns = [c for c in columns_output if 'flag' in c]
        assert len(flag_columns) == 1
    else:
        columns_output = list(set(manual_filter.columns) - set(columns_input))
        flag_columns = [c for c in columns_output if 'flag' in c]

    # Expand resolved taxonomic classifications to full dataset

    printv(f'* Apply resolved taxonomic classifications to full dataset', verbose=verbose, indent=indent)

    init = True
    after = 0
    start = time.time()

    with pd.read_csv(inputfile, **params) as reader:

        for i,chunk in enumerate(reader):

            chunk_length = len(chunk)

            if init:
                columns_overwrite = list(set(columns_output).intersection(chunk.columns))
                nomatch_flag = [c for c in chunk.columns if ('flag_taxamatch' in c) and ('nomatch' in c)]
                assert len(nomatch_flag) <= 1
                isflag = (len(nomatch_flag) == 1)

            indices = list(chunk[chunk[matchtype_key] == 'noclassification_suspicious'].index)

            if len(indices) != 0:

                chunk.loc[indices, columns_data] = chunk.loc[indices, columns_data].fillna('_MISSING_')
                chunkByClassification = chunk.loc[indices, columns_data].groupby(columns_data)

                chunk_classifications = set(chunkByClassification.groups.keys())
                for clsf in chunk_classifications:

                    indices_chunk = chunkByClassification.get_group(clsf).index

                    if clsf in manual_filter_keys:

                        # Use previous manual filter

                        idx_classification = manual_filter_by_classification.get_group(clsf).index[0]
                        chunk.loc[indices_chunk, columns_overwrite] = manual_filter.loc[idx_classification, columns_overwrite].to_numpy()

                    else:

                        # Use newly created filter

                        idx_classification = classificationByClassification.get_group(clsf).index[0]
                        chunk.loc[indices_chunk, columns_overwrite] = classification.loc[idx_classification, columns_overwrite].to_numpy()

                if isflag:
                    chunk.loc[chunk['taxamatch_generatedby_isinworms'] == 'nomatch', nomatch_flag] = True
                else:
                    chunk = chunk[chunk['taxamatch_generatedby_isinworms'] != 'nomatch']

            after += len(chunk)

            if remove_verbatim_keys:
                chunk = chunk.drop(columns=verbatim_columns)

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
    printv('', verbose=verbose, indent=indent)

    return outputfile
