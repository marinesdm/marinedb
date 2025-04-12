
def valueisin(df, key, values, flag=False):

    searchfor = ''.join([f'(?=.*{value})' for value in values])
    keep = df[key].str.contains(rf'{searchfor}')

    if flag:
        df[f'flag_{key}_isin'] = (~keep)
    else:
        return df[keep].reset_index(drop=True)

def featureisin(df, key, values, flag=False):

    keep = df[key].isin(values)

    if flag:
        df[f'flag_{key}_isin'] = (~keep)
        return df
    else:
        return df[keep].reset_index(drop=True)

def apply(df, key, values, value2feature=False, flag=False):

    if value2feature:
        return valueisin(df, key, values, flag=flag)
    else:
        return featureisin(df, key, values, flag=flag)
