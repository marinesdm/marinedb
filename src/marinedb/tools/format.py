#!/usr/bin/env python3
# coding: utf-8

# External import

from importlib.resources import files
import pandas as pd
import argparse
import json

# Internal import

from marinedb.utils import standardizenan
from marinedb.utils import resolvepath
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

    jedi_dataset.to_csv(outputfile, sep='\t', index=False)

    return None

def apply(inputfile, dataset_name, outputfile=None, outputdir=None):

    if outputfile is None:
        temp = os.path.basename(inputfile).split('.')
        outputfile = temp[0] + '_processedby_format'
        if len(temp) == 2:
            outputfile += f'.{temp[1]}'
    if outputdir is None:
        outputdir = os.path.dirname(resolvepath(inputfile))
    if len(os.path.dirname(outputfile)) == 0:
        outputfile = os.path.join(outputdir, outputfile)

    if dataset_name == 'jedi':
        format_jedi(inputfile, outputfile)
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
