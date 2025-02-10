def valueisin(feature, values):
    for value in values:
        if value in feature:
            return True 
    return False 

def featurenotisin(df, key, values):
    return df[~df[key].isin(values)].reset_index(drop=True)

def apply(df, key, values, value2feature=False):
    if value2feature:
        index2keep=[]
        for idx, feature in enumerate(df[key].values):
            if not valueisin(feature, values):
                index2keep.append(idx)
        return df.iloc[index2keep,:].reset_index(drop=True)
    else: 
        return featurenotisin(df, key, values)
