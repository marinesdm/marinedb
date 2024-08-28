
# Local imports
from . import isin
from . import notisin
from . import contains
from . import doesnotcontain
from . import isboundedby
from . import lettersonly
from . import isinworms
from . import dropna
from . import minfloatprecision

def filter(df, config_dict):

    for colfilters in config_dict:

        colname = list(colfilters.keys())[0]

        print(f'        ** {colname}')
        for filter in colfilters[colname]:

            columns_before = set(df.columns)

            if isinstance(filter, dict):
                filter_name = list(filter.keys())[0]
                filter_params = filter[filter_name]
            else:
                filter_name = filter
                filter_params = {}

            length_before=len(df)

            if colname=='filter':
                df = eval(f"{filter_name}.apply(df, **filter_params)")
            else:
                df = eval(f"{filter_name}.apply(df, colname, **filter_params)")

            print(f'            {filter_name} | before: {length_before}, after: {len(df)}')

            columns_after = set(df.columns)
            new_columns = columns_after - columns_before
            if len(new_columns)!=0:
                print(f'            {filter_name} | new columns: {list(new_columns)}')

    return df
