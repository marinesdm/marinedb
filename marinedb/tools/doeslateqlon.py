import numpy as np

def apply(df, keylat, keylon, flag=False, eps=1e-5):

    #eps=1e-5:
        #GBIF: coordinates rounded to 6 decimals
        #5 decimals = ~1m precision at the equator (less elsewhere)

    if flag:
        df[f'flag_doeslateqlon'] = np.abs(df[keylat].astype('Float64') - df[keylon].astype('Float64')) <= eps
        return df

    else:
        return df[np.abs(df[keylat].astype('Float64') - df[keylon].astype('Float64')) > eps] #delete if lat or lon is NaN


