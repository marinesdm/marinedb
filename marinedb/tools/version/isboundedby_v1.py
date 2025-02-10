
def apply(df, key, operator, value):

    if '<' in operator:
        if '=' in operator:
            df = df[df[key]<=float(value)]
        else:
            df = df[df[key]<float(value)]
    elif '>' in operator:
        if '=' in operator:
            df = df[df[key]>=float(value)]
        else:
            df = df[df[key]>float(value)]
    else:
        raise ValueError('`isboundedby.py` | the comparison operator in `value` should be "<", ">", or a combination of "=" and "<" or ">".')

    return df.reset_index(drop=True)
