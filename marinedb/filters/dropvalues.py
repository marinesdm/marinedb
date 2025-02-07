import pandas as pd
import re


def boolean(value):

    if isinstance(value,str):
        if value in ['True','False']:
            value=(value=='True')
        else:
            raise ValueError(f'`value` must be True or False, but `value`={value}')

    else:
        value=bool(value)

    return value


TYPE_CONVERSION = {
                    'int':int,
                    'float':float,
                    'bool':boolean,
                    'string':str
                  }


def apply(df, **conditions):

    OR_condition = None

    for key, value in conditions.items():
        print('key,value:',key,value)

        # Ensure the objects compared are of the same type

        dtype = str(df[key].dtypes)

        if dtype=='object':
            df[key]=df[key].convert_dtypes()
            dtype = str(df[key].dtypes)

        try:
            astype = TYPE_CONVERSION[re.match(r'int|float|bool',dtype.lower()).group()]
            column_dtype = dtype
        except AttributeError:
            astype = TYPE_CONVERSION['string']
            column_dtype = 'string'

        df[key]=df[key].astype(column_dtype)

        if isinstance(value,tuple):
            value = list(value)
        if not isinstance(value, list):
            value = [value]

        value = [astype(v) for v in value]
        print('value:',value)
        print('df dtype:',df[key].dtypes)
        print('dtype:',dtype)
        # Filtering conditions

        condition = ((~pd.isnull(df[key])) & (df[key].isin(value)))

        if OR_condition is None:
            OR_condition = condition
        else:
            OR_condition = (OR_condition | condition)

        df[key] = df[key].astype(dtype)
        print('df dtype:', df[key].dtypes)
    df = df[~OR_condition].reset_index(drop=True)

    return df
