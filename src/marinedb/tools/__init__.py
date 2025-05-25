#!/usr/bin/python
# coding: utf-8

# External imports

import os
import pandas as pd

# Internal imports

from marinedb.tools import contains, doesnotcontain, dropvalues, isboundedby, isin, notisin, isna
from marinedb.tools.spatial import *
from marinedb.tools.temporal import *
from marinedb.tools.taxonomic import *
from marinedb.tools.marineloc import *

from marinedb.utils.printverbose import printv


# Global variable

__all__ = ['contains', 'doesnotcontain','dropvalues','isboundedby','isin','isna','notisin','doeslateqlon','isbelow_minlatlonprecision','iszero','lettersonly','taxasubset','parsedate','processdateinterval','splitdate','temporal']


def apply(df, config_dict, verbose=True, indent='', store_stats=True, outputdir_marinedb='./', outputfile_marinedb='marinedb_stats.txt'):

    if len(os.path.dirname(outputfile_marinedb)) == 0:
        outputfile_marinedb = os.path.join(outputdir_marinedb, outputfile_marinedb)

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

            proc_params['verbose'] = verbose
            proc_params['indent'] = indent + '   '

            length_before=len(df)

            if colname == 'tool':

                colname = [value for key, value in proc_params.items() if 'key' in key]
                if len(colname) != 0:
                    printv(f'* {", ".join(colname)}', verbose=verbose, indent=indent)
                    procstep_string = f'{"-".join(colname)}'
                else:
                    printv(f'* dataframe', verbose=verbose, indent=indent)
                    procstep_string = 'dataframe'
                printv(f'** {proc_name}', verbose=verbose, indent=indent)

                procstep_string = '_'.join([procstep_string, proc_name])

                df = eval(f"{proc_name}.apply(df, **proc_params)")

            else:

                printv(f'* {colname}', verbose=verbose, indent=indent)
                printv(indent + f'** {proc_name}', verbose=verbose, indent=indent)

                procstep_string = '_'.join([colname, proc_name])

                df = eval(f"{proc_name}.apply(df, colname, **proc_params)")

            length_after = len(df)
            printv(f'{proc_name} | before: {length_before}, after: {length_after}', verbose=verbose, indent=indent + '   ')

            if store_stats:
                header += [f'{procstep_string}' + '_before', f'{procstep_string}' + '_after']
                stats += [length_before, length_after]

            columns_after = set(df.columns)
            new_columns = columns_after - columns_before
            if len(new_columns) != 0:
                printv(f'{proc_name} | new column(s): {list(new_columns)}', verbose=verbose, indent=indent + '   ')
            printv('', verbose=verbose, indent=indent)

    if store_stats:
        stats = pd.DataFrame([stats], columns=header, dtype=int)
        if os.path.isfile(outputfile_marinedb):
            stats.to_csv(outputfile_marinedb, sep='\t', index=False, header=False, mode='a')
        else:
            stats.to_csv(outputfile_marinedb, sep='\t', index=False)

    return df

