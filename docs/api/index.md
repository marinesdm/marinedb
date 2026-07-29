# Overview

`marinedb` is an open-source Python package for building reproducible and 
configurable workflows to curate marine species-occurrence data.

Marine occurrence datasets commonly combine heterogeneous sources and may contain
issues that span multiple dimensions, including spatial, temporal, and taxonomic. 
Rather than imposing a single fixed pipeline, `marinedb` provides independent modules 
that can be selected, ordered, and configured according to input data characteristics 
and intended downstream analyses.

The package includes tools to:

- annotate or exclude records according to values, patterns,
  ranges, missing data, or other user-defined conditions
- detect invalid, imprecise, or otherwise problematic coordinates
- exclude land-based records from marine occurrence datasets
- parse, reconstruct, validate, and standardize temporal information
- harmonize scientific names and taxonomic classifications against WoRMS
- filter underrepresented taxa and spatially subsample overrepresented ones
- process Darwin Core basis-of-record information
- select, rename, and cast output columns
- retain a trace of the processing steps applied to each generated or modified
  column

`marinedb` is intended primarily for Linux environments. Windows users can run
it through the Windows Subsystem for Linux. Python 3.12 is currently strongly
recommended.

## Running a curation workflow

A complete workflow is launched with `clean.py`, using the path to a YAML
configuration file as its required positional argument.

The command also accepts options controlling parallel execution and
intermediate-file cleanup.

```bash
python clean.py CONFIG_FILE [OPTIONS]
```

### Arguments

``CONFIG_FILE`` 

Path to the YAML configuration file defining the curation workflow.

### Options

``--parallel`` / ``--no-parallel``

Whether to execute the main workflow on multiple CPUs. Parallel processing
is disabled by default.

``--cpu-max INTEGER``

Maximum number of CPUs available for parallel execution. When omitted,
`marinedb` determines the usable CPU allocation internally.

``--cleanup`` / ``--no-cleanup``

Whether to delete intermediate files generated during processing.
Intermediate-file cleanup is enabled by default.

The command-line `cleanup` setting is propagated automatically to modules that
support a corresponding cleanup option. It therefore generally does not need
to be configured separately within individual operations.

!!! example
    ```bash
    python clean.py config_gbif.yaml --parallel --cpu-max 22 --cleanup
    ```

### Outputs

In addition to the curated dataset, `clean.py` creates:

- `marinedb_dtypes.json`, describing the data types of the final columns.
- `marinedb_stats.txt`, recording row counts before and after each main
  curation step for each [partition of 100,000 rows](#large-datasets).
- `marinedb_times.txt`, recording the processing time in seconds and the row
  counts before and after the main curation stage for each partition. It does 
  not include preparatory operations such as `format`, `createwormsfilters`, 
  or `marineloc`, nor operations from the `postprocessing` section.

## Configuration-driven workflows

A curation workflow is defined in a YAML configuration file and executed by
`clean.py`. The configuration describes:

1. the input and output paths
2. the processing operations
3. the variables to retain, rename, and cast
4. any post-processing operations

A minimal configuration follows this structure:

```yaml
data:

  # Input and output paths
  inputfile_path: ...
  inputdir_path: ...
  outputdir_path: ...
  outputfile_path: ...

  # Main curation workflow
  processing:
    ...

  # Final column selection, renaming, and type casting
  variables:
    ...

  # Operations that depend on previous curation results
  postprocessing:
    ...
```

`processing`, `variables`, and `postprocessing` may be left empty when they are not needed.
When `variables` is left empty, all columns are retained.

??? info "Workflow-managed parameters"

    When a configuration is executed through `clean.py`, several technical
    parameters are managed centrally to keep processing consistent across
    modules.

    In particular, the workflow:

    - assigns module output directories from `inputdir_path` and
      `outputdir_path`
    - normalizes missing values before the main processing steps and disables
      redundant missing-value standardization in most individual modules
    - prevents intermediate batches from dropping empty columns, ensuring a
      consistent table structure across batch processing
    - propagates the workflow-level `cleanup` setting to modules that support
      it

    These parameters generally do not need to be specified separately inside
    each operation.

### Input and output paths

The first part of the configuration file must define the input file, a working directory, 
an output directory, and the final output filename.

!!! Example

    ```yaml
    data:

    inputfile_path: "/path/to/source/occurrences.txt"
    inputdir_path: "/path/to/workspace"
    outputdir_path: "/path/to/output/directory"
    outputfile_path: "occurrences_processedby_marinedb.txt"
    ```

`inputfile_path` identifies the dataset to process. It may be an absolute or relative path. 
The file must already exist.

`inputdir_path` defines the working directory used by the workflow. It is primarily
used to store preparatory outputs, reusable resources, temporary files, and other intermediate 
workflow products. The directory is created automatically when it does not already exist.

`outputdir_path` defines the directory used for the final curated dataset and for outputs produced 
by most processing and post-processing modules. It is created automatically when it does not 
already exist.

`outputfile_path` defines the final processed file. When it is empty or
has the same filename as the input file, `marinedb` generates a filename from the
input filename using the `_processedby_marinedb` suffix. When only a filename is
provided, the final file is placed inside `outputdir_path`.

`clean.py` assigns module-level output directories automatically from
`inputdir_path` and `outputdir_path`. Users therefore generally do not need to
specify `outputdir` inside individual operations.

??? info "Detailed directory assignments"

    - `format` and `createwormsfilters` write their preparatory or reusable
      resources to `inputdir_path`.
    - `marineloc` uses `inputdir_path` by default for its intermediate files,
      including split files stored under `marineloc/split`, unless a supported
      directory argument is explicitly provided.
    - WoRMS resources created internally by `createwormsfilters` are written to 
      `inputdir_path`, while the taxonomic decision-history file produced by 
      `isinworms` is written to `outputdir_path`.
    - Other processing and post-processing modules with a standard `outputdir` 
      parameter write to `outputdir_path`.

### Curation operations

The `processing` and `postprocessing` sections contain the curation operations. 
The `processing` section is executed first, followed by `postprocessing`. 
Steps are executed sequentially, so each operation receives the result produced by the
preceding operation.

Modules can:

- be applied to a single dataset column
- use several explicitly specified columns
- use columns automatically resolved from previous processing steps

#### A single column

For a module applied to a single column, the column name must be used as the first key.

!!! example

    ```yaml
    processing:

        - coordinateUncertaintyInMeters:
            - isboundedby:
                operator: ">"
                value: 1000
                flag: false
                dropna: false
    ```

    Here, `isboundedby` excludes records with values in `coordinateUncertaintyInMeters` 
    greater than 1000 m.

Several operations can be applied sequentially to the same column. They may be
defined in separate entries or grouped under the same column entry.

!!! example
    
    Equivalent configurations:

    ```yaml
    processing:

        - year:
            - isna:
                flag: false

        - year:
            - isboundedby:
                operator: "<"
                value: 1950
                flag: true
    ```

    ```yaml
    processing:

        - year:
            - isna:
                flag: false
             - isboundedby:
                operator: "<"
                value: 1950
                flag: true
    ```

#### Multiple columns

Modules that require several columns must be placed under `tool`, with the
relevant column names supplied as parameters. This includes integrated
workflows such as `temporal` or `marineloc`.

!!! example

    ```yaml
    processing:

        - tool:
            - islatloninvalid:
                latkey: "decimalLatitude"
                lonkey: "decimalLongitude"
                flag: false
                dropna: true
    ```

Some modules are also placed under `tool`, but do not require every input column to be 
specified explicitly. When columns are generated or resolved by an earlier stage of the 
integrated workflow, `clean.py` forwards them automatically.

!!! example

    When `taxasubset` is used after taxonomic harmonization, the species identifier 
    generated during the preceding taxonomic steps is passed automatically. 
    Users therefore do not need to specify `speciesidkey` again. However, `latkey` 
    and `lonkey` must still be supplied.

    ```yaml
    postprocessing:

        - tool:
            - taxasubset:
                upperbound: 1000
                latkey: "decimalLatitude"
                lonkey: "decimalLongitude"
    ```

#### Parameter values

A parameter may receive a single value or a collection of values.

!!! example

    `values` receives a list, while `flag` receives a Boolean value.

    ```yaml
    processing:

        - kingdom:
            - notisin:
                values: ['Bacteria', 'Archaea', 'Viruses']
                flag: false
    ```

    This is equivalent to:

    ```yaml
    processing:

        - kingdom:
            - notisin:
                values:
                    - 'Bacteria'
                    - 'Archaea'
                    - 'Viruses'
                flag: False
    ```

Nested dictionaries and lists are used for modules with more complex configuration 
requirements, such as taxonomic rank mappings.

!!! example

    `rank_mapping` receives a dictionary whose keys identify the taxonomic
    ranks expected by `isinworms` and whose values identify the corresponding
    input columns.

    ```yaml
    processing:

        - scientificName:
            - isinworms:
                rank_mapping:
                    scientificname: 'scientificName'
                    genus: 'genus'
                    family: 'family'
                    order: 'order'
                    cls: 'class'
                    phylum: 'phylum'
                    kingdom: 'kingdom'
            ...
    ```

Each module page documents its accepted parameters and their behavior.

### Columns throughout the workflow

#### Column provenance

`marinedb` systematically records processing provenance in column names.

- Columns derived from an existing column follow the pattern `<column>_processedby_<operation>`. 
- Columns newly created by an operation follow the pattern `<column>_generatedby_<operation>`

!!! example
    For example, taxonomic harmonization may produce columns such as `species_processedby_isinworms` 
    and `AphiaID_generatedby_isinworms`. 

When a column is processed repeatedly, the names of successive operations are appended to the 
provenance suffix. This naming convention makes it possible to trace how each output field was 
produced.

!!!example 

    For example, 
    `eventDate_processedby_parsedate_processdateinterval_splitdate` indicates that
    the original `eventDate` column has passed through three successive steps:

    1. `parsedate` standardized the date to ISO 8601 format.
    2. `processdateinterval` processed date intervals by removing them or
    collapsing them to a single temporal value, according to the selected
    settings.
    3. `splitdate` extracted and reconciled temporal components and may have
    removed inconsistent parts of the date value.


Users do not need to reproduce these processed-column names when writing the configuration file. 
For columns derived from an original input column, they can continue to refer to the original name, 
and `marinedb` automatically resolves the most recent version available at each point in the workflow. 

This automatic resolution also applies in the `variables` section.

Columns created by an operation do not have an original input-column name to
resolve. Generated columns must therefore be referenced explicitly using their
full `<column>_generatedby_<operation>` name.

!!! example

    ```yaml
    processing:

        - basisOfRecord:
            - mapbasisofrecord:
                inplace: true
            - notisin:
                values: "FOSSIL_SPECIMEN"
                flag: false
    ```
    
    Here, `mapbasisofrecord` first processes and renames the source column following
    the `<column>_processedby_<operation>` convention. `notisin` is then applied to
    this renamed processed column, even though the configuration continues to refer
    to `basisOfRecord`.

#### Columns created during processing

Columns generated as the workflow progresses are immediately available to subsequent 
processing steps. A later operation can therefore target a generated column explicitly 
when needed. 

Because generated columns cannot be resolved from an original input-column name, 
they must be targeted using their full generated name.

!!! example

    The following operation flags harmonized scientific names whose WoRMS
    status is not `accepted`. 

    ```yaml
    processing:

        - status_generatedby_isinworms:
            - notisin:
                values: 'accepted'
                flag: true

    ```

    Here, `notisin` is applied directly to the `status_generatedby_isinworms` 
    column created earlier by `isinworms`.


### Column selection, renaming, and type casting

The `variables` section controls the structure of the final dataset. It can be
used to:

- select the columns to retain
- rename columns
- assign final data types

The `variables` section is evaluated after the main processing workflow, so it 
can select both original and newly generated columns.

Columns generated during processing are automatically added to the final
selection and do not need to be listed explicitly in `variables`, unless they
must be renamed or assigned a specific output type. 

When `variables` is left empty, all original and generated columns are retained.

#### Retaining a column

A column can be retained without modification by listing its name.

!!! example

    ```yaml
    variables:

        - decimalLatitude
        - decimalLongitude
        - eventDate
        - AphiaID_generatedby_isinworms
    ```

    `AphiaID_generatedby_isinworms` could be omitted from this list because
    columns generated during processing are retained automatically. It is listed 
    here only to illustrate that generated columns may also be referenced 
    explicitly in `variables`.

#### Renaming a column

A column can be renamed using a key-value mapping.

!!! example

    ```yaml
    variables:

        - decimalLatitude
        - decimalLongitude
        - eventDate
        - AphiaID_generatedby_isinworms:
            AphiaID
    ```

    Here, `AphiaID_generatedby_isinworms` is retained in the final dataset
    under the name `AphiaID`.

    Note that `decimalLatitude`, `decimalLongitude` and `eventDate` are 
    automatically resolved to their most recent processed versions, whereas 
    `AphiaID_generatedby_isinworms` must be referenced by its full
    generated name.

#### Renaming a column and assigning a type

A nested mapping renames the column and assigns its final type. 
The outer key identifies the column available after processing. The nested key
defines its final name, and the associated value defines its output type.

When a column is listed without an explicit data type, its output type defaults 
to `string`.


!!! example

    ```yaml
    variables:

        - decimalLatitude:
            decimalLatitude: "float"
        - decimalLongitude:
            decimalLongitude: "float"
        - eventDate
        - AphiaID_generatedby_isinworms:
            AphiaID: "int"
    ```

At the end of processing, `marinedb` also creates a `marinedb_dtypes.json` file 
describing the data types of the final columns. This file can be reused to load 
the curated dataset later with the expected column types.

### Post-processing 

The `postprocessing` section contains operations that depend on results
produced earlier in the workflow. It is executed after the `processing`
section.

Post-processing operations include:

- interactive resolution of uncertain taxonomic matches
- filtering underrepresented taxa
- spatial subsampling of overrepresented taxa

!!! example

    ```yaml
    postprocessing:

    - tool:
        - resolvetaxamatch:
            review_level: 3

    - tool:
        - taxasubset:
            lowerbound: 50
            upperbound: 1000
            latkey: "decimalLatitude"
            lonkey: "decimalLongitude"
    ```

    Here, `resolvetaxamatch` uses the taxonomic matching results generated
    earlier in the workflow. `taxasubset` then uses the resulting species
    identifier to apply the requested occurrence thresholds.

When both lower- and upper-bound taxon processing are requested,
`taxasubset` applies the lower-bound operation first and passes its result to
the upper-bound operation.

## Selection and transformation modules

`marinedb` modules belong to two broad categories: selection modules and
transformation modules. Each module page documents the purpose of the
operation, its accepted parameters, its behavior, and its outputs.

### Selection module

Selection modules evaluate records against a condition and, depending on the
`flag` parameter, either annotate, retain or exclude records.

- With `flag=True`, all records are retained and the result of the test is
  stored in a Boolean column.
- With `flag=False`, records are retained or excluded directly, without
  creating a flag column.

!!! warning

    The exact filtering logic requires particular attention because it varies
    between selection modules. Depending on the operation, matching records
    may be retained or excluded when `flag=False`, and a `True` flag may
    indicate either a valid condition or an identified issue.

    The meaning of `flag=True` and `flag=False` is stated explicitly on each
    module page. Users should check the corresponding API reference before
    adding a selection operation to a workflow.

Some selection modules provide a `dropna` parameter. When direct filtering is
used (`flag=False`), this parameter controls whether records with missing
values in the evaluated field are also excluded. It generally has no effect
when `flag=True`.

!!! example

    The following operation retains all records and creates a Boolean flag
    column. The flag is `True` for records whose `class` value is `"Aves"` and
    `False` for records with any other non-missing value. Records with a missing 
    `class` value receive a missing flag.

    ```yaml
    processing:

        - class:
            - isin:
                values: "Aves"
                flag: true
    ```

!!! note
    Even when `flag=False` and no flag column is created, any processed or
    generated columns continue to follow the naming conventions described in
    [Column provenance](#column-provenance).

### Transformation modules

Transformation modules standardize, restructure, or otherwise modify data. 

Most provide an inplace option:

- `inplace=False` retains the source column and creates a processed column
- `inplace=True` replaces the source values with the processed result

!!! example

    The following operation maps values from `samplingProtocol` to standardized
    Darwin Core basis-of-record categories. Because `inplace=False`, the
    original `samplingProtocol` column is retained and the standardized values
    are stored in a new processed column.

    ```yaml
    processing:

        - samplingProtocol:
            - mapbasisofrecord:
                inplace: False
    ```

!!! warning
    Some modules necessarily discard records and therefore do not support this flexibility : 

    - the `marineloc` workflow always removes records identified as land-based
    - `taxasubset`, when used to subsample overrepresented taxa, necessarily removes excess observations

!!! note
    Even when `inplace=True` and the source column is replaced, the processed
    column is renamed to record the transformation according to the conventions
    described in [Column provenance](#column-provenance).

## Execution order

Modules may generally be listed in the desired processing order, but several operations 
follow fixed execution constraints. 

Dataset-specific preparation defined by the user in `format.py` is always performed first. 
When enabled, land-based record removal and `createwormsfilters` are then executed early 
in the workflow to improve processing efficiency.

Operations that depend on completed taxonomic harmonization must be placed in
postprocessing. These currently include `resolvetaxamatch` and `taxasubset`.

## Integrated workflows

Several high-level modules coordinate multiple lower-level operations and
manage the parameters and intermediate columns shared between them.

Examples include:

- `temporal`, which coordinates date parsing, interval processing, and
component extraction
- `isinworms`, which can invoke `createwormsfilters` and coordinate
WoRMS-based taxonomic harmonization
- `basisofrecordisin`, which can invoke `mapbasisofrecord` before evaluating
basis-of-record categories
- `taxasubset`, which coordinates lower- and upper-bound taxon processing

Using these integrated modules is recommended for standard workflows because
they apply their component stages in the intended order and reduce the risk of
incompatible settings.

## Large datasets

To accommodate large-scale datasets, the main `clean.py` workflow processes data 
iteratively in blocks 100,000 rows, rather than requiring the complete dataset to 
remain in memory. It also supports parallel execution.

Some individual modules implement their own parallel or distributed processing strategies. 
Their memory requirements and scalability limitations are documented on the corresponding 
module pages.

Not every operation is currently distributed. In particular, spatial
subsampling of overrepresented taxa requires the complete input dataset to fit
in memory. When the available memory is insufficient, that operation is
aborted and its input is returned unchanged.

## Software maturity and issue reporting

The modular design of `marinedb` allows many combinations of modules,
parameters, execution orders, and dataset structures. Only a limited subset of
these combinations has been tested so far.

As the package is applied to new datasets and workflows, previously undetected
errors, incompatible settings, or unexpected interactions between modules may
therefore emerge. This is particularly likely during the early stages of the
package's development.

Users are encouraged to report reproducible problems, unclear behavior, or
documentation gaps through the issue tracker. Reports should preferably
include:

- the `marinedb` latest commit used
- the Python version and operating environment
- the relevant section of the YAML configuration
- the complete error message or traceback
- a minimal example or description of the input data needed to reproduce the
  problem
- the expected and observed behavior

Users may also contact the maintainer directly.