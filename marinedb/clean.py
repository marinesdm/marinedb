#!/usr/bin/env python3

# External imports
import gzip
import argparse
import yaml
import numpy as np
import pandas as pd
import time

# Local imports
import tools
import tools.createwormsfilters as cwf
import utils.standardizenan
import utils.convertdatetype
from marinedb.utils import writedataframe

TYPE = {
        'int':'Int64',
        'float':'Float64',
        'str':'string', #preserve NaN
        'bool':'boolean',
        'datetime':'datetime64[ns]'
       }


BATCH_SIZE = 100000 #issues if too big


def get_key(onekeydict):

    if isinstance(onekeydict, str):
        return onekeydict
    elif isinstance(onekeydict, dict):
        keys=list(onekeydict.keys())
        if len(keys)==1:
            return keys[0]
        else:
            raise Exception(f'The dictionary should contain only one key, not {len(keys)}')
    else:
        raise TypeError(f'Type not recognized: {type(onekeydict)}')

def get_keys(list_onekeydict):

    return [get_key(list_onekeydict[idx]) for idx in range(len(list_onekeydict))]

def create_columns2keep(config):

    config_columns = config["variables"]
    columns2keep={}

    for column in config_columns:

        if isinstance(column, str):
            columns2keep[column]=column

        else:
            colname_old=get_key(column)
            colname_new=get_key(column[colname_old])
            columns2keep[colname_old]=colname_new

    return columns2keep


def dtypeconversion(df, config):

    for column in config:

        if isinstance(column, dict):
            colname_old=get_key(column)
            if isinstance(column[colname_old], dict):
                colname_new=get_key(column[colname_old])
                coltype=column[colname_old][colname_new]
            else:
                coltype=''
        else:
            coltype=''

        known_key=(coltype in TYPE.keys())
        known_value=(coltype in TYPE.values())

        if (coltype!=''):

            if (known_key or known_value): #None

                if 'datetime' in coltype:
                    df=convertdatetype.apply(df,colname_old)

                if known_key:
                    df[colname_old]=df[colname_old].astype(TYPE[coltype])
                else:
                    df[colname_old]=df[colname_old].astype(coltype)

            else:

                print(f'        INFO | {coltype} is not a recognized type')
                try:
                    df[colname_old]=df[colname_old].astype(coltype)
                except TypeError:
                    print(f'        WARNING | Type conversion to {coltype} failed')
                    coltype=''

        if (coltype==''):

            print(f'        INFO | No type specified for {colname_old}, `str` by default.')
            df[colname_old]=df[colname_old].astype('string')

    return df


def processing_data(df2clean, config, columns2keep, init=False):

    # Apply several filters to filter the columns or the observations

    print(f'    ** standardizenan')
    df = standardizenan.apply(df, key=None, letters_only=False)

    columns_before = set(df.columns)
    df2clean = tools.apply(df2clean, config["processing"])
    columns_after = set(df.columns)
    new_columns = list(columns_after - columns_before)

    if init:
        columns2keep = create_columns2keep(config)
        if len(new_columns)!=0:
            for col in new_columns:
                columns2keep[col]=col

    # Select the columns

    print(f'    ** columnselection')
    print(f'     {list(columns2keep.keys())}')
    df2clean = df2clean[list(columns2keep.keys())]

    # Apply dtype conversion

    print(f'    ** dtypeconversion')
    df2clean = dtypeconversion(df2clean, config["variables"])


    # Rename the columns

    print(f'    ** columnrenaming')
    df2clean = df2clean.rename(columns=columns2keep)

    return df2clean, config, columns2keep


#def write_tsvfile(df, tsv_filename, init=False):
#
#    print(f'Storing in {tsv_filename} | {len(df)} observations')
#    if init:
#        df.to_csv(tsv_filename, mode='w', index=False, header=True, sep='\t')
#    else:
#        df.to_csv(tsv_filename, mode='a', index=False, header=False, sep='\t')

#    return True


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Clean gzip file from GBIF.')
    parser.add_argument('config_file', type=str, help='path to the yaml configuration file')
    args = parser.parse_args()

    config = yaml.safe_load(open(args.config_file,'r'))["data"]
    outputfile = config["output_path"] + config["output_file"]

    print(f'----- Start cleaning: {config["gbif_gz_file"]} -----')

    start_cleaning = time.time()

    # Check if `isinworms` is among the filters to apply

    wormsfiltering = False

    isinworms_filter = [filter for filter in config["processing"] if "isinworms" in str(filter)]
    isinworms_column = get_keys(isinworms_filter)

    if len(isinworms_filter)>1:
        raise Exception(f'The `isinworms.py` filter should be applied only to the column containing species names. Select one from {isinworms_column}')

    elif len(isinworms_filter)==1:

        # Set up the required components to apply the `isinworms` filter

        isinworms_column = isinworms_column[0]
        isinworms_column_idx = get_keys(config['processing']).index(isinworms_column)
        isinworms_idx = get_keys(config['processing'][isinworms_column_idx][isinworms_column]).index('isinworms')
        isinworms_params = config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']
        isinworms_args = list(isinworms_params.keys())

        if 'outputpath' not in isinworms_args:
            config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']['outputpath']=config['input_path']
            isinworms_params = config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']
            isinworms_args = list(isinworms_params.keys())

        createwormsfilters_args = list(inspect.signature(cwf.create_WoRMSfilter).parameters.keys())
        createwormsfilters_params = {arg : isinworms_params[arg] for arg in isinworms_args if arg in createwormsfilters_args}
        createwormsfilters_params['gzfile_path'] = config['gzfile_path']
        createwormsfilters_params['colname'] = isinworms_column
        createwormsfilters_params['store'] = True

        ## Load existing filters or generate new ones if none are found

        #print('Initialization | Prepare for standardization using WoRMS')
        print('* Initialization')
        print('    ** createwormsfilters')

        worms_matchfilter, worms_acceptedfilter = cwf.create_WoRMSfilter(**createwormsfilters_params)

        ## Add the filters to `config`

        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']["matchfilter"] = worms_matchfilter.copy(deep=True)
        config['processing'][isinworms_column_idx][isinworms_column][isinworms_idx]['isinworms']["acceptedfilter"] = worms_acceptedfilter.copy(deep=True)

        del worms_matchfilter
        del worms_acceptedfilter

        wormsfiltering = True

    # Read the gzip text data file

    print('* Processing')

    with gzip.open(config['gzfile_path'],'r') as gbif_data:

        header = gbif_data.readline().decode("utf8").strip('\n').split('\t')
        header_length = len(header)

        columns2keep = create_columns2keep(config)

        batch = 0
        data2clean = []
        init=True
        error = []

        start=time.time()
        for idx, line in enumerate(gbif_data):

            # Add observations

            obs = line.decode("utf8").strip('\n').split('\t')
            obs = [preprocessquotationmark(value) for value in obs]

            if len(obs)==header_length:
                data2clean.append(obs)
                batch += 1
            else:
                error.append(idx+2)
                print()
                print(f'    SplittingError: splitting gives more fields than columns line n°{idx+2}, the value will be ignored')
                print(f'                    line n°{idx+2}: {line}') #DEBUG comment

            if batch==BATCH_SIZE:

                df2clean = pd.DataFrame(data2clean,columns=header)

                # Process data
                print()
                print(f'Processing | {idx+1} lines done')
                df2clean, config, columns2keep = processing_data(df2clean, config, columns2keep, init=init, worms=worms)

                # Store data

                writedataframe.to_txt(df2clean, outputfile, init=init, verbose=True)

                end=time.time()
                print()
                print(f'TIME : {np.round(end-start,0)}s')

                init=False
                data2clean.clear()
                batch=0
                start=time.time()

    if batch!=0:

        df2clean = pd.DataFrame(data2clean,columns=header)

        # Process data
        print()
        print(f'Processing | {idx+1} lines done (end of file)')
        df2clean, config, columns2keep = processing_data(df2clean, config, columns2keep)

        # Store data
        #write_tsvfile(df2clean, outputfile)
        writedataframe.to_txt(df2clean, outputfile, init=False, verbose=True)

    print()
    print(f'----- End cleaning: {config["gbif_gz_file"]} -----')
    print()
    if len(error)!=0:
        print(f'SplittingError: For {len(error)} observations, splitting resulted in more fields than columns, and these observations have been excluded.')
        print(f'Refer to lines: {error}')
    print(f'TIME : {np.round(time.time() - start_cleaning,0)}s')
