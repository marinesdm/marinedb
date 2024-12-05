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


def isnan(value, nan_values=None):

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
    nan_values+=STR_NAN_VALUES
    if str(value) in nan_values:
        return True

    if not re.search(r'[a-zA-Z0-9]',str(value)):
        return True

    return False

def apply(df, key=None, nan_encoding=[]):

    visnan = np.vectorize(isnan)

    if key is None:

        # Convert all missing value in the dataset to pd.NA
        df = pd.DataFrame(np.where(visnan(df,nan_encoding=nan_encoding), pd.NA, df),columns=df.columns)

    else:
        df[key]=np.where(visnan(df[key], nan_encoding=nan_encoding), pd.NA, df[key])

    return df
