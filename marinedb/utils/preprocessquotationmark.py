import pandas as pd
from marinedb.utils import regexstrip

def apply(target):

    # Pre-process strings to prevent quotation mark issues in pandas

    if isinstance(target,str):

        target = regexstrip.apply(target, pattern=r'["\s]+')
        target = regexstrip.apply(target, pattern=r"['\s]+")

    elif isinstance(target, list | tuple | pd.Series): #python >= 3.10

        target=pd.Series(target).str.replace('^["\s]+|["\s]+$','',regex=True)
        target=target.str.replace("^['\s]+|['\s]+$",'',regex=True).tolist()

    else:
        raise ValueError(f'Type not recognized: {type(target)}')

    return target
