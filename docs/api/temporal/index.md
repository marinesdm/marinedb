# Temporal data curation

This section documents the `marinedb` modules dedicated to cleaning and
standardizing the temporal dimension of species occurrence data.

These tools can:

- standardize dates to ISO 8601 format
- reconstruct missing or unparsable dates from separate year, month, and day
  fields
- process date intervals
- extract and reconcile year, month, and day components
- detect invalid dates
- detect dates outside an expected temporal range

The temporal curation workflow consists of three main stages:

1. **Date parsing and reconstruction**  
   Raw date values are standardized to ISO 8601 format. Missing or unparsable
   dates may be reconstructed from valid year, month, and day values when these
   do not clearly conflict with the original date.

2. **Date-interval processing**  
   Date intervals are annotated, removed, or collapsed to a single temporal
   value by retaining their start, their end, or only the components shared by
   both bounds.

3. **Date-component extraction**  
   Year, month, and day values are extracted from the processed dates and
   compared with any corresponding component columns already present in the
   input data. When values disagree, the function either removes the
   inconsistent components or gives precedence to those extracted from the
   date field, according to the selected strategy.

Each stage is documented separately and can be run independently. However,
using the integrated `temporal` module is strongly recommended for standard
workflows, as it applies the stages in the expected order and reduces the risk
of errors arising from untested combinations of individual module settings.

## Tools

- [`parsedate`](parsedate.md): standardize occurrence dates and reconstruct
  missing or unparsable values from separate temporal components.
- [`processdateinterval`](processdateinterval.md): annotate, remove, or collapse
  date intervals.
- [`splitdate`](splitdate.md): extract year, month, and day components and
  reconcile them with existing temporal fields.
- [`temporal`](temporal.md): run the complete temporal data-curation workflow.
- [`isdateinvalid`](isdateinvalid.md): detect or exclude incorrectly formatted
  or nonexistent dates.
- [`isdateunlikely`](isdateunlikely.md): detect or exclude dates outside a
  user-defined year range.