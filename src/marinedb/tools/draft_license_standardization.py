import pandas as pd

def sort_codes(codes):

    codes = [c for c in codes if (not pd.isnull(c)) and (c != 'CC')]
    if len(codes) == 0:
        return pd.NA
    codes = 'CC ' + '-'.join(sorted(codes))

    return codes

def standardize_license(df, key_in, key_out):

    df = df.copy()

    is_license = (~df[key_in].isna())

    pattern1 = r"https?://creativecommons.org/li[cs]en[cs]es"
    index_cc_licenses = df[is_license & df[key_in].str.contains(pattern1,na=False)].index

    pattern2 = r"https?://creativecommons.org/li[cs]en[cs]es/(?P<code>[a-z-]+)/"
    cc_code = df.loc[index_cc_licenses,key_in].str.extract(pattern2)
    df.loc[index_cc_licenses,key_out] = 'CC ' + cc_code.code.str.upper()

    pattern3 = r"https?://creativecommons.org/publicdomain/zero/1.0"
    df.loc[is_license & df[key_in].str.contains(pattern3,na=False),key_out] = 'CC0'

    pattern4 = r"copyright|no use without permission"
    df.loc[is_license & df[key_in].str.contains(pattern4,case=False,na=False),key_out] = 'COPYRIGHT'

    is_processed = (~df[key_out].isna())

    pattern5 = r"[^a-zA-Z]"
    pattern6 = r"https?://"
    index_cc_licenses = df[is_license & (~is_processed) & (~df[key_in].str.contains(pattern6))].index
    cc_code = df.loc[index_cc_licenses,key_in].str.replace(pattern5, repl=" ", regex=True)
    cc_code = cc_code.str.replace(r"\s+", repl=" ", regex=True)
    pattern7 = r"(?P<code1>CC)\s?(?P<code2>BY)\s?(?P<code3>NC|ND|SA)?\s?(?P<code4>NC|ND|SA)?\s?(?P<code5>NC|ND|SA)?"
    cc_code = cc_code.str.upper().str.extract(pattern7)
    cc_code['code'] = cc_code.to_numpy().tolist()
    cc_code['code'] = cc_code['code'].apply(sort_codes)
    df.loc[index_cc_licenses,key_out] = cc_code['code']

    pattern8 = r"CC[ -_]?(?:0|ZERO)"
    df.loc[df[key_in].str.upper().str.contains(pattern8),key_out] = 'CC0'

    cc_by = [
             "http://data.gc.ca/eng/open-government-licence-canada",
             "http://data.gc.ca/eng/open-government-licence-canada & http://www.canadensys.net/norms",
             "Uso citando la fuente"
            ]
    df.loc[df[key_in].isin(cc_by), key_out] = "CC BY"

    cc_by_nc = [
                "Content licensed under Creative Commons Attribution-Non-Comercia 4.0 International License",
                "Sólo para uso no comercial citando la fuente",
                "Sólo para uso no comercial",
                "Solo para uso no comercial",
                "Not-for-profit use only",
                "not-for-profit use only"
               ]
    df.loc[df[key_in].isin(cc_by_nc), key_out] = "CC BY-NC"

    cc_0 = ["The data may be used and redistributed for free but is not intended for legal use, since it may contain inaccuracies. Neither the data Contributor, ERD, NOAA, nor the United States Government, nor any of their employees or contractors, makes any warranty, express or implied, including warranties of merchantability and fitness for a particular purpose, or assumes any legal liability for the accuracy, completeness, or usefulness, of this information."]
    df.loc[df[key_in].isin(cc_0), key_out] = "CC0"

    return df
