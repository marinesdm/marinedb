

def apply(df, key, values, flag=False):

    if isinstance(values,str):
        values = [values]

    keep = df[key].isin(values)

    if flag:
        values_str = '-'.join(values)
        df[f'flag_{key}_isin_{values_str}'] = (~keep)
        return df
    else:
        return df[keep].reset_index(drop=True)
