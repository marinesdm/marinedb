import numpy as np
import pandas as pd

def get_floatprecision(series_flt):

    series_flt = series_flt.str.strip()
    series_flt = series_flt.str.split(pat='.')
    precision = np.where(series_flt.str.len().eq(1) | series_flt.str[1].eq(''), 0, series_flt.str[1].str.len())

    return pd.Series(precision)


def apply(df, key, value, flag=False):

    if not isinstance(value,int):
        raise ValueError('`minfloatprecision.py` | `value` must be an integer')

    print(f'            * minfloatprecision | count the number of decimals')

    tempcol = f'{key}_precision'
    if tempcol in df.columns:
        print(f'              {tempcol} column already exists and will be used')
    else:
        df[tempcol] = get_floatprecision(df[key].astype('string')).astype('Int64')

    print(f'            * minfloatprecision | filter and/or flag')

    if flag:
        df[f'flag_{key}_minfloatprecision_{str(value)}'] = df[tempcol]<value
        return df
    else:
        df = df[df[tempcol]>=value].reset_index(drop=True)
        df.drop(columns=[tempcol], inplace=True)
        return df
