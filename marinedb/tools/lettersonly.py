
def apply(df, key, flag=False):

    pattern=r'[0-9]'
    delete = df[key].str.contains(pattern)

    if flag:
        df[f'flag_{key}_lettersonly'] = delete
        return df
    else:
        return df[~delete]
