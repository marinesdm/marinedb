# Land–sea filtering

This section documents the tools used to exclude land-based records from marine 
occurrence datasets.

The workflow consists of four main stages:

1. **File splitting**  
   The original occurrence file is divided into smaller files to limit memory
   use and enable parallel processing.

2. **Land–sea classification**  
   Each split file is processed to classify coordinates as located on land or
   at sea. Classification first uses a precomputed land–sea–coast mask, then
   resolves coastal locations using higher-resolution coastlines.

3. **Marine-filter creation**  
   The indices of records classified as marine are extracted into a dedicated
   filter file.

4. **Marine-record filtering**  
   The marine filter is applied to the original occurrence file to retain the
   complete records corresponding to marine locations.

Each stage is documented separately and can be run independently. The
integrated `marineloc.py` script chains these stages together to simplify
standard use. It can also reuse existing split files or an existing marine 
filter to continue the workflow from a later stage.

## Standard workflow

For a standard local run, `marineloc.py` performs the complete workflow.

Users generally only need to provide the original file format, the latitude
and longitude column names, and the appropriate field separator. An optional
control column can be used to verify record alignment during final filtering,
while coordinate classification can be parallelized locally across multiple
CPUs.

## Distributed classification

When land–sea classification must be distributed across multiple machines,
the complete workflow cannot initially be run through `marineloc.py`.
The classification stage must first be prepared and executed separately.

First, split the input file with `split_pandas_parquet.py`. If needed, create
a custom spatial mask with `createmask.py`. Then classify the resulting split
files with `island.py`, distributing this step across multiple machines with
`parallel_island.sh`.

All participating machines must have access to the same split files and must
write to the same processed output directory. Each machine shuffles the input 
file order before processing and skips files for which a processed output already 
exists. Shuffling reduces the likelihood that several machines start processing 
the same file simultaneously.

Occasional redundant processing remains possible because a file is detected as 
completed only after its output has been written. However, this approach favours 
fault tolerance. If a machine stops before completing a file, no processed output 
is written for that file, allowing another machine to process it later. 

Once distributed classification is complete, users can resume the configuration-based
workflow with `marineloc.py` by providing the original occurrence file and the
directories containing the original and processed split files. `marineloc.py`
then creates the marine filter, applies it to the original occurrence file,
and passes the resulting marine dataset to the next stage of the workflow.

## Tools

- [`split_pandas_parquet`](split_pandas_parquet.md) : split the original occurrence file
- [`island`](island.md) : classify split-file coordinates as land or sea
- [`parallel_island.sh`](parallel_island.md) : distribute land–sea
  classification across multiple machines
- [`createmarinefilter`](createmarinefilter.md) : create the marine filter
- [`filtermarinelocations`](filtermarinelocations.md) : apply the marine filter
  to the original occurrence file
- [`marineloc`](marineloc.md) : run or resume the integrated workflow