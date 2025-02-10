import numpy as np
import pandas as pd

def get_floatprecision(series_flt):

    series_flt = series_flt.str.strip()
    series_flt = series_flt.str.split(pat='.')
    precision = np.where(series_flt.str.len().eq(1) | series_flt.str[1].eq(''), 0, series_flt.str[1].str.len())

    return pd.Series(precision)


def apply(df, key, value, latlon=False, flag=False):

    if not isinstance(value,int):
        raise ValueError('`minfloatprecision.py` | `value` must be an integer')

    print(f'            * minfloatprecision | count the number of decimals')
    colname = f'{key}_precision'
    if colname in df.columns:
        print(f'              {colname} column already exists and will be used')
    else:
        df[colname] = get_floatprecision(df[key].astype('string')).astype('Int64')

    print(f'            * minfloatprecision | filter and/or flag')
    if (not latlon) and flag:
        df[f'flag_{key}_minfloatprecision_{str(value)}'] = df[colname]<value
        return df

    elif latlon:
        df[f'flag_{key}_minfloatprecision_latlon_{str(value)}'] = df[colname]<value
        regex = fr'^flag_.+_minfloatprecision_latlon_{str(value)}$'
        latlon_columns = df.columns[df.columns.str.contains(regex)]

        if len(latlon_columns)<2:
            return df

        elif len(latlon_columns)==2:
            flag_latlon = f'flag_minfloatprecision_latlon_{str(value)}'
            df[flag_latlon] = df[latlon_columns[0]] * df[latlon_columns[1]]
            if flag:
                df.drop(columns=latlon_columns, inplace=True)
                return df
            else:
                df = df[~df[flag_latlon]].reset_index(drop=True)
                df.drop(columns=df.columns[df.columns.str.contains(fr'latlon_{str(value)}$')], inplace=True)
                return df

        else:
            raise Exception(f'There should be no more than two columns `flag_..._minfloatprecision_latlon_{str(value)}` (latitude & longitude)')

    else:
        return df[df[colname]>=value].reset_index(drop=True)
