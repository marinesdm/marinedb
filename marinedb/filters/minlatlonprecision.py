import filters.minfloatprecision as mfp
import numpy as np

def apply(df, keylat, keylon, value, flag=False):

    print(f'            * minlatlonprecision | minfloatprecision for {keylat}')
    df = mfp.apply(df, keylat, value, flag=True)
    print(f'            * minlatlonprecision | minfloatprecision for {keylon}')
    df = mfp.apply(df, keylon, value, flag=True)
    flagcolumns = [f'flag_{keylat}_minfloatprecision_{str(value)}', f'flag_{keylon}_minfloatprecision_{str(value)}']
    precisioncolumns = [f'{keylat}_precision',f'{keylon}_precision']

    doescontain_necessarycolumns = set(flagcolumns+precisioncolumns) - set(df.columns)
    if len(doescontain_necessarycolumns)!=0:
        raise Exception(f'Running minfloatprecision for latitude and longitude should produce 4 columns.')

    flagname = f'flag_minlatlonprecision_{str(value)}'
    df[flagname] = df[flagcolumns[0]] * df[flagcolumns[1]] #latitude AND longitude below a threshold of `value` decimals

    dropcolumns = flagcolumns + precisioncolumns

    if flag:
        df['latlon_precision'] = df[precisioncolumns].max(axis=1).astype('Int64')
        df.drop(columns=dropcolumns, inplace=True)
        return df
    else:
        df = df[~df[flagname]].reset_index(drop=True)
        df.drop(columns=dropcolumns+[flagname], inplace=True)
        return df
