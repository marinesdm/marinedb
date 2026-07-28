# isinworms

## API reference

<h3>
  <code>marinedb.tools.taxonomic.isinworms</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/taxonomic/isinworms.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.taxonomic.isinworms.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Classification match types

The `classif_matchtype_generatedby_isinworms` column records how the
taxonomic matching decision was reached. Each value consists of a base
decision type, optionally followed by a suffix indicating a subsequent
marine-status, fossil-status, taxonomic-resolution, or user-selection
assessment.

### WoRMS-based decisions

| Value | Meaning |
|---|---|
| `taxonNoSpecies` | The input scientific-name field is missing. |
| `worms_taxonNoMatch` | The scientific-name field is not missing, but the submitted name is not recognized by WoRMS. |
| `worms_taxonNoSpecies` | WoRMS recognizes the submitted value only at a rank above species. |
| `worms_taxonQuarantineDeleted` | WoRMS returns only quarantined or deleted records. |

### Classification-based decisions

| Value | Meaning |
|---|---|
| `classification_singleMatch` | A single WoRMS candidate matches the available higher-rank classification. This commonly occurs when WoRMS returns only one candidate. |
| `classification_singleAphiaID` | All candidates matching the higher-rank classification refer to the same accepted AphiaID and therefore to the same accepted taxon. No further distinction between candidates is required. |
| `classification_bestMatch` | One candidate is selected as the best higher-rank classification match. |
| `classification_bestSpeciesName` | One candidate is selected as the best scientific-name match among the remaining candidates. |
| `classification_undecided` | Several candidates remain and no candidate could be selected with sufficient confidence. |
| `classification_allAccepted` | All remaining candidates are accepted and share the same higher-rank classification, but could not be distinguished from the available input information. |
| `noclassification_kingdomNoMatch` | The higher-rank classification does not match, and the submitted kingdom is also inconsistent with the WoRMS candidates. |

For `classification_bestMatch`, candidates are first restricted to those with the lowest mismatch level, defined as the number of explicit rank mismatches plus
the number of rank comparisons for which information is missing on only one side. This worst-case, risk-averse strategy treats each one-sided missing value as a potential
mismatch, so that two confirmed mismatches are preferred to three potential mismatches. Among the retained candidates, those with the lowest number of explicit rank mismatches are kept. A match is assigned only if this leaves a single candidate.

<div
  style="
    width: 100%;
    max-width: 52rem;
    margin: 1.5rem auto;
  "
>
  <img
    src="../../../figure/classification_bestMatch.png"
    alt="Risk-averse classification-matching strategy"
    style="
      display: block;
      width: 100%;
      height: auto;
    "
  >

  <p
    style="
      width: 100%;
      margin: 0.75rem 0 0;
      text-align: left;
      font-style: italic;
    "
  >
    Candidate prioritization for
    <code>classification_bestMatch</code>. Diagonal lines connect combinations
    with the same mismatch level, defined as the sum of explicit rank mismatches
    and one-sided missing rank comparisons. Candidates with the lowest available
    mismatch level are retained first. Within that level, candidates with fewer
    explicit rank mismatches are preferred.
  </p>
</div>

For `classification_bestSpeciesName`, candidates are first restricted to those with the highest number of matching scientific-name components. Among these, candidates with the highest mean word-level Levenshtein similarity are retained. A match is assigned only if this leaves a single candidate. This criterion is applied only when all remaining candidate names share the same supported structure: either `Genus species [subspecies]` or `Genus (Subgenus) species [subspecies]`. Candidate sets mixing these structures, as well as other nomenclatural structures, such as names containing `var.` or `f.`, are not evaluated at this stage.

### Authorship-based decisions

| Value | Meaning |
|---|---|
| `classification_authorship_singleMatch` | A single candidate matches the available authorship information. |
| `classification_authorship_bestAuthorMatch` | One candidate is selected because its author names match the verbatim authorship better than those of the other candidates. |
| `classification_authorship_bestDateMatch` | One candidate is selected because its authorship date best matches the verbatim authorship date after the author-name comparison. |
| `classification_authorship_noSensuConflict` | One candidate remains after excluding candidates whose presence or absence of `sensu` conflicts with the verbatim authorship. |
| `classification_authorship_noMatchIsMore` | No complete authorship match is found, but the verbatim value contains additional information that may not have been fully used during authorship processing. |
| `classification_authorship_noMatch` | No candidate adequately matches the available authorship information. |

When several authorship candidates remain, author-name similarity is evaluated first, followed by authorship-date similarity and then by the presence or
absence of a `sensu` conflict.

### Potential taxonomic-revision decisions

These decision types apply when the submitted higher-rank classification conflicts with the WoRMS classification, while the scientific name and kingdom remain consistent. Such discrepancies may reflect taxonomic revisions. When informative authorship data are available, they are used to further evaluate the candidate set.

| Value | Meaning |
|---|---|
| `noclassification_authorship_singleMatch` | Authorship comparison supports a single candidate. |
| `noclassification_authorship_noMatchIsMore` | No authorship match is found, but the verbatim value contains additional information that may not have been fully used during authorship processing. |
| `noclassification_authorship_noMatch` | The available authorship information does not support any candidate. |
| `noclassification_kingdomMatch` | Authorship information is unavailable or insufficiently informative, so the case remains `uncertain`. |

### Decision suffixes

The following suffixes may be appended to a base decision type:

| Suffix | Meaning |
|---|---|
| `_taxonNoSpecies` | Taxonomic resolution leads to a taxon above species rank. The case is therefore classified as `nomatch`. |
| `_marine_unsure` | A resolved match has insufficient marine and brackish information to determine its environmental status and is therefore classified as `uncertain`. |
| `_non_marine` | The resolved taxon, or all candidates in an unresolved set, are explicitly non-marine and non-brackish. The case is therefore classified as `nomatch`. |
| `_fossil` | The resolved taxon, or all candidates in an unresolved set, are explicitly extinct while `keep_fossil=False`. The case is therefore classified as `nomatch`. |
| `_userSelected` | The decision is made interactively by the user, either by selecting a WoRMS candidate or by rejecting all available candidates. |

Marine status is evaluated before fossil status. Once a case is classified as `nomatch`, subsequent fossil assessment is not performed. Consequently, a 
non-marine taxon receives the `_non_marine` suffix but not an additional `_fossil` suffix, even if it is also extinct.

A match reclassified as `uncertain` because of unresolved marine status remains eligible for fossil assessment. It may therefore subsequently be reclassified 
as `nomatch` with the `_fossil` suffix when the matched taxon is explicitly extinct.

The `_userSelected` suffix is mainly produced through `resolvetaxamatch`, which calls `isinworms` in interactive mode for eligible uncertain cases. Selecting a WoRMS candidate changes the decision to `match`. Rejecting all candidates changes it to `nomatch`.

## Matching issues

The `issue_isinworms` column records problems or ambiguities encountered during taxonomic matching. Multiple issues may be combined in the same cell using semicolons.

### Authorship-processing issues

| Value | Meaning |
|---|---|
| `AUTHORSHIP_PARSE_FAILED` | The verbatim authorship cannot be parsed. Authorship-based matching is skipped for the corresponding verbatim value. |
| `AUTHORSHIP_MULTIPLE_SENSU` | More than one occurrence of `sensu` is detected in the candidate authorship information. These cases are not supported, so authorship-based matching is skipped for the corresponding verbatim value. |

Issues encountered while processing different verbatim columns are retained even when a later column allows authorship-based matching to continue.
Consequently, an authorship-processing issue may appear together with an ambiguity or taxonomic-resolution issue.

### Ambiguous matches

Ambiguity issues indicate that a match selected by one criterion is contradicted by a later criterion. Ambiguity checking stops after the first contradiction, while the initially selected match is retained.

| Value | Meaning |
|---|---|
| `AMBIGUOUS_HIGHER_RANKS_AUTHORSHIP_MATCH` | A unique match selected based on higher-rank classification is contradicted by authorship matching. |
| `AMBIGUOUS_HIGHER_RANKS_SPECIES_NAME_MATCH` | A match selected based on higher-rank classification, either as a unique match or as the best available classification match, is contradicted by scientific-name similarity. |
| `AMBIGUOUS_AUTHORSHIP_HIGHER_RANKS_MATCH` | A match selected based on authorship information is not retained among the candidates with the best higher-rank classification. |
| `AMBIGUOUS_AUTHORSHIP_SPECIES_NAME_MATCH` | A match selected based on authorship information is contradicted by scientific-name similarity. |

### Taxonomic-resolution issues

| Value | Meaning |
|---|---|
| `UNRESOLVED_TAXONOMIC_CYCLE` | A cyclic WoRMS resolution path is detected while mapping an infraspecific or unaccepted name to an accepted species-level name. The match is reclassified as `uncertain` for manual review. |

## Basic usage

When `createwormsfilters` and `isinworms` are both specified in the
configuration file, arguments specific to `createwormsfilters` need to be
defined only for that step. The workflow automatically passes the generated
WoRMS filters and the relevant configuration values to `isinworms`.

When only `isinworms` is specified, it automatically calls
`createwormsfilters` whenever the required filters are unavailable or
incomplete. In that case, the filter-creation arguments defined under
`isinworms` control this upstream processing.

!!! example
    ```
        - isinworms:
            rank_mapping:
              scientificname: 'species'
              genus: 'genus'
              family: 'family'
              order: 'order'
              cls: 'class'
              phylum: 'phylum'
              kingdom: 'kingdom'
            worms_dtypes:
              AphiaID: 'Int64'
              match_type: 'string'
              status: 'string'
              valid_AphiaID: 'Int64'
              lsid: 'string'
              isMarine: 'Int64'
              isBrackish: 'Int64'
              rank: 'string'
              authority: 'string'
            check_ambiguity: True
            uncertainty_level: 3
            fuzzy: True
            verbatimcolumn: ['scientificName', 'scientificNameAuthorship', 'originalScientificName']
            verbatimauthorshiponly: [False, True, False]
            keep_fossil: False
            inplace: True
            resume: True
            resume_mode: 'soft'
            parallel: True
            flag_nomatch: False
            flag_uncertain: False
            store_isinworms: False
    ```

## AphiaID-based classifications

`isinworms` returns the taxonomic classification of each matched species as 
taxon names. The WoRMS `AphiaRecordsByMatchNames` endpoint used by `isinworms` 
can only provide the AphiaID of the matched species and the AphiaID of its 
direct parent.

For users who need a more model-ready, identifier-based taxonomic
representation, the standalone `worms_classification_by_aphiaid.py` script can
be run independently. It relies on the WoRMS `AphiaClassificationByAphiaID` endpoint
to retrieve the AphiaIDs associated with the kingdom, phylum, class, order,
family, genus, and species ranks. The resulting file can then be joined back
to the curated dataset.

```bash
python worms_classification_by_aphiaid.py INPUTFILE [OPTIONS]
```

### Outputs

The script creates two files next to the input file:

- `<INPUTFILE>_worms_classification.<EXT>`, containing one row per unique input
AphiaID and separate `<rank>_AphiaID` columns
- `aphiaid_taxon_mapping.json`, mapping every AphiaID encountered in the
retrieved classification trees to its taxonomic rank and taxon name

The tabular output can be joined back to the curated dataset using the 
`input_AphiaID` column. The JSON mapping retains the corresponding textual 
taxonomic information while allowing the main dataset to use AphiaIDs only.

Taxonomic levels outside the principal ranks listed above are not included as
columns in the tabular output. Any unrecognized rank labels encountered during
retrieval are reported in the command-line output.

### Arguments

``INPUTFILE``

Path to a tab-separated file containing a column of WoRMS AphiaIDs.

### Options

``--aphiaid-column``

Name of the column containing the AphiaIDs. Defaults to `AphiaID`.

``--max-attempt`` 

Maximum number of attempts made for each WoRMS request. Defaults to `10`.

``--pause-duration``

Number of seconds to wait between failed request attempts. Defaults to `20`.

``--timeout``

Maximum number of seconds allowed for each request. Defaults to `30`.