import json

def apply(df, key, values, flag=False):

    if isinstance(values, str):
        values = [values]

    searchfor = '|'.join(values)
    delete = df[key].str.contains(rf'{searchfor}')

    if flag:

        if key=="issue":
            with open('filters/gbif_issues.json','r') as issues_file:
                issues_dict = json.load(issues_file)
            value_str = '-'.join([str(issues_dict[key]["id"]) for key in values])

        else:
            value_str = '-'.join(values)

        df[f'flag_{key}_doesnotcontain_{value_str}'] = delete

        return df

    else:

        return df[~delete].reset_index(drop=True)
