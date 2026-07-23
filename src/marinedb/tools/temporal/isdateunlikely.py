#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd
from datetime import datetime

# Internal import

from marinedb.tools import isboundedby
from marinedb.tools import getcolumnname

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variable

__all__ = [] # populated using the @export decorator

YEAR_NOW = datetime.now().year

@export
def apply(df, datekey=None, yearkey=None, year_min=1700, year_max=YEAR_NOW, flag=False, dropna=False, verbose=True, indent=''):
    """Detect or exclude occurrence dates outside an expected year range.

    Evaluate either a standardized date column or a separate year column against
    user-defined minimum and maximum years. Dates whose year falls outside this
    range are treated as unlikely.

    When both ``datekey`` and ``yearkey`` are provided, validation is performed
    from ``yearkey`` and ``datekey`` is ignored.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        datekey (str, optional):
            Name of the column containing dates to evaluate.

            Non-missing values must follow one of the forms ``YYYY``, ``YYYY-MM``,
            or ``YYYY-MM-DD``.

        yearkey (str, optional):
            Name of the column containing year values to evaluate.

            Non-missing values must follow the ``YYYY`` format.

        year_min (int, optional):
            Minimum year considered plausible.

        year_max (int, optional):
            Maximum year considered plausible.

        flag (bool, optional):
            Whether to annotate or exclude unlikely records.

            If ``True``, all records are retained and a Boolean flag column is
            created. If ``False``, records outside the selected year range are
            removed.

        dropna (bool, optional):
            Whether to treat missing dates or years as unlikely.

    Returns:
        (pandas.DataFrame):
            Processed DataFrame with unlikely records flagged or excluded.

    Raises:
        ValueError:
            If neither ``datekey`` nor ``yearkey`` is provided.

        ValueError:
            If non-missing values in ``datekey`` do not follow the expected date
            format.

        ValueError:
            If non-missing values in ``yearkey`` do not follow the expected year
            format.

    Note:
        - The selected interval is inclusive: years equal to ``year_min`` or
        ``year_max`` are considered plausible.

        - When ``flag=True``, the generated column is named
        ``flag_<DATE_COLUMN>_isdateunlikely_<YEAR_MIN>-<YEAR_MAX>`` when validating
        ``datekey``, or
        ``flag_<YEAR_COLUMN>_isdateunlikely_<YEAR_MIN>-<YEAR_MAX>`` when validating
        ``yearkey``.

        - Invalid formats interrupt processing. The error message recommends applying
        the temporal curation workflow upstream to standardize and validate temporal
        values before evaluating whether dates are unlikely.
    """

    if (datekey is None) and (yearkey is None):
        raise ValueError(f'`isdateunlikely.py` | Either `datekey` or `yearkey` must be specified')
    if (datekey is not None) and (yearkey is not None):
        printv(f"INFO | Since `yearkey` is provided ('{yearkey}'), `datekey` will be ignored ('{datekey}')", verbose=verbose, indent=indent)
        datekey = None

    tempcol = []

    if datekey is not None:

        df, datekey, _ = getcolumnname.apply(df, datekey, '', inplace=True)

        ismissing = pd.isnull(df[datekey])
        isformatvalid = df.loc[~ismissing, datekey].str.fullmatch(r'[0-9]{4}(-[0-9]{2}){0,2}').astype('bool')
        if (~isformatvalid).any():
            example = df.loc[(~ismissing) & (~isformatvalid), datekey].iloc[0]
            raise ValueError(f"`isdateunlikely.py` | Invalid date formats found (e.g., '{example}'). Dates must follow the format: YYYY or YYYY-MM or YYYY-MM-DD. Please run `temporal.py`, `parsedate.py` or `isdateinvalid.py` (with flag=False) first.")

        yearkey = 'TEMPORARYYEAR'
        tempcol.append(yearkey)
        df[yearkey] = df[datekey].str.split('-').str[0].astype('Float64').astype('Int64')

    else:

        df, yearkey, _ = getcolumnname.apply(df, yearkey, '', inplace=True)

        ismissing = pd.isnull(df[yearkey])
        isformatvalid = df.loc[~ismissing, yearkey].astype('str').str.fullmatch(r'[0-9]{4}(\.0*)?').astype('bool')
        if (~isformatvalid).any():
            example = df.loc[(~ismissing) & (~isformatvalid), yearkey].iloc[0]
            raise ValueError(f"`isdateunlikely.py` | Invalid year formats found (e.g., '{example}'). Years must follow the format YYYY. Please run `temporal.py`, `convertdatetype.py` or `isdateinvalid.py` (with flag=False) first.")

    params = {
              'flag': flag,
              'dropna': dropna,
              'verbose': verbose,
              'indent': indent
              }

    columns_before = set(df.columns)
    df = isboundedby.apply(df, yearkey, operator='>=', value=year_min, **params)
    df = isboundedby.apply(df, yearkey, operator='<=', value=year_max, **params)
    columns_isboundedby = list(set(df.columns) - columns_before)
    tempcol += columns_isboundedby

    if flag:
        assert len(columns_isboundedby) == 2
        if datekey is not None:
            flagname = f'flag_{datekey}_isdateunlikely_{year_min}-{year_max}'
        else:
            flagname = f'flag_{yearkey}_isdateunlikely_{year_min}-{year_max}'
        ismissing = pd.isnull(df[yearkey])

        df.loc[~ismissing, flagname] = (df.loc[~ismissing, columns_isboundedby].sum(axis=1) != len(columns_isboundedby))
        df[flagname] = df[flagname].astype('boolean')

    df.drop(columns=tempcol, inplace=True)

    return df
