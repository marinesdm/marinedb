#!/usr/bin/python
# coding: utf-8

# External imports

import os
import pandas as pd

# Internal imports

from . import *
from .spatial import *
from .temporal import *
from .taxonomic import *
from .marineloc import *

__all__ = ['contains', 'doesnotcontain','dropvalues','isboundedby','isin','isna','notisin','marineloc','doeslateqlon','isbelow_minlatlonprecision','iszero','lettersonly','taxasubset','parsedate','processdateinterval','splitdate','temporal']

def apply(df, config_dict, indent=indent, store_stats=True, outputfile_stats='cleaning_stats.txt'):

    header = []
    stats = []

    for procstep in config_dict:

        colname = list(procstep.keys())[0]

        for proc in procstep[colname]:

            columns_before = set(df.columns)

            if isinstance(proc, dict):
                proc_name = list(proc.keys())[0]
                proc_params = proc[proc_name]
            else:
                proc_name = proc
                proc_params = {}

            length_before=len(df)

            if colname == 'tool':

                colname = [key for key in proc_params.keys() if 'key' in key]
                if len(colname) != 0:
                    print(indent + f'* {", ".join(colname)}')
                    procstep_string = f'{"-".join(colname)}'
                else:
                    print(indent + f'* dataframe')
                    procstep_string = 'dataframe'
                print(indent + f'** {proc_name}')
                procstep_string = '_'.join(procstep_string, proc_name)

                proc_params['indent'] = indent + '   '
                df = eval(f"{proc_name}.apply(df, indent='   ', **proc_params)")

            else:

                print(indent + f'* {colname}')
                print(indent + f'** {proc_name}')
                proc_params['indent'] = indent + '   '

                df = eval(f"{proc_name}.apply(df, colname, indent='   ', **proc_params)")

            print()
            length_after = len(df)
            print(indent + f'{proc_name} | before: {length_before}, after: {length_after}')
            if store_stats:
                header += [f'{procstep_string}' + '_before', f'{procstep_string}' + '_after']
                stats += [length_before, length_after]

            columns_after = set(df.columns)
            new_columns = columns_after - columns_before
            if len(new_columns) != 0:
                print(f'    {proc_name} | new columns: {list(new_columns)}')
            print()

    if store_stats:
        stats = pd.DataFrame([stats], columns=header, dtype=int)
        if os.path.exists(outputfile_stats):
            stats.to_csv(outputfile_stats, sep='\t', index=False, header=False, mode='a')
        else:
            stats.to_csv(outputfile_stats, sep='\t', index=False)

    return df

