import filters.minfloatprecision as mfp
import numpy as np

def apply(df, keylat, keylon, value, flag=False):

    oldcolumns = set(df.columns)
    df = mfp.apply(df, keylat, value, flag=True)
    df = mfp.apply(df, keylon, value, flag=True)
    newcolumns = set(df.columns) - oldcolumns
    if len(newcolumns)!=4:
        raise Exception(f'There should be no more than four columns (2*latitude & 2*longitude)')
    flag_newcolumns = [col for col in newcolumns if 'flag' in col]
    precision_newcolumns = list(newcolumns - set(flag_newcolumns))

    flagname = f'flag_minlatlonprecision_{str(value)}'
    df[flagname] = df[flag_newcolumns[0]] * df[flag_newcolumns[1]] #latitude AND longitude below a threshold of `value` decimals

    if flag:
        df['latlon_precision'] = df[precision_newcolumns].max(axis=1).astype('Int64')
        df.drop(columns=new_columns, inplace=True)
        return df
    else:
        df = df[~df[flagname]].reset_index(drop=True)
        df.drop(columns = new_columns + [flagname], inplace=True)
        return df
