# parsedate

## API reference

<h3>
  <code>marinedb.tools.temporal.parsedate</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/temporal/parsedate.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.temporal.parsedate.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Date-parsing issues

The `issue_parsedate` column records parsing failures, invalid or ambiguous
date components, internal inconsistencies, mismatches between the date field
and separate temporal components, and dates reconstructed during processing.
Multiple issues may be combined in the same cell using semicolons.

Issue values are constructed from the original input-column names converted to
uppercase. For example, issues derived from `eventDate`, `year`, `month`, and
`day` use the prefixes `EVENTDATE`, `YEAR`, `MONTH`, and `DAY`. These prefixes 
continue to refer to the original column names even when the corresponding columns 
are subsequently renamed in the `variables` section.          

### Initial date-parsing issues

These issues originate from the GBIF date parser or from Java exceptions captured by the `marinedb` 
command-line wrapper when the original date values are submitted for parsing.

| Value pattern | Meaning |
|---|---|
| `<DATE>_INVALID` | The date parser cannot interpret the original value as a valid date. |
| `<DATE>_JAVA_ILLEGALARGUMENTEXCEPTION` | The GBIF parser raises a Java `IllegalArgumentException` while processing the original value. |
| `<DATE>_JAVA_DATETIMEEXCEPTION` | The GBIF parser raises a Java `DateTimeException` while processing the original value. |
| `<DATE>_UNLIKELY` | The value can be interpreted as a date but is classified as unlikely by the GBIF parser. |

For example, when the original date column is `eventDate`, the first issue becomes `EVENTDATE_INVALID`.

??? info "GBIF date-parser resources"

    `parsedate` relies on a Java command-line wrapper built around the GBIF
    date parser. Additional information is available in the GBIF
    [date-parser documentation](https://github.com/gbif/parsers/blob/dev/assets/DateParsingDocumentation.md), 
    [date-parser source code](https://github.com/gbif/parsers/tree/dev/src/main/java/org/gbif/common/parsers/date), 
    [date-parser tests](https://github.com/gbif/parsers/tree/dev/src/test/java/org/gbif/common/parsers/date),  
    and [high-level temporal-interpretation documentation](https://techdocs.gbif.org/en/data-processing/temporal-interpretation).

### Invalid or ambiguous temporal components

These issues are produced while validating separate year, month, or day
columns used to check or reconstruct a date.

| Value pattern | Meaning |
|---|---|
| `<COMPONENT>_INVALID` | The component cannot be converted to a valid numeric temporal value. This includes non-numeric values, unsupported year lengths, months outside `1`-`12`, and days outside `1`-`31`. |
| `<YEAR>_AMBIGUOUS` | The year contains two digits and therefore cannot be interpreted unambiguously. Depending on the selected settings, it may be replaced with a missing value. |
| `<YEAR>_<MONTH>_<DAY>_COMBINATION_INVALID` | The year, month, and day are individually valid but do not form an existing calendar date, including invalid leap-year combinations. |

For example, when the original year column is `year`, the first issue becomes `YEAR_INVALID`.

### Hierarchical inconsistencies

These issues indicate that a more specific temporal component is present while
a required broader component is missing.

| Value pattern | Meaning |
|---|---|
| `<YEAR>_<MONTH>_INCONSISTENT` | A month value is present while the corresponding year is missing. |
| `<YEAR>_<DAY>_INCONSISTENT` | A day value is present while the corresponding year is missing. |
| `<MONTH>_<DAY>_INCONSISTENT` | A day value is present while the corresponding month is missing. |

### Date-component mismatches

Mismatch issues are produced when an unparsable date string is compared with
separate year, month, or day values and a clear conflict is detected.

| Value pattern | Meaning |
|---|---|
| `<DATE>_<YEAR>_MISMATCH` | The year value cannot be reconciled with the date string. |
| `<DATE>_<MONTH>_MISMATCH` | The month value cannot be reconciled with the date string. |
| `<DATE>_<DAY>_MISMATCH` | The day value cannot be reconciled with the date string. |
| `UNCERTAIN_<DATE>_<COMPONENT>_MISMATCH` | A mismatch is detected, but the date string contains more than ten characters, making the interpretation less reliable because additional time, interval, or contextual information may be present. |
| `UNCERTAIN_<DATE>_<COMPONENTS>_MATCH` | The available temporal components appear to match parts of the date string, but residual numeric content remains. The apparent match is therefore considered uncertain. |

Examples include `EVENTDATE_YEAR_MISMATCH`, `UNCERTAIN_EVENTDATE_MONTH_MISMATCH`, and `UNCERTAIN_EVENTDATE_YEAR_MONTH_DAY_MATCH`.

!!! warning

    Mismatch issues produced during `parsedate` should be interpreted as
    conservative warning signals rather than as exhaustive or definitive
    diagnoses.

    Components are tested sequentially, and checking stops when the first clear
    conflict is found. The reported component therefore marks the point at
    which inconsistency becomes detectable, but it may not identify the
    original source of the mismatch.

    ??? example

        `01/03/2010` is an ambiguous non-ISO 8601 date intentionally left 
        unparsed by the GBIF parser because the first two components could represent 
        either day-month or month-day order. 

        Suppose the intended order is `DD/MM/YYYY`, while the separate fields contain 
        `2010` for the year, `01` for the month, and `01` for the day. The apparent 
        month match is accepted first, and a day mismatch is then reported, even though 
        the underlying disagreement originated earlier.

    Some reported mismatches may be false positives caused by unsupported languages or 
    date formats, including unparsable date ranges.

    Conversely, genuine mismatches may remain undetected when the date format
    is ambiguous or when separate components can be found within an
    unparsable date range.

`parsedate` therefore follows a reasonable-doubt strategy: unless a clear
conflict is detected, the date and its separate components are treated as
internally consistent. When a clear mismatch is found, date reconstruction is
prevented.

### Date reconstruction

| Value pattern | Meaning |
|---|---|
| `<DATE>_ASSEMBLED` | The original date could not be retained directly, but a replacement date was reconstructed from valid and sufficiently consistent temporal components and formatted according to ISO 8601. |

For example, a date reconstructed for `eventDate` is annotated with `EVENTDATE_ASSEMBLED`.
