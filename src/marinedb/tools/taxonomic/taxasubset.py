#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.tools import getcolumnname
from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

def lowerbound_subset(df, taxonkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, limit=50, flag=False, dropna=False, indent=''):

    ispartialclassification = (specieskey is None) or (genuskey is None) or (familykey is None) or (orderkey is None) or (classkey is None) or (phylumkey is None) or (kingdomkey is None)
    istaxonkey = (taxonkey is not None)

    if (not istaxonkey) and ispartialclassification:
        raise Exception(f'`taxasubset.py` | Either the column containing taxon IDs or the columns specifying the taxonomic classification must be provided')

    if istaxonkey and (not ispartialclassification):
        print(indent + f"INFO | Classification keys will be ignored (taxonkey='{taxonkey}')")

    if (not istaxonkey):

        taxonkey = 'taxonkey_taxasubset'
        columns = [specieskey, genuskey, familykey, orderkey, classkey, phylumkey, kingdomkey]
        for i,key in enumerate(columns):
            df, columns[i], _ = getcolumnname.apply(df, key, '', inplace=True)

        df[taxonkey] = 0
        df[columns] = df[columns].astype('string')

        dfg = df.fillna('_MISSING_').groupby(columns)[taxonkey]
        ngroup = iter(range(0, dfg.ngroups))
        df[taxonkey] = dfg.transform(lambda x: next(ngroup)).astype('Int64')
        df.loc[pd.isnull(df[specieskey]) | df[columns[1:]].isnull().all(axis=1), taxonkey] = pd.NA

    else:
        df, taxonkey, _ = getcolumnname.apply(df, taxonkey, '', inplace=True)

    count = df[taxonkey].value_counts()
    isabovelimit = list(count[count >= limit].index)
    isabovelimit = df[taxonkey].isin(isabovelimit).astype('boolean')
    ismissing = pd.isnull(df[taxonkey])
    isabovelimit[ismissing] = pd.NA

    if (not istaxonkey):
        df.drop(columns=taxonkey, inplace=True)

    if flag:

        # Flag rows corresponding to taxa with more than `limit` occurrences in the dataset

        df[f'flag_taxasubset_isabove_{limit}'] = isabovelimit

        return df

    else:

        # Drop rows:
        #   - corresponding to taxa with less than `limit` occurrences in the dataset
        #   - with missing values in `taxonkey` if `dropna`

        isabovelimit[ismissing] = (not dropna)

        return df[isabovelimit]


def upperbound_subset(df, limit=-1, flag=False): #TODO
    return df

@export
def apply(df, lowerbound=-1, upperbound=-1, flag=False, dropna=False, indent='', seed=None,  taxonkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None):

    if (upperbound == -1) and (lowerbound == -1):
        # Do not filter taxa based on their number of occurrences in the dataset
        return df

    if lowerbound > 0:

        # Filter taxa with less than `lowerbound` occurrences in the dataset

        params = {
                  'taxonkey': taxonkey,
                  'specieskey': specieskey,
                  'genuskey': genuskey,
                  'familykey': familykey,
                  'orderkey': orderkey,
                  'classkey': classkey,
                  'phylumkey': phylumkey,
                  'kingdomkey': kingdomkey,
                  'limit': lowerbound,
                  'flag': flag,
                  'dropna': dropna,
                  'indent': indent
                 }

        df = lowerbound_subset(df, **params)

    if upperbound > 0:
        # Limit the number of observations per taxon to `upperbound`
        df = upperbound_subset(df, limit=upperbound, flag=flag, seed=seed)

    return df

