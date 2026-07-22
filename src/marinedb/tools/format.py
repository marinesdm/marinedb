#!/usr/bin/env python3
# coding: utf-8

# External import

from importlib.resources import files
import pandas as pd
import argparse
import json
import os

# Internal import

from marinedb.utils.printverbose import printv
from marinedb.utils import resolvepath
from marinedb.utils import standardizenan
from marinedb.utils.allexport import export

# Global variables

JEDI_DWC_MAPPING_PATH = files('marinedb.tools.data').joinpath('jedi_dwc_mapping.json')
__all__ = [] # populated using the @export decorator

def format_jedi(inputfile, outputfile):

    jedi_dataset = pd.read_csv(inputfile, sep=',', low_memory=False)
    with open(JEDI_DWC_MAPPING_PATH, 'r') as json_file:
        jedi_dwc_mapping = json.load(json_file)
    jedi_dataset = jedi_dataset.rename(columns=jedi_dwc_mapping)

    # Normalize missing value representations ('nd' in JeDI)
    jedi_dataset = standardizenan.apply(jedi_dataset)
    # Combine the genus and specific epithet to form the binomial scientific name
    jedi_dataset['scientificName'] = jedi_dataset['genus'] + ' ' + jedi_dataset['scientificName']
    # Correct orthographic errors in scientific names
    jedi_dataset.loc[jedi_dataset['scientificName'] == 'Halicreas minum', 'scientificName'] = 'Halicreas minimum'
    # Create the 'kingdom' column
    jedi_dataset['kingdom'] = 'Animalia'
    # Create an index column
    jedi_dataset['jedi_id'] = jedi_dataset.index.tolist()

    outputfile = os.path.splitext(outputfile)[0] + '.txt'
    jedi_dataset.to_csv(outputfile, sep='\t', index=False)

    return outputfile

def apply(inputfile, dataset_name, outputfile=None, outputdir=None, overwrite=True, verbose=True, indent='') -> str:
    """Apply dataset-specific transformations required by marinedb.

    This preprocessing step is always performed before the main curation workflow. 
    Currently, only JeDI dataset is supported. 

    Args:
        inputfile (str):
            Path to the input dataset.

        dataset_name (str):
            Name of the dataset-specific formatting procedure to apply. Currently,
            only ``"jedi"`` is supported.

        outputfile (str, optional):
            Path or name of the formatted output file.

            If omitted, the output name is derived from ``inputfile`` by adding
            ``"_processedby_format"`` before the file extension.

        outputdir (str, optional):
            Directory in which to write the formatted dataset.

            If omitted, the directory is inferred from ``outputfile`` when it
            contains a directory path, or from ``inputfile`` otherwise.

        overwrite (bool, optional):
            Whether to overwrite an existing output file.

            If ``True``, the existing file is replaced. If ``False``, the existing
            file is reused without modification.

    Returns:
        Path to the formatted output file.

    Raises:
        ValueError:
            If ``dataset_name`` is not supported.
    """

    if outputfile is None:
        temp = os.path.basename(inputfile).split('.')
        outputfile = temp[0] + '_processedby_format'
        if len(temp) == 2:
            outputfile += f'.{temp[1]}'

    if outputdir is None:
        if len(os.path.dirname(outputfile)) != 0:
            outputdir = os.path.dirname(resolvepath.apply(outputfile))
        else:
            outputdir = os.path.dirname(resolvepath.apply(inputfile))

    if len(os.path.dirname(outputfile)) == 0:
        outputfile = os.path.join(outputdir, outputfile)
    outputfile = resolvepath.apply(outputfile)

    if os.path.isfile(outputfile):
        if overwrite:
            printv(f'WARNING | {outputfile} already exists and will be overwritten (overwrite={overwrite})', verbose=verbose, indent=indent)
        else:
            printv(f'INFO | Reusing existing file {outputfile} without changes (overwrite={overwrite})', verbose=verbose, indent=indent)
            return outputfile

    if dataset_name == 'jedi':
        outputfile = format_jedi(inputfile, outputfile)
    else:
        raise ValueError(f"`format.py` | '{dataset_name}' is not supported. Only 'jedi' is currently accepted for `dataset_name`")

    return outputfile

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Format the dataset')
    parser.add_argument('inputfile', type=str, help='path to the dataset file')
    parser.add_argument('dataset', type=str, help="name of the dataset to format (currently, only 'jedi' is supported)")
    parser.add_argument('outputfile', type=str, help='path and name of the outputfile')
    args = parser.parse_args()

    inputfile = args.inputfile
    outputfile = args.outputfile
    dataset_name = args.dataset

    _ = apply(inputfile, outputfile, dataset_name)
