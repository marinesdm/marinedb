
def apply(df, key, values, flag=False):

    if isinstance(values, str):
        values = [values]

    delete = df[key].isin(values)

    if flag:
        values_str = '-'.join(values)
        df[f'flag_{key}_notisin_{values_str}'] = delete
        return df
    else:
        return df[~delete].reset_index(drop=True)
