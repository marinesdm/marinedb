# island

## API reference

<h3><code>marinedb.tools.marineloc.island</code></h3>

::: marinedb.tools.marineloc.island.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false


## Command-line usage

```bash
python island.py INPUTDIR [OPTIONS]
```

### Arguments

``INPUTDIR``

Path to the directory containing the split files to process.

### Required options

``--latitude-column``, ``--latitude``

Name of the column containing latitude values.

``--longitude-column``, ``--longitude``

Names of the column containing longitude values. 

 ``--index-column``, ``--index``

Name of the column containing the record index.

### Optional options

``--control-column``, ``--control``

Name of an optional control column retained in the processed files to verify
record alignment during final filtering.

``--delimiter``

Field separator used in the input and output files. 

The default is a tab character. When specifying a tab explicitly 
from the terminal, enclose the escaped separator in quotes.

``--fileslist-path``, ``--fileslist``

Path to a text file listing the input files to process, with one file per line.

Relative file names are resolved within ``INPUTDIR``. If omitted, all files
directly contained in ``INPUTDIR`` are considered.

Providing a file list allows files to be assigned manually across machines,
but reduces fault tolerance if a machine stops before completing its assigned
files.

``--maskfile-path``, ``mask``

Path to a custom ``.npz`` land–sea–coast mask.

If omitted, the ``globe_mask_coastline.npz`` mask bundled with ``marinedb`` is
used.

``--outputdir-path``, ``outputdir``

Directory in which processed files are written. 
A ``processed`` subdirectory is added unless the supplied path 
already points to one. The default is the current directory.

For distributed computation, the resulting processed directory must be shared
by all participating machines so that each machine can detect files already
processed by the others.

``--parallel``, ``--no-parallel``

Whether to process several input files concurrently using multiple CPUs.

The default is ``--no-parallel``.

``--cpu``

Maximum number of CPUs used for local parallel processing. 

If omitted or set to -1, all CPUs available to the process are used. If
fewer files than CPUs are available, the number of workers is automatically
reduced to the number of files. A value of 1 disables parallel processing. 

``--store-time``, ``--no-store-time``

Whether to record the processing time for each input file.

The default is ``--store-time``.

``--store-stats``, ``--no-store-stats``

Whether to generate land–sea classification statistics for each input file.

The default is ``--store-stats``.

``--cluster-mode``, ``--no-cluster-mode``

Whether the script is being run as part of a workflow distributed across
multiple machines.

When enabled, parameter and progress messages are suppressed. The default is
``--no-cluster-mode``.

## Basic usage

!!! Example
    ```bash
    python split_pandas_parquet.py /path/to/split/directory  
        --latitude-column lat 
        --longitude-column lon 
        --index-column index 
        --control-column rank_species
        --delimiter ","  
        --parallel
    ```

## Distributed use

For classification across multiple machines, use [parallel_island.sh](parallel_island.md)