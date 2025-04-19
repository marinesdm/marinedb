#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, issuekey, issuemsg, subset=None):

    if (issuekey not in df.columns):
        df[issuekey] = pd.NA

    if (subset is None):
        subset = list(df.index)

    df.loc[subset, issuekey] = df.loc[subset, issuekey].fillna('') + f';{issuemsg}'
    df.loc[subset, issuekey] = df.loc[subset, issuekey].str.strip(' ;')
    df[issuekey] = df[issuekey].astype('string')

    return df
