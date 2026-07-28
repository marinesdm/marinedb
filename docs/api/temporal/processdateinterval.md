# processdateinterval

## API reference

<h3>
  <code>marinedb.tools.temporal.processdateinterval</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/temporal/processdateinterval.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.temporal.processdateinterval.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Date-interval issues

The `issue_processdateinterval` column records failures encountered while
processing parsed date intervals and intervals whose duration exceeds the
configured maximum width. Multiple issues may be combined in the same cell
using semicolons.

Issue values are constructed from the original input-column name converted to
uppercase. For example, an issue derived from `eventDate` uses the prefix
`EVENTDATE`. This prefix continues to refer to the original column name even when the
corresponding column is subsequently renamed in the `variables` section.

| Value pattern | Meaning |
|---|---|
| `<DATE>_INTERVAL_PROCESSING_FAILED` | At least one boundary of a date interval cannot be converted to ISO 8601. |
| `<DATE>_INTERVAL_EXCEEDS_LIMIT` | The duration of the parsed date interval exceeds the configured maximum interval width. |

In both case, the date is replaced with a missing value in the output.