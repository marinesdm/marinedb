#!/usr/bin/env python3

# External imports
import gzip
import argparse
import yaml
import numpy as np
import pandas as pd
import datetime3_11 as datetime
import time

# Local imports
import filters
import filters.getwormsfilters as gwf
import fiters.standardizenan as stdnan
import filters.convertdatetype as cvtdate

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
    else:
        return list(onekeydict.keys())[0]

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
            colname_new=get_key(column[colname_new])
        columns2keep[colname_old]=colname_new

    return columns2keep


def format_df(df, config):

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

        if (coltype!='') and (known_key or known_value): #None

            if 'datetime' in coltype:
                df=cvtdate.apply(df,colname_old)

            if known_key:
                df[colname_old]=df[colname_old].astype(TYPE[coltype])
            else:
                df[colname_old]=df[colname_old].astype(coltype)

        else:

            print(f'        Warning: unspecified types for {colname_old}, `str` by default.')
            df[colname_old]=df[colname_old].astype('string')

    return df


def processing_data(df2clean, config, columns2keep, init=False):

    # Apply several filters to filter the columns or the observations

    print(f'    * Filtering:')

    print(f'        ** standardizenan')
    df = stdnan.apply(df, key=None)

    columns_before = set(df.columns)
    df2clean = filters.filter(df2clean, config["filters"])
    columns_after = set(df.columns)
    new_columns = list(columns_after - columns_before)

    if init:
        columns2keep = create_columns2keep(config)
        if len(new_columns)!=0:
            for col in new_columns:
                columns2keep[col]=col

    # Select the columns

    print(f'    * Selecting columns:')
    print(f'     {list(columns2keep.keys())}')
    df2clean = df2clean[list(columns2keep.keys())]

    # Apply dtype conversion

    print(f'    * Applying dtype conversion')
    df2clean = format_df(df2clean, config["variables"])


    # Rename the columns

    df2clean = df2clean.rename(columns=columns2keep)

    return df2clean, config, columns2keep


def write_tsvfile(df, tsv_filename, init=False):

    print(f'Storing in {tsv_filename} | {len(df)} observations')
    if init:
        df.to_csv(tsv_filename, mode='w', index=False, header=True, sep='\t')
    else:
        df.to_csv(tsv_filename, mode='a', index=False, header=False, sep='\t')

    return True


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Clean gzip file from GBIF')
    parser.add_argument('config_file', type=str, help='path to the yaml configuration file')
    args = parser.parse_args()

    config = yaml.safe_load(open(args.config_file,'r'))["data"]
    config["variables"].append({'gbifID':{'gbifID':'int'}})
    output_file = config["output_path"] + config["output_file"]
    worms=False

    print(f'----- Start cleaning: {config["gbif_gz_file"]} -----')

    start_cleaning = time.time()

    try:
        # If filters are to be applied to the "species" column
        species_idx = get_keys(config["filters"]).index("species")
        try:
            # If the "isinworms" filter is to be applied to the "species" column
            isinworms_idx = get_keys(config["filters"][species_idx]["species"]).index("isinworms")
            ## Create the filters if needed or load them
            print(f'Processing | Full dataset')
            print('    * Creating WoRMS filters')
            worms_matchfilter, worms_acceptedfilter = gwf.get_WoRMSfilter(config["gbif_gz_file"], store=True, outputpath=config["input_path"], overwrite=False)
            ## Add the filters to config
            config["filters"][species_idx]["species"][isinworms_idx]["isinworms"]["matchfilter"] = worms_matchfilter.copy(deep=True)
            config["filters"][species_idx]["species"][isinworms_idx]["isinworms"]["acceptedfilter"] = worms_acceptedfilter.copy(deep=True)
            del worms_matchfilter
            del worms_acceptedfilter
            worms=True
        except ValueError:
            pass
    except ValueError:
        pass


    # Read the tsv data file

    with gzip.open(config['gbif_gz_file'],'r') as gbif_data:

        header = gbif_data.readline().decode("utf8").strip('\n').split('\t')
        header_length = len(header)

        columns2keep = create_columns2keep(config)

        batch = 0
        data2clean = []
        init=True
        error = 0

        start=time.time()
        for idx, line in enumerate(gbif_data):

            if batch < BATCH_SIZE:
                # Add observations
                obs = line.decode("utf8").strip('\n').split('\t')
                if len(obs) == header_length:
                    data2clean.append(obs)
                    batch += 1
                else:
                    error += 1
                    print(f'    SplittingError: splitting gives more fields than columns line n°{idx}, the value will be ignored')
                    print(f'                    line n°{idx}: {line}')
            else:
                df2clean = pd.DataFrame(data2clean,columns=header)

                # Process data
                print()
                print(f'Processing | {idx+1} lines done')
                df2clean, config, columns2keep = processing_data(df2clean, config, columns2keep, init=init, worms=worms)

                # Store data
                write_tsvfile(df2clean, output_file, init=init)

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
        write_tsvfile(df2clean, output_file)

    print()
    print(f'----- End cleaning: {config["gbif_gz_file"]} -----')
    print()
    if error!=0:
        print(f'SplittingError: For {error} observations, splitting gave more fields than columns and the observations have been ignored.')
        print()
    print(f'TIME : {np.round(time.time() - start_cleaning,0)}s')
