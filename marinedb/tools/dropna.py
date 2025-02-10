import pandas as pd

def apply(df, key, flag=False):

    if flag:
        df[f'flag_{key}_dropna'] = pd.isna(df[key])
        return df
    else:
        return df[~pd.isna(df[key])].reset_index(drop=True)
