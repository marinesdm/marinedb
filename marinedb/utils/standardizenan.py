import numpy as np
import pandas as pd
import re

STR_NAN_VALUES = ["-1.#IND",
                  "1.#QNAN",
                  "1.#IND",
                  "-1.#QNAN",
                  "#N/A N/A",
                  "#N/A",
                  "#n/a",
                  "N/A",
                  "n/a",
                  "NA",
                  "<NA>",
                  "#NA",
                  "NULL",
                  "null",
                  "NaN",
                  "-NaN",
                  "nan",
                  "-nan",
                  "",
                  "None"]

def isnan(value, nan_values=None, letters_only=False):

    try:
        if pd.isnull(float(value)): #NaN, nan, 'nan', 'NaN' ...
            return True
    except (ValueError,TypeError):
        if pd.isnull(value): #NaT
            return True

    if nan_values is None:
        nan_values=[]
    elif isinstance(nan_values,str):
        nan_values=[nan_values]
    nan_values = list(set(nan_values + STR_NAN_VALUES))

    if str(value) in nan_values:
        return True

    if letters_only:
        pattern=r'[a-zA-Z]'
    else:
        pattern=r'[a-zA-Z0-9]'

    if not re.search(pattern,str(value)):
        return True

    return False

def apply(df, key=None, nan_values=None, letters_only=False):

    visnan = np.vectorize(isnan)

    if key is None:

        # Convert all missing values in the dataset to pd.NA
        df = pd.DataFrame(np.where(visnan(df, nan_values=nan_values, letters_only=letters_only), pd.NA, df),columns=df.columns)

    elif len(key)==0: # empty list or ''

        return df

    else:
        # Convert all missing values in `key` columns to pd.NA
        df[key]=np.where(visnan(df[key], nan_values=nan_values, letters_only=letters_only), pd.NA, df[key])

    return df
