#!/usr/bin/python
# coding: utf-8

# Internal import

from marinedb.utils.allexport import export
from marinedb.tools.temporal import parsedate
from marinedb.tools.temporal import splitdate

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, format=None, inplace=False, flag=True, stdnan=True, parallel=False, cpu=None, drop_interval=False, strategy='overlap', maxinterval_number=1, maxinterval_level='years', split='all', drop_mismatch=True, indent=''):

    params = {
              'yearkey' : yearkey,
              'monthkey' : monthkey,
              'daykey' : daykey,
              'drop_empty' : False,
              'indent': indent
             }

    # Parse raw date strings

    params_parsedate = {
                        'format' : format,
                        'inplace' : inplace,
                        'stdnan' : stdnan,
                        'parallel' : parallel,
                        'cpu' : cpu
                       }

    df = parsedate.apply(df, datekey, **params, **params_parsedate)

    # Process date intervals

    params_processdateinterval = {
                                  'drop_interval' : drop_interval,
                                  'strategy' : strategy,
                                  'maxinterval_number' : maxinterval_number,
                                  'maxinterval_level' : maxinterval_level,
                                 }

    # Split date into year, month, and day

    params_splitdate = {
                        'split' : split,
                        'drop_mismatch' : drop_mismatch,
                        'flag' : flag,
                        'inplace' : inplace
                       }

    df = splitdate.apply(df, datekey, **params, **params_processdateinterval, **params_splitdate)

    return df
