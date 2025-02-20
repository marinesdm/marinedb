# coding: utf-8

# External import
import pandas as pd

# Internal import
from marinedb.tools.temporal.convertdatetype import astype_Int64

def parse_year(df, yearkey, drop_ambiguous=False):

    # Convert to integers

    df = astype_Int64(df, yearkey)

    # Ambiguous year string
    # e.g. does "20" represent 1720, 1820, 1920, or 2020?

    if drop_ambiguous:
        isincomplete = (~pd.isnull(df[yearkey])) & (df[yearkey].astype('string').str.len()<4)
        df.loc[isincomplete, yearkey] = pd.NA

    return df

def parse_month(df, monthkey):

    # Convert to integers

    df = astype_Int64(df, monthkey)

    return df

def parse_day(df, daykey):

    # Convert to integers

    df = astype_Int64(df, daykey)

    return df

