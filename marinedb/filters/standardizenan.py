import numpy as np

def isnan(value):

    if str(value)=='':
        return True
    try:
        return pd.isnull(float(value)) #NaN, nan, 'nan', 'NaN' ...
    except (ValueError,TypeError):
        return pd.isnull(value) #NaT

def apply(df, key=None):

    visnan = np.vectorize(isnan)

    if key is None:
        # Convert all missing value in the dataset to pd.NA
        df = np.where(visnan(df), pd.NA, df)
    else:
        df[key]=np.where(visnan(df[key]), pd.NA, df[key])

    return df
