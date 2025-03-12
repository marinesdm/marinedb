# coding: utf-8

# Internal import

from marinedb.tools.temporal import parsedate
from marinedb.tools.temporal import processdateinterval
from marinedb.tools.temporal import splitdate
#from marinedb.tools import getcolumnname

def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, format=None, inplace=False, flag=True, stdnan=True, parallel=False, cpu=None, drop_interval=False, strategy='overlap', maxinterval_number=1, maxinterval_level='years', split='all', drop_mismatch=True):

    params = {
              'yearkey' : yearkey,
              'monthkey' : monthkey,
              'daykey' : daykey,
             }

    # Parse raw date strings

#    df, datekey = getcolumnname.apply(df, datekey, 'parsedate', inplace)

    params_parsedate = {
                        'format' : format,
                        'inplace' : inplace,
                        'stdnan' : stdnan,
                        'parallel' : parallel,
                        'cpu' : cpu
                       }

    df = parsedate.apply(df, datekey, **params, **params_parsedate)

    # Process date intervals

#    df, datekey = getcolumnname.apply(df, datekey, 'processdateinterval', inplace)

    params_processdateinterval = {
                                  'drop_interval' : drop_interval,
                                  'strategy' : strategy,
                                  'maxinterval_number' : maxinterval_number,
                                  'maxinterval_level' : maxinterval_level,
#                                  'flag' : True,
#                                  'inplace' : inplace
                                 }

#    df = processdateinterval.apply(df, datekey, **params_processdateinterval)

    # Split date into year, month, and day

    params_splitdate = {
                        'split' : split,
#                        'drop_interval' : drop_interval,
                        'drop_mismatch' : drop_mismatch,
                        'drop_empty' : False,
                        'flag' : flag,
                        'inplace' : inplace
                       }

    df = splitdate.apply(df, datekey, **params, **params_processdateinterval, **params_splitdate)
#    df = splitdate.apply(df, datekey, **params, **params_splitdate)

    return df
