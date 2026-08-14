#!/usr/bin/python
# coding: utf-8

# External imports

import os
import re
import glob
import time
import pandas as pd
from datetime import datetime

# Internal imports

from marinedb.tools import contains, doesnotcontain, dropvalues, isboundedby, isin, notisin, isna
#from marinedb.tools import *
from marinedb.tools.spatial import *
from marinedb.tools.temporal import *
from marinedb.tools.taxonomic import *
from marinedb.tools.marineloc import *

from marinedb.utils.printverbose import printv

# Global variable

__all__ = ['contains',
           'doesnotcontain',
           'dropvalues',
           'isboundedby',
           'isin',
           'isna',
           'notisin',
           'doeslateqlon',
           'belowminlatlonprecision',
           'iszero',
           'islatloninvalid',
           'islatlonzero',
           'lettersonly',
           'taxasubset',
           'mapbasisofrecord',
           'basisofrecordisin',
           'parsedate',
           'processdateinterval',
           'splitdate',
           'convertdatetype',
           'temporal',
           'isdateinvalid',
           'isdateunlikely']

TODAY = datetime.today().strftime('%Y%m%d')
DEFAULT_OUTPUTFILE = f'marinedb_stats_{TODAY}.txt'

def resolve_outputfile(outputfile_marinedb, df, sep="\t"):

    expected_header = df.columns.tolist()

    def header_matches(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing_header = f.readline().rstrip("\n\r").split(sep)

        return existing_header == expected_header

    def get_base_filepath(filepath):
        """
        Remove an existing _YYYYMMDD or _YYYYMMDD_HHMMSS suffix.
        """
        directory, filename = os.path.split(filepath)
        stem, ext = os.path.splitext(filename)

        stem = re.sub(
            r"_\d{8}(?:_\d{6})?$",
            "",
            stem,
        )

        return os.path.join(directory, stem + ext)

    base_filepath = get_base_filepath(outputfile_marinedb)

    directory, filename = os.path.split(base_filepath)
    stem, ext = os.path.splitext(filename)

    today = datetime.today().strftime("%Y%m%d")

    dated_filepath = os.path.join(
        directory,
        f"{stem}_{today}{ext}",
    )

    # 1. Try the requested file first
    if os.path.isfile(outputfile_marinedb):
        if header_matches(outputfile_marinedb):
            return outputfile_marinedb

    # 2. Search all existing files associated with today's date
    dated_files = glob.glob(
        os.path.join(
            directory,
            f"{stem}_{today}*{ext}",
        )
    )

    for filepath in sorted(dated_files):
        if header_matches(filepath):
            return filepath

    # 3. If the dated filename does not exist yet, use it
    if not os.path.isfile(dated_filepath):
        return dated_filepath

    # 4. Otherwise, create a new time-stamped filename
    while True:
        current_time = datetime.today().strftime("%H%M%S")

        filepath = os.path.join(
            directory,
            f"{stem}_{today}_{current_time}{ext}",
        )

        if not os.path.isfile(filepath):
            return filepath

        # Extremely unlikely, but ensure HHMMSS changes before retrying
        time.sleep(1)

def apply(df, config_dict, verbose=True, indent='', store_stats=True, outputdir_marinedb='./', outputfile_marinedb=DEFAULT_OUTPUTFILE, partition=None):

    if len(os.path.dirname(outputfile_marinedb)) == 0:
        outputfile_marinedb = os.path.join(outputdir_marinedb, outputfile_marinedb)

    header = []
    stats = []
    if partition is not None:
        header += ['partition_number']
        stats += [partition]
    header += ['init']
    stats += [len(df)]

    count = 1
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

            length_before = len(df)

            if colname == 'tool':

                colnames = [value for key, value in proc_params.items() if 'key' in key]
                if len(colnames) != 0:
                    printv(f'* {", ".join(colnames)}', verbose=verbose, indent=indent)
                    procstep_string = f'{"-".join(colnames)}'
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
            printv(f'{proc_name} | before: {length_before}, after: {length_after} ({length_after - length_before})', verbose=verbose, indent=indent + '   ')

            if store_stats:
                header += [f'STEP_{count:03}_{procstep_string}_before', f'STEP_{count:03}_{procstep_string}_after']
                stats += [length_before, length_after]

            columns_after = set(df.columns)
            new_columns = columns_after - columns_before
            if len(new_columns) != 0:

                printv(f'{proc_name} | new column(s): {list(new_columns)}', verbose=verbose, indent=indent + '   ')

            printv('', verbose=verbose, indent=indent)

            count += 1

    if store_stats:

        stats = pd.DataFrame([stats], columns=header, dtype=int)

        outputfile_marinedb = resolve_outputfile(outputfile_marinedb, stats, sep='\t')

        if os.path.isfile(outputfile_marinedb):
            stats.to_csv(outputfile_marinedb, sep='\t', index=False, header=False, mode='a')
        else:
            stats.to_csv(outputfile_marinedb, sep='\t', index=False)

    return df

