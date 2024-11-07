import re

def apply(string, pattern=None):

    if pattern is None:
        # By default, remove leading and trailing whitespace
        pattern = r'^\s+|\s+$'
    elif pattern[0]!='^':
        pattern = fr'^{pattern}|{pattern}$'

    return re.sub(fr'{pattern}','',string)

