
def apply(df, **conditions):

    OR_condition = None

    for key, value in conditions.items():

        if isinstance(value, list | tuple): #python >= 3.10
            condition = df[key].isin(value)
        else:
            condition = (df[key] == value)

        if OR_condition is None:
            OR_condition = condition
        else:
            OR_condition = (OR_condition | condition)

    df = df[~OR_condition].reset_index(drop=True)

    return df
