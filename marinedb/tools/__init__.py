
# Local imports

from . import *

def apply(df, config_dict):

    for procstep in config_dict:

        colname = list(procstep.keys())[0]

        print(f'    * {colname}')
        for proc in procstep[colname]:

            columns_before = set(df.columns)

            if isinstance(proc, dict):
                proc_name = list(proc.keys())[0]
                proc_params = proc[proc_name]
            else:
                proc_name = proc
                proc_params = {}

            length_before=len(df)

            if colname=='tool':
                df = eval(f"{proc_name}.apply(df, **proc_params)")
            else:
                df = eval(f"{proc_name}.apply(df, colname, **proc_params)")

            print(f'        {proc_name} | before: {length_before}, after: {len(df)}')

            columns_after = set(df.columns)
            new_columns = columns_after - columns_before
            if len(new_columns)!=0:
                print(f'        {proc_name} | new columns: {list(new_columns)}')

    return df
