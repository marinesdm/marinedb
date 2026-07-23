#!/usr/bin/python
# coding: utf-8

# External import

import pandas as pd

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

from marinedb.tools import getcolumnname
from marinedb.tools.temporal import parsedate
from marinedb.tools.temporal import processdateinterval
from marinedb.tools.temporal import splitdate

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, datekey, yearkey=None, monthkey=None, daykey=None, format=None, stdnan=True, parallel=False, cpu=None,  inplace_parse=False, flag_interval=True, drop_interval=False, inplace_interval=False, strategy_interval='overlap', maxinterval_number=1, maxinterval_level='years', split_date='all', drop_mismatch_split=True, inplace_components_split=False, inplace_date_split=False, dropna_date=False, verbose=True, indent=''):
    """Run the complete temporal data-curation workflow.

    Standardize occurrence dates, process date intervals, and extract year, month,
    and day components while reconciling them with any corresponding component
    columns already present in the input data.

    The workflow successively applies ``parsedate``, ``processdateinterval``, and
    ``splitdate``. Parsing issues, interval-processing issues, and inconsistencies
    between dates and separate temporal components are recorded in their respective
    annotation columns.

    Args:
        df (pandas.DataFrame):
            Input DataFrame.

        datekey (str):
            Name of the column containing the occurrence dates to process.

        yearkey (str, optional):
            Name of a column containing year values.

            When provided, these values may be used to reconstruct missing or
            unparsable dates and are subsequently compared with the corresponding 
            years extracted from the standardized date.

        monthkey (str, optional):
            Name of a column containing month values.

            When provided, these values may be used to reconstruct missing or
            unparsable dates and are subsequently compared with the corresponding 
            months extracted from the standardized date.

            ``yearkey`` must also be provided.

        daykey (str, optional):
            Name of a column containing day values.

            When provided, these values may be used to reconstruct missing or
            unparsable dates and are subsequently compared with the corresponding 
            days extracted from the standardized date.

            Both ``yearkey`` and ``monthkey`` must also be provided.

        parallel (bool, optional):
            Whether to parse dates concurrently using multiple CPUs.

        cpu (int, optional):
            Maximum number of CPUs used for parallel date parsing.

            If ``None`` and ``parallel=True``, all CPUs available to the current
            process are used. This argument is ignored when ``parallel=False``.

        inplace_parse (bool, optional):
            Whether to replace ``datekey`` with the standardized dates produced
            during parsing.

            If ``False``, the standardized dates are written to a new processed
            column.

        flag_interval (bool, optional):
            Whether to retain the date-interval flag and interval-width columns
            generated during interval processing.

        drop_interval (bool, optional):
            Whether to replace date intervals with missing values instead of
            collapsing them.

        inplace_interval (bool, optional):
            Whether to replace the parsed date column with the values produced
            during interval processing.

            If ``False``, interval processing is applied to a new processed date 
            column, allowing the preceding date-column version to be retained.

        strategy_interval (str, optional):
            Strategy used to collapse date intervals. Accepted values are:

            - ``"start"`` to retain the interval start;
            - ``"end"`` to retain the interval end;
            - ``"overlap"`` to retain only the date components shared by both
            interval bounds.

        maxinterval_number (int, optional):
            Maximum interval width allowed with the ``"start"`` and ``"end"``
            strategies.

            Intervals exceeding this limit are replaced with missing values. Use
            ``-1`` to process intervals regardless of their width.

        maxinterval_level (str, optional):
            Unit used with ``maxinterval_number``. Accepted values are
            ``"days"``, ``"months"``, and ``"years"``.

        split_date (str, optional):
            Scope of date-component extraction. Accepted values are:

            - ``"all"`` to extract components from all dates;
            - ``"interval"`` to extract components only for records whose original
            date was an interval.

        drop_mismatch_split (bool, optional):
            Strategy used when components extracted from the date
            disagree with values in existing year, month, or day columns.

            If ``True``, inconsistent components are removed from both the
            date and component columns while preserving temporal
            hierarchy. 
            
            If ``False``, the values extracted from the date column are
            retained and written to the component columns, giving 
            precedence to the date field.

            Whether the original date and component columns are overwritten is
            controlled separately by ``inplace_date_split`` and
            ``inplace_components_split``.

        inplace_components_split (bool, optional):
            Whether to overwrite existing year, month, and day columns during
            component extraction.

            If ``False``, the results are written to new processed component columns. 
            Components for which no input column was provided are always written to
            newly generated columns.

        inplace_date_split (bool, optional):
            Whether to overwrite the date column when inconsistencies are
            removed according to ``drop_mismatch_split``.

            If ``False``, modifications to the date are written to a new processed
            date column.

            This argument has no effect when ``drop_mismatch_split=False``, because
            the date values are retained unchanged under that strategy.

            This option is automatically set to ``True`` when
            ``inplace_interval=False``. Once interval processing has created a new
            date-column version, subsequent date transformations are applied in place
            to avoid generating additional processed columns.

        dropna_date (bool, optional):
            Whether to remove records whose processed date is missing after all
            temporal-curation stages.

    Returns:
        (pandas.DataFrame):
            Processed DataFrame containing standardized dates, reconciled temporal
            components, and any retained issue or interval-annotation columns.

    Note:
        - In ``marinedb``, once a transformation creates a processed version of a
        column, subsequent transformations are generally applied in place to that
        processed version rather than creating a new column at every stage. The
        processed column name is updated by appending the names of the successive 
        modules. Temporal interval processing is an exception: setting 
        ``inplace_interval=False`` creates a new processed date column before 
        intervals are collapsed or removed, allowing the preceding column 
        version containing the standardized intervals to be retained.

        - Missing or unparsable dates may be reconstructed from separate temporal
        components when a valid year is available and the components form a valid
        calendar date without clearly conflicting with the original date.

        - Giving precedence to the processed date when
        ``drop_mismatch_split=False`` is a design choice and does not imply
        that the date field is inherently more reliable than the separate
        component fields.
    """

    params = {
              'drop_empty' : False,
              'verbose': verbose,
              'indent': indent + '   '
             }

    printv('', verbose=verbose)
    printv('** parsedate', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    # Parse raw date strings

    params_parsedate = {
                        'format': format,
                        'inplace': inplace_parse,
                        'stdnan': stdnan,
                        'parallel': parallel,
                        'cpu': cpu
                       }

    df = parsedate.apply(df, datekey, yearkey=yearkey, monthkey=monthkey, daykey=daykey, **params_parsedate, **params)

    printv('** processdateinterval', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    # Process date intervals

    params_processdateinterval = {
                                  'drop_interval': drop_interval,
                                  'strategy': strategy_interval,
                                  'maxinterval_number': maxinterval_number,
                                  'maxinterval_level': maxinterval_level,
                                  'inplace': inplace_interval,
                                  'flag': True
                                 }

    columns_before = set(df.columns)
    basedatekey = datekey.split('_processedby_')[0]

    df = processdateinterval.apply(df, datekey, **params_processdateinterval, **params)

    columns_after = set(df.columns)
    columns_diff = list(columns_after - columns_before)
    columns_diff = [c for c in columns_diff if not (c.startswith(f'{basedatekey}_processedby') or c.startswith('issue_'))]

    # Split date into year, month, and day

    printv('** splitdate', verbose=verbose, indent=indent)
    printv('', verbose=verbose)

    if not inplace_interval:
        # minimizes the number of generated columns
        inplace_date_split = True

    params_splitdate = {
                        'split': split_date,
                        'drop_mismatch': drop_mismatch_split,
                        'inplace_components': inplace_components_split,
                        'inplace_date': inplace_date_split
                       }

    df = splitdate.apply(df, datekey, yearkey=yearkey, monthkey=monthkey, daykey=daykey, **params, **params_splitdate)

    # Drop columns generated by `processdateinterval`

    if not flag_interval:
        df.drop(columns=columns_diff, inplace=True)

    # Drop rows with missing values in the `datekey` column

    if dropna_date:

        df, datekeyout, _ = getcolumnname.apply(df, datekey, '', inplace=True, minimize_columns=False)
        ismissing = pd.isnull(df[datekeyout])
        df = df[~ismissing].reset_index(drop=True)

    return df
