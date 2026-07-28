# Package resources

## Reference files

Several `marinedb` modules rely on reference files distributed with the
package. These resources are located in 
<code>marinedb/tools/data</code>
<a href="{{ source_base_url }}/src/marinedb/tools/data?ref_type=heads"
   target="_blank"
   rel="noopener noreferrer"
   style="font-weight:normal;font-size:0.8em;">[source]</a>.

They provide default mappings, taxonomic vocabularies, and spatial masks used 
during data curation.

### `basisOfRecord.yaml`

Contains the default mapping from source values to standardized Darwin Core
basis-of-record categories.

It is used by [`mapbasisofrecord`](taxonomic/mapbasisofrecord.md) and, indirectly, 
by [`basisofrecordisin`](taxonomic/basisofrecordisin.md).

The supported output categories are:

- `OCCURRENCE`
- `HUMAN_OBSERVATION`
- `MACHINE_OBSERVATION`
- `MATERIAL_SAMPLE`
- `MATERIAL_CITATION`
- `FOSSIL_SPECIMEN`
- `LIVING_SPECIMEN`
- `PRESERVED_SPECIMEN`

Users can extend or override this mapping for an individual operation through
the corresponding module parameters. Advanced users may also modify the YAML
file directly to change the default mapping for their local installation. 

!!! warning

    Changes made directly to package resource files may be overwritten when
    the repository is updated or the package is reinstalled.

### `globe_mask.npz`

Contains the binary global land–sea mask from which the land–sea–coast mask is
constructed.

This file can be used by `createmask.py` to rebuild `globe_mask_coastline.npz` with alternative 
parameters controlling how coastline is defined.

### `globe_mask_coastline.npz`

Contains the global land–sea–coast mask used by default by [`island.py`](spatial/marineloc/island.md) 
to identify and exclude records located on land.

### `ignoreWords.yaml`

Contains words and abbreviations ignored during scientific-name and authorship
processing. 

Its primary purpose is to clean raw taxonomic strings before they are queried
against WoRMS by [`createwormsfilters.py`](taxonomic/createwormsfilters.md). 
Ignoring these terms helps prevent WoRMS matching from failing for reasons unrelated 
to the taxon itself.

The same resource is also used by [`isinworms.py`](taxonomic/isinworms.md) when extracting 
and comparing taxonomic authorship. Ignoring these terms reduces false authorship mismatches.

The file is divided into two main sections.

#### `SCN_IGNORE`

Contains words and abbreviations that may occur alongside a taxon name but are
not treated as part of the scientific name used for matching.

The list includes:

- infraspecific and supraspecific rank terms and abbreviations, such as
  `subsp`, `var`, `forma`, `genus`, `tribe`, and `clade`
- life-stage, sex, and specimen-condition terms, such as `larva`, `juvenile`,
  `adult`, `male`, `exuvia`, `shell`, and `fragment`
- cultivation and microbiological qualifiers, such as `cultured`,
  `uncultured`, `candidatus`, `clone`, and `environmental`
- uncertainty and open-nomenclature qualifiers, such as `indet`, `cf`, `aff`,
  `near`, `complex`, `aggregate`, and `incertae sedis`
- nomenclatural-status and editorial qualifiers, such as `nom`, `ined`,
  `inval`, `illeg`, `rej`, `conservandum`, and `provisorium`
- contextual terms that may describe the record rather than the taxon name,
  such as `endosymbiont`, `sample`, `marine`, `virus`, and `from`

#### `AUTHORSHIP_IGNORE`

Contains words and name particles that may occur in authorship strings but
should not be interpreted as author surnames during authorship comparison.

The list includes:

- interpretive and nomenclatural qualifiers, such as `sensu`, `secundum`,
  `lato`, `stricto`, `emend`, `corr`, and `excl`
- authorship connectors and citation terms, such as `ex`, `et`, `and`, `in`,
  `apud`, `fide`, and `auct`
- manuscript or anonymous-authorship indicators, such as `ms`, `anon`, and
  `author`
- generational and collaborative qualifiers, such as `filius`, `fil`, and
  `et al.`
- surname particles and prepositions from several languages, such as `van`,
  `von`, `de`, `del`, `della`, `du`, `di`, `dos`, `mac`, and `mc`

### `month.yaml`

Contains mappings from textual month representations to numeric month values.

The resource includes month names and abbreviations in several languages, with
particular coverage of European languages. 

The mapping is currently used to detect internal inconsistencies in temporal
information. It is not used to convert textual month values into numeric
months in the curated output.

### `taxonomicRanks.yaml`

Contains taxonomic ranks and subranks ordered from the lowest to the highest
rank, from `mutatio` to `superdomain`.

The file is used by [`createwormsfilters.py`](taxonomic/createwormsfilters.md) to determine whether a WoRMS candidate
is below species level. 

Ambiguous rank names are excluded from the ordered reference. These include series, subsection, section, 
subdivision, division, and superdivision. Their meaning can vary among nomenclatural codes or taxonomic groups and
therefore cannot be positioned unambiguously in a single rank hierarchy.

## Utility functions

Several generic helper functions are available in 
<code>marinedb/tools/data</code>
<a href="{{ source_base_url }}/src/marinedb/utils?ref_type=heads"
   target="_blank"
   rel="noopener noreferrer"
   style="font-weight:normal;font-size:0.8em;">[source]</a>.

These utilities support recurring tasks used throughout `marinedb`, including
path resolution, file reading and writing, missing-value standardization,
printing, output-file naming, directory cleanup, and memory or file-size
reporting.

One particularly useful utility is `extractcolumns.py`, which extracts only selected columns from a file. 
This is useful when the complete dataset is too large to load into memory and only a subset of
fields is required.

The remaining utilities can be explored directly in the source directory.