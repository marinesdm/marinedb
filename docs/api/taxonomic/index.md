# Taxonomic tools

This section documents the `marinedb` modules dedicated to taxonomic
harmonization, basis-of-record processing, taxonomic filtering, and
taxon-based occurrence subsampling.

These tools can:

- create reusable WoRMS matching resources
- harmonize scientific names, taxonomic classifications, and authorship
  information against WoRMS
- identify and resolve uncertain or unresolved taxonomic matches
- standardize values to Darwin Core basis-of-record categories
- flag or exclude records based on basis-of-record categories
- detect taxonomic values containing unsupported characters
- annotate or exclude underrepresented taxa
- spatially subsample overrepresented taxa

## WoRMS-based taxonomic harmonization

The recommended taxonomic harmonization workflow consists of three main
stages:

1. **WoRMS resource creation**  
   Unique scientific names are extracted from the input data, preprocessed, 
   and queried against WoRMS. Unaccepted and infraspecific candidate matches 
   are then resolved to accepted species-level taxa when possible before being 
   stored in reusable filters for subsequent taxonomic harmonization.

2. **Taxonomic harmonization**  
   Scientific names are matched against WoRMS and candidate taxa are compared
   using taxonomic classification and authorship information. Accepted names
   and species-level taxa are assigned when possible, while uncertain and
   unresolved outcomes can be annotated or excluded.

3. **Manual taxonomic resolution**  
   Selected uncertain matches can be submitted to interactive review. Manual
   decisions are stored and propagated to all records sharing the same
   taxonomic combination.

These stages are implemented by `createwormsfilters`, `isinworms`, and
`resolvetaxamatch`. Running them in isolation is discouraged for standard
taxonomic workflows, as the three modules are designed to operate together.
`isinworms` can call `createwormsfilters` automatically when the required
WoRMS resources are not already available. The integrated workflow also
harmonizes and forwards the parameters shared by the three modules throughout
processing, reducing the risk of inconsistent settings between stages.

## Basis-of-record processing

Basis-of-record processing can consist of two complementary operations:

1. **Standardization**  
   Values from an existing basis-of-record field or another informative
   column, such as a sampling-protocol field, are mapped to standardized
   Darwin Core basis-of-record categories. The default mapping can be extended
   or modified through user-provided mappings.

2. **Filtering**  
   Standardized or existing basis-of-record values are compared with a
   user-defined set of categories. Matching records can be flagged, or
   non-matching records can be excluded.

These operations are implemented by `mapbasisofrecord` and `basisofrecordisin`. 
`basisofrecordisin` can call `mapbasisofrecord` directly to standardize source 
values before testing them against the requested basis-of-record categories. 
Users can therefore rely on `basisofrecordisin` alone when both standardization 
and filtering are needed, or call `mapbasisofrecord` separately when only 
standardization is required.

## Additional taxonomic filters

`lettersonly` checks whether taxonomic values contain only letters, spaces, or
hyphens. It provides a broad character-based filter for workflows in which
full taxonomic harmonization is not performed. It can identify many molecular,
strain, or environmental-sequence identifiers containing digits, underscores,
or other symbols. It should preferably be applied only to relatively
standardized taxonomic columns, as legitimate bacterial, archaeal, or viral
taxa may contain alphanumeric values, while non-standardized scientific names
may include authorship dates or other punctuation.

`taxasubset` is intended for use after taxonomic and occurrence-data cleaning. 
It controls the number of records associated with each taxon. It can annotate 
or exclude underrepresented taxa and spatially subsample overrepresented ones 
using the H3 hierarchical hexagonal grid.

## Tools

- [`createwormsfilters`](createwormsfilters.md): create reusable WoRMS matching
  resources from the scientific names found in the input data.
- [`isinworms`](isinworms.md): harmonize scientific names, classifications, and
  authorship information against WoRMS.
- [`resolvetaxamatch`](resolvetaxamatch.md): interactively review and resolve
  selected uncertain taxonomic matches.
- [`mapbasisofrecord`](mapbasisofrecord.md): map source values to standardized
  Darwin Core basis-of-record categories.
- [`basisofrecordisin`](basisofrecordisin.md): flag or exclude records according
  to user-specified basis-of-record categories, with optional prior
  standardization.
- [`lettersonly`](lettersonly.md): evaluate taxon names for unsupported
  characters.
- [`taxasubset`](taxasubset.md): annotate or exclude underrepresented taxa and
  spatially subsample overrepresented taxa.

## Choosing an approach

For general taxonomic cleaning, use the WoRMS-based workflow composed of
`createwormsfilters`, `isinworms`, and, when needed, `resolvetaxamatch`.

Use `lettersonly` only as a simpler character-based alternative when full
taxonomic harmonization is not performed.

Use `taxasubset` after taxonomic harmonization and occurrence cleaning, once
the species identifiers and, for spatial subsampling, the geographic
coordinates are ready for downstream processing.