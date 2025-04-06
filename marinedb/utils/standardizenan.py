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
        nan_values = []
    elif isinstance(nan_values,str):
        nan_values = [nan_values]
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

def standardizenan_elementwise(df, key=None, nan_values=None, letters_only=False):

    visnan = np.vectorize(isnan)

    if key is None:

        # Convert all missing values in the dataset to pd.NA
        df = pd.DataFrame(np.where(visnan(df, nan_values=nan_values, letters_only=letters_only), pd.NA, df),columns=df.columns)

    elif len(key) == 0: # empty list or ''
        return df

    else:
        # Convert all missing values in `key` columns to pd.NA
        df[key]=np.where(visnan(df[key], nan_values=nan_values, letters_only=letters_only), pd.NA, df[key])

    return df

def standardizenan_vectorized(df, key=None, nan_values=None, letters_only=False): #finalement plus long que elementwise ...

    if key is None:
        key = list(df.columns)
    if len(key) == 0:
        return df
    if isinstance(key,str):
        key = [key]

    temp = df[key].copy()
    temp[key] = temp[key].astype('float', errors='ignore').astype('Float64', errors='ignore') #useless? if yes, no need for temp then

    if nan_values is None:
        nan_values = []
    if isinstance(nan_values,str):
        nan_values = [nan_values]
    nan_values = list(set(nan_values + STR_NAN_VALUES))

    pattern_nan = [re.escape(val.lower()) for val in nan_values if len(val) > 0]
    pattern_nan = list(set(pattern_nan))
    pattern_nan = fr"{'|'.join(pattern_nan)}"

    if letters_only:
        pattern_alphanum = r'[a-zA-Z]'
    else:
        pattern_alphanum = r'[a-zA-Z0-9]'

    for k in key:
        ismissing1 = (temp[k].astype('string').str.len() == 0) # ''
        ismissing2 = temp[k].astype('string').str.fullmatch(pattern_nan, case=False)
        ismissing3 = (~temp[k].astype('string').str.contains(pattern_alphanum))
        temp.loc[ismissing1 | ismissing2 | ismissing3, k] = pd.NA
        df.loc[pd.isnull(temp[k]), k] = pd.NA

    return df

def standardizenan_vectorized_v2(df, key=None, nan_values=None, letters_only=False): #finalement plus long que elementwise ...

    if key is None:
        key = list(df.columns)
    if len(key) == 0:
        return df
    if isinstance(key,str):
        key = [key]

    if nan_values is None:
        nan_values = []
    if isinstance(nan_values,str):
        nan_values = [nan_values]
    nan_values = list(set(nan_values + STR_NAN_VALUES))

    pattern_nan = [re.escape(val.lower()) for val in nan_values if len(val) > 0]
    pattern_nan = list(set(pattern_nan))
    pattern_nan = fr"{'|'.join(pattern_nan)}"

    if letters_only:
        pattern_alphanum = r'[a-zA-Z]'
    else:
        pattern_alphanum = r'[a-zA-Z0-9]'

    for k in key:
        ismissing1 = (df[k].astype('string').str.len() == 0) # ''
        ismissing2 = df[k].astype('string').str.fullmatch(pattern_nan, case=False)
        ismissing3 = (~df[k].astype('string').str.contains(pattern_alphanum))
        df.loc[ismissing1 | ismissing2 | ismissing3, k] = pd.NA
        df.loc[pd.isnull(df[k]), k] = pd.NA

    return df


def apply(df, key=None, nan_values=None, letters_only=False):

    visnan = np.vectorize(isnan)

    if key is None:

        # Convert all missing values in the dataset to pd.NA
        df = pd.DataFrame(np.where(visnan(df, nan_values=nan_values, letters_only=letters_only), pd.NA, df),columns=df.columns)

    elif len(key) == 0: # empty list or ''

        return df

    else:
        # Convert all missing values in `key` columns to pd.NA
        df[key]=np.where(visnan(df[key], nan_values=nan_values, letters_only=letters_only), pd.NA, df[key])

    return df
