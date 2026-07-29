# splitdate

## API reference

<h3>
  <code>marinedb.tools.temporal.splitdate</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/temporal/splitdate.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.temporal.splitdate.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Date-splitting issues

The `issue_splitdate` column records mismatches detected when standardized
dates are split into separate year, month, and day components and compared with
existing temporal-component columns. Multiple issues may be combined in the
same cell using semicolons.

Unlike the mismatch issues produced by `parsedate`, these issues are evaluated
after dates and date intervals have normally been standardized. A reported mismatch 
therefore represents a confirmed disagreement rather than a conservative warning signal.

Issue values are constructed from the original input-column name converted to uppercase. 
For example, an issue derived from `eventDate` and `year` produces the prefix 
`EVENTDATE_YEAR`. This prefix continues to refer to the original column names even when 
the corresponding column are subsequently renamed in the `variables` section.

| Value pattern | Meaning |
|---|---|
| `<DATE>_<YEAR>_MISMATCH` | The year extracted from the standardized date differs from the value in the existing year column. |
| `<DATE>_<MONTH>_MISMATCH` | The month extracted from the standardized date differs from the value in the existing month column. |
| `<DATE>_<DAY>_MISMATCH` | The day extracted from the standardized date differs from the value in the existing day column. |

!!! note

    `splitdate` validates the existing year, month, and day values internally
    before comparing them with the extracted components. However, conversion
    issues such as `INVALID`, `AMBIGUOUS`, and `INCONSISTENT` are not retained
    in `issue_splitdate`.

    Within the standard temporal workflow, these checks have already been
    performed by `parsedate`, so retaining them again would be redundant.
    When `splitdate` is used independently of `parsedate`, conversion problems
    detected during this internal step are therefore not reported.

    An option to retain these conversion issues will be added in a future
    release. Until then, users who do not want to run the full temporal workflow
    but need these issues should run `convertdatetype` before `splitdate`.

## Basic usage

!!! example
    ```
    - tool:
        - splitdate:
            datekey: 'eventDate'
            yearkey: 'year'
            monthkey: 'month'
            daykey: 'day'
            split: 'all'
            strategy: 'start'
            maxinterval_number: 3
            maxinterval_level: 'months'
            drop_interval: false
            drop_mismatch: true
            inplace_date: false
            inplace_components: False
            flag: true
    ```