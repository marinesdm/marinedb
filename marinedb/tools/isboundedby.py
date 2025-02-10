operator_mapping = {
                    '>':'SUP',
                    '>=':'SUPEQ',
                    '<':'INF',
                    '<=':'INFEQ'
                    }


def value_mapping(str_value):

    if '-' in str_value:
        return f'NEG{str_value[1:]}'
    else:
        return f'POS{str_value}'


def apply(df, key, operator, value, flag=False):

    if '<' in operator:
        if '=' in operator:
            keep = (df[key].astype('Float64') <= float(value))
        else:
            keep = (df[key].astype('Float64') < float(value))
    elif '>' in operator:
        if '=' in operator:
            keep = (df[key].astype('Float64') >= float(value))
        else:
            keep = (df[key].astype('Float64') > float(value))
    else:
        raise ValueError('`isboundedby.py` | the comparison operator in `value` should be "<", ">", or a combination of "=" and "<" or ">".')

    if flag:
        condition = '-'.join([operator_mapping[operator], value_mapping(str(value))])
        df[f'flag_{key}_isboundedby_{condition}'] = (~keep)
        return df
    else:
        return df[keep].reset_index(drop=True) #delete if NaN
