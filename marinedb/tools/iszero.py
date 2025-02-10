import numpy as np

def apply(df, key, flag=False, eps=1e-5):

    #eps=1e-5:
        #GBIF: coordinates rounded to 6 decimals
        #5 decimals = ~1m precision at the equator

    if flag:
        df[f'flag_iszero_{key}'] = np.abs(df[key].astype('Float64')) <= eps
        return df

    else:
        return df[np.abs(df[key].astype('Float64')) > eps] #delete if NaN
