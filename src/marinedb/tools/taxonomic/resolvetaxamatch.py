#!/usr/bin/python
# coding: utf-8

# External import

import os
import time
import math
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
def apply(inputfile, isinworms_params, review_level=1, taxamatch_key = 'taxamatch_generatedby_isinworms', matchtype_key='classif_matchtype_generatedby_isinworms', auxiliary_columns=None, flag_uncertain=True, manual_filter_file='manual_filter_generatedby_resolvetaxamatch.txt', resume=True, store_manual_filter=True, outputfile=None, verbose=True, indent=''):

    with open(inputfile,'r') as data:
        header = data.readline().strip('\n').split('\t')
    print('flag_uncertain',flag_uncertain)
    # Auxiliary columns required during processing
    # but not requested by the user

    if auxiliary_columns is None:
        auxiliary_columns = []
    elif len(auxiliary_columns) != 0:
        print(auxiliary_columns) #debug
        update_colnames = pd.DataFrame([],columns=header)
        temp = []
        for colname in auxiliary_columns:
            _, updated_colname, _ = getcolumnname.apply(update_colnames, colname, '', inplace=True)
            if colname == updated_colname:
                updated_colname = [c for c in header if c.startswith(colname)]
                assert len(updated_colname) == 1
                updated_colname = updated_colname[0]
            temp.append(updated_colname)
        auxiliary_columns = temp
        print(auxiliary_columns) #debug

    if not flag_uncertain:
        auxiliary_columns.append('flag_taxamatch_generatedby_isinworms_isin_uncertain')

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

    outputdir = resolvepath.apply(os.path.dirname(outputfile))
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
    if is_verbatim:
        if isinstance(isinworms_params['verbatimcolumn'], str):
            isinworms_params['verbatimcolumn'] = [isinworms_params['verbatimcolumn']]

    # Review level: include mismatch cases from most to least likely to be false mismatches

    # highest risk of false mismatch
    # classification mismatch but kingdom match (potential taxonomic changes)
    classif_matchtype = ['noclassification_kingdomMatch']

    if review_level > 1:
        # moderate risk of false mismatch
        # classification match but authorship mismatch with isMore flag (potential code limitation)
        classif_matchtype.append('classification_authorship_noMatchIsMore')

    if review_level == 3:
        # lower risk of false mismatch (more reliable mismatches)
        # classification mismatch and authorship mismatch with isMore flag (potential code limitation)
        classif_matchtype.append('noclassification_authorship_noMatchIsMore')

    # Select columns

    columns_mapping = isinworms_params['rank_mapping']
    columns_input = list(columns_mapping.keys())
    columns_data = [columns_mapping[c] for c in columns_input]

    if is_verbatim:
        # some verbatim columns may also be used as rank columns
        verbatim_columns = list(set(isinworms_params['verbatimcolumn']) - set(columns_data))
        columns_input += verbatim_columns
        columns_data += verbatim_columns
        auxiliary_columns += verbatim_columns
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

    # Retrieve mismatch cases likely to be false mismatches (candidates for manual review)

    params = {
              'sep': '\t',
              'chunksize': CHUNKSIZE,
              'skip_blank_lines': False,
              'on_bad_lines': 'error', # avoid `usecols` to ensure `on_bad_lines` error triggers
              'engine': 'python'
             }

    printv('* Retrieve potential false mismatches for manual review', verbose=verbose, indent=indent)
    #low-confidence or suspect matches: on pourrait laisser choisir list matchtype_key, et intégrer le code qui va chercher les données originales pour gbif

    start = time.time()
    unique_combinations = set()
    before = 0
    nuncertain = 0
    warning = False

    with pd.read_csv(inputfile, **params) as reader:

        for i,chunk in enumerate(reader):

            chunk_length = len(chunk)
            before += chunk_length

            # Select mismatch cases to be reviewed (based on review_level criteria)

            chunk = chunk.loc[chunk[matchtype_key].isin(classif_matchtype),:]
            chunk = chunk.astype('string')
            chunk = chunk.fillna('_MISSING_')

            if len(chunk) != 0:

                if (not warning) and (chunk[taxamatch_key] != 'uncertain').any():

                    printv('', verbose=verbose, indent=indent)
                    printv(
                         "WARNING | Some records cannot be reviewed manually because they "
                         "were categorized as 'nomatch' during `isinworms` execution "
                         "(`uncertainty_level` < `review_level`). These records will be "
                         "excluded from the review process.",
                         verbose=True,
                         indent=indent + '  '
                    )
                    printv('', verbose=verbose, indent=indent)

                    warning = True

                if warning:
                    chunk = chunk[chunk[taxamatch_key] == 'uncertain']

                # Add unique classifications linked to these mismatches,
                # excluding those already handled by the manual filter

                if len(chunk) != 0:
                    chunk = chunk[columns_data].drop_duplicates()
                    nuncertain += len(chunk)
                    unique_combinations.update(
                        t
                        for t in chunk.itertuples(index=False, name=None)
                        if t not in manual_filter_keys
                    )

            if ((i+1)%10 == 0):
                nlines = i*CHUNKSIZE + chunk_length
                printv(f'  Progress | {nlines:,d} lines ({round(time.time()-start)}s): {len(unique_combinations):,d} unique flagged classifications', verbose=verbose, indent=indent)

    # Manually review selected potential mismatches

    if nuncertain == 0:
        printv('INFO | No potential false mismatches found', verbose=verbose, indent=indent)
        if input_is_output:
            outputfile = inputfile
        else:
            os.rename(inputfile, outputfile)
        printv('', verbose=verbose, indent=indent)
        printv(f'resolvetaxamatch | before: {before:,d}, after : {before:,d} (0)', verbose=verbose, indent=indent)
        return outputfile

    ncombinations = len(unique_combinations)
    nbatch = math.ceil(ncombinations/50)

    printv('', verbose=verbose, indent=indent)
    printv(f'* Review potential false mismatches | {ncombinations} unique classifications to be reviewed ({nbatch} batches)', verbose=verbose, indent=indent)

    if ncombinations != 0:

        classification = pd.DataFrame(list(unique_combinations), columns=columns_input, dtype='string')
        classification_indices = classification.groupby(columns_input)
        classification = classification.replace('_MISSING_', pd.NA)

        assert classification_indices.ngroups == len(classification)

        # Set parameters

        isinworms_params['parallel'] = False
        isinworms_params['store_createwormsfilters'] = False
        isinworms_params['store_isinworms'] = True
        isinworms_params['overwrite_isinworms'] = (not resume)
        isinworms_params['outputfile'] = manual_filter_file
        isinworms_params['outputdir_isinworms'] = os.path.dirname(outputfile)
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

        for ibatch in range(nbatch):

            printv(f'  Progress | {ibatch + 1} / {nbatch}', verbose=verbose, indent=indent)

            start = ibatch*50
            if ibatch == (nbatch-1):
                end = ncombinations
            else:
                end = start + 50

            classification_batch = classification.iloc[start:end,:].copy()
            classification_batch_reviewed = isinworms.apply(classification_batch, **isinworms_params)

            if start == 0:
                classification_reviewed = classification_batch_reviewed
                isinworms_params['overwrite_isinworms'] = False
            else:
                classification_reviewed = pd.concat([classification_reviewed, classification_batch_reviewed])

        keys = list(columns_mapping.keys())
        for key in keys:
            _, new_key, _ = getcolumnname.apply(classification_reviewed, key, '', inplace=True)
            columns_mapping[new_key] = columns_mapping.pop(key)
        classification_reviewed = classification_reviewed.rename(columns=columns_mapping)

        if not store_manual_filter:
            # clean
            os.remove(manual_filter_file)

    else:

        printv(f"INFO | All potential mismatches already resolved in {manual_filter_file}. Processing automatically without user interaction.", verbose=verbose, indent=indent)


    if len(unique_combinations) != 0:
        columns_output = list(classification_reviewed.columns)
        flag_columns = [c for c in columns_output if 'flag' in c]
        assert len(flag_columns) == 1
    else:
        columns_output = list(set(manual_filter.columns) - set(columns_input))
        flag_columns = [c for c in columns_output if 'flag' in c]

    # Apply resolved taxonomic classifications to the full dataset

    printv('', verbose=verbose, indent=indent)
    printv(f'* Apply resolved taxonomic classifications to the full dataset', verbose=verbose, indent=indent)

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
                flag_nomatch = (len(nomatch_flag) == 1)

            resolve_mask = (chunk[taxamatch_key] == 'uncertain') & chunk[matchtype_key].isin(classif_matchtype)
            indices = list(chunk[resolve_mask].index)

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

                        idx_classification = classification_indices.get_group(clsf).index[0]
                        chunk.loc[indices_chunk, columns_overwrite] = classification_reviewed.loc[idx_classification, columns_overwrite].to_numpy()

                if flag_nomatch:
                    chunk.loc[chunk[taxamatch_key] == 'nomatch', nomatch_flag] = True
                else:
                    chunk = chunk[chunk[taxamatch_key] != 'nomatch']

            if not flag_uncertain:
                chunk = chunk[chunk[taxamatch_key] != 'uncertain']

            after += len(chunk)

            if len(auxiliary_columns) != 0:
                chunk = chunk.drop(columns=auxiliary_columns)

            # Store

            if init:
                chunk.to_csv(outputfile, sep='\t', index=False, mode='w')
                init = False
            else:
                chunk.to_csv(outputfile, sep='\t', index=False, mode='a',header=False)

            if ((i+1)%2 == 0): #3
                nlines = i*CHUNKSIZE + chunk_length
                printv(f'Progress | {nlines:,d} lines ({round(time.time()-start)}s)', verbose=verbose, indent=indent)

    # Clean

    printv('', verbose=verbose, indent=indent)

    if outputfile != inputfile:
        printv(f'* Delete {inputfile}', verbose=verbose, indent=indent)
        os.remove(inputfile)

    if input_is_output:
        os.rename(outputfile, inputfile)

    printv(f'resolvetaxamatch | before: {before:,d}, after : {after:,d} ({after - before:,d})', verbose=verbose, indent=indent)
    printv('', verbose=verbose, indent=indent)

    return outputfile
