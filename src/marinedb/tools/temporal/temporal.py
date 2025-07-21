#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname
from marinedb.tools.temporal import parsedate
from marinedb.tools.temporal import splitdate

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, format=None, inplace=False, stdnan=True, parallel=False, cpu=None,  flag_interval=True, drop_interval=False, strategy_interval='overlap', maxinterval_number=1, maxinterval_level='years', split_date='all', drop_mismatch_split=True, dropna_date=False, verbose=True, indent=''):

    params = {
              'yearkey' : yearkey,
              'monthkey' : monthkey,
              'daykey' : daykey,
              'drop_empty' : False,
              'verbose': verbose,
              'indent': indent + '   '
             }

    printv('', verbose=verbose)
    printv('** parsedate', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    # Parse raw date strings

    params_parsedate = {
                        'format' : format,
                        'inplace' : inplace,
                        'stdnan' : stdnan,
                        'parallel' : parallel,
                        'cpu' : cpu
                       }

    df = parsedate.apply(df, datekey, **params, **params_parsedate)

    printv('** splitdate', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    # Process date intervals

    params_processdateinterval = {
                                  'drop_interval' : drop_interval,
                                  'strategy' : strategy_interval,
                                  'maxinterval_number' : maxinterval_number,
                                  'maxinterval_level' : maxinterval_level,
                                 }

    # Split date into year, month, and day

    params_splitdate = {
                        'split' : split_date,
                        'drop_mismatch' : drop_mismatch_split,
                        'flag' : flag_interval,
                        'inplace' : inplace
                       }

    df = splitdate.apply(df, datekey, **params, **params_processdateinterval, **params_splitdate)

    # Drop rows with missing values in the `datekey` column

    if dropna_date:

        df, datekeyout, _ = getcolumnname.apply(df, datekey, '', inplace=True)
        ismissing = pd.isnull(df[datekeyout])
        df = df[~ismissing].reset_index(drop=True)

    return df
