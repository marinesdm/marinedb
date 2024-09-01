import numpy as np
import pandas as pd

def isnan(value, nan_encoding=[]):

    if str(value)=='':
        return True
    if len(nan_encoding)!=0:
        if (str(value) in nan_encoding):
            return True
    try:
        return pd.isnull(float(value)) #NaN, nan, 'nan', 'NaN' ...
    except (ValueError,TypeError):
        return pd.isnull(value) #NaT

def apply(df, key=None, nan_encoding=[]):

    visnan = np.vectorize(isnan)

    if key is None:
        # Convert all missing value in the dataset to pd.NA
        df = pd.DataFrame(np.where(visnan(df,nan_encoding=nan_encoding), pd.NA, df),columns=df.columns)
    else:
        df[key]=np.where(visnan(df[key], nan_encoding=nan_encoding), pd.NA, df[key])

    return df
