

COLNAMES = {
            'species':'species',
            'genus':'genus',
            'family':'family',
            'order':'order',
            'class':'class',
            'phylum':'phylum',
            'kingdom':'kingdom',
            'other':'gbifID'
           }

def lowerbound_subset(df, limit=50, colnames=COLNAMES, flag=False):

    columns = [COLNAMES['species'],COLNAMES['genus'],COLNAMES['family'],COLNAMES['order'],COLNAMES['class'],COLNAMES['phylum'],COLNAMES['kingdom']]
    uniqueSpecies = df[columns + [COLNAMES['other']]].fillna('unk').groupby(columns) #fillna: get_group() doesn't work with NaN
    countBySpecies = uniqueSpecies.count().reset_index().rename(columns={COLNAMES['other']:'count'})
    species2keep = countBySpecies[countBySpecies['count']>=limit].reset_index(drop=True)

    observations2keep = []
    for idx in range(len(species2keep)):
        indexes = uniqueSpecies.get_group(tuple(species2keep.loc[idx, columns])).index
        observations2keep += list(indexes)

    if flag:
        flagname = f'flag_subset_lowerbound_{limit}'
        df[flagname] = True
        df.loc[observations2keep,flagname] = False
        return df

    else:
        return df.loc[observations2keep,:]


def upperbound_subset(df, limit=-1, flag=False): #TODO
    return df

def apply(df, lowerbound=-1, upperbound=-1, flag=False, seed=None):

    if (upperbound==-1) and (lowerbound==-1):
        return df

    if lowerbound > 0:
        df = lowerbound_subset(df, limit=lowerbound, flag=flag)

    if upperbound > 0:
        df = upperbound_subset(df, limit=upperbound, flag=flag, seed=seed)

    return df

