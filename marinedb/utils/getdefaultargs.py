import inspect

def apply(func):

    signature = inspect.signature(func)

    default_args = {k : v.default for k,v in signature.parameters.items() if v.default is not inspect.Parameter.empty}

    return default_args
