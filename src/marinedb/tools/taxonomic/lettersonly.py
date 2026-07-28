#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
from unidecode import unidecode

# Internal import

from marinedb.utils.allexport import export
from marinedb.tools import getcolumnname

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, flag=False, dropna=False, verbose=True, indent=''):
    """Evaluate taxon names for unsupported characters.

    Identifies values in a user-specified taxonomic column that contain
    characters other than letters, spaces, or hyphens. Accented characters
    are transliterated before evaluation, so names such as `Terpsinoë` 
    are treated as alphabetic.

    This simple character-based filter is mainly intended for workflows in
    which full taxonomic harmonization is not performed. It captures many
    non-canonical molecular, strain, and environmental-sequence identifiers
    containing digits, underscores, or other symbols, but may also identify
    legitimate taxonomic values.

    !!! info

        - When ``flag=True``, records containing only letters, spaces, or hyphens are flagged.

        - When ``flag=False``, records containing unsupported characters are excluded.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        key (str):
            Name of the taxonomic column to evaluate.

        flag (bool, optional):
            Whether to add a Boolean flag instead of removing records.
            
            When `True`, all records are retained and the generated 
            `flag_<key>_lettersonly` column is `True` when the value 
            contains only letters, spaces, or hyphens, `False` when 
            unsupported characters are present, and missing when the
            evaluated value is missing. 

            When `False`, records containing unsupported characters
            are removed.

        dropna (bool, optional):
            Whether to remove records with missing values in `key` when
            `flag=False`. Missing values are retained when `False`.

    Returns:
        (pandas.DataFrame):
            Processed DataFrame. When `flag=True`, the input records are
            retained and a Boolean flag column is added. Otherwise, records
            containing unsupported characters are removed, together with
            missing values when `dropna=True`.

    Notes:
        The character check is intentionally broad and should not be
        interpreted as taxonomic validation. It should preferably be applied
        only to columns whose values are already known to be relatively
        standardized. Legitimate values containing numbers or punctuation may 
        be identified as non-compliant or removed. Examples include bacterial 
        classes such as `CG2-30-54-11`, viral names such as 
        `Pilayella littoralis virus 1`, and non-standardized scientific names 
        containing authorship dates.

        For general taxonomic cleaning, the recommended approach is to use
        `createwormsfilters`, `isinworms`, and, when needed,
        `resolvetaxamatch`.
    """

    df, key, _ = getcolumnname.apply(df, key, '', inplace=True)

    df[key] = df[key].astype('string')

    # Flag or exclude rank names containing non-letter characters
    # e.g., GWE2-31-10, UBA1177, and JACPGU01 classes (typically DNA-derived observations, or microbial groups)
    # Note: some edge cases may be incorrectly flagged or excluded,
    # e.g., "Hexabothrium (incertae sedis)" (aphiaID=719046)
    # e.g., "[non-Uristidae]" (aphiaID=875566) genera

    pattern=r'[^a-zA-Z\s\-]'
    tempkey = 'TEMPORARYLETTERSONLY_{key}'
    df[tempkey] = df[key]
    ismissing = pd.isnull(df[key])
    df.loc[~ismissing, tempkey] = df.loc[~ismissing, tempkey].apply(unidecode) # e.g., "Terpsinoë" and "Naïs" genera
    islettersonly = (~df[tempkey].str.contains(pattern, na=False))
    islettersonly = islettersonly.astype('boolean')
    islettersonly[ismissing] = pd.NA

    df.drop(columns=[tempkey], inplace=True)

    if flag:
        # Flag rows where the `key` column contains only letters
        df[f'flag_{key}_lettersonly'] = islettersonly
        return df
    else:
        # Drop rows:
        #   - where `key` contains non-letter characters
        #   - with missing values in `key` if `dropna`
        islettersonly[ismissing] = (not dropna)
        return df[islettersonly].reset_index(drop=True)
