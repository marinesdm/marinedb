
def apply(df, key, values, flag=False):

    if isinstance(values, str):
        values = [values]

    searchfor = ''.join([f'(?=.*{value})' for value in values])
    keep = df[key].str.contains(rf'{searchfor}')

    if flag:

        if key=="issue":
            with open('../gbif_issues.json','r') as issues_file:
                issues_dict = json.load(issues_file)
            value_str = '-'.join([str(issues_dict[key]["id"]) for key in values])

        else:
            value_str = '-'.join(values)

        df[f'flag_{key}_contains_{value_str}'] = (~keep)

        return df

    else:

        return df[keep].reset_index(drop=True)
