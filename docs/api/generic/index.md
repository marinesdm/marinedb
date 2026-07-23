# Generic data curation

This section documents the generic `marinedb` modules used to curate species
occurrence data according to user-defined values, patterns, ranges, or missing
data.

These tools can identify records whose values:

- contain or do not contain specified patterns;
- belong or do not belong to a defined set;
- fall within user-defined bounds;
- are missing.

## Tools

- [`doesnotcontain`](doesnotcontain.md): detect values that do not contain the
  specified patterns.
- [`contains`](contains.md): detect values containing one or more specified
  patterns.
- [`isin`](isin.md): detect values belonging to a user-defined set.
- [`notisin`](notisin.md): detect values that do not belong to a user-defined
  set.
  - [`isna`](isna.md): detect missing values.
- [`isboundedby`](isboundedby.md): detect numeric values within user-defined
  lower and upper bounds.