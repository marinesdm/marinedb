# Distributed land–sea classification

`parallel_island.sh` runs the land–sea classification stage across multiple
machines using `parallel-ssh`. Each machine receives the same processing
arguments and must have access to the same split input files and processed
output directory.

The script launches `island.py` with local parallel processing enabled on each
machine. Within each machine, several split files may therefore be classified
concurrently using the number of CPUs specified by `--cpu`.

!!! warning

    All participating machines must write to the same processed output
    directory. This allows each machine to detect files already completed by
    the others and is required for coordinated distributed processing.

## Processing behavior

When no file list is supplied, each machine considers all files in the split
input directory. `island.py` shuffles the file order independently on each
machine and skips input files for which a processed output already exists.

This reduces the likelihood that multiple machines process the same file
simultaneously while preserving fault tolerance. If a machine stops before
writing its output, the unfinished file remains available for another machine
to process.

Because a file is detected as completed only after its output has been
written, occasional redundant processing remains possible, particularly near
the end of the file pool.

## Requirements

The following resources must be accessible from every node:

- the `marinedb` installation and its dependencies;
- the split input files;
- the optional custom mask and file list;
- the shared processed output directory;
- `parallel-ssh` on the machine from which the command is launched.

File paths passed to the script must resolve correctly on every machine.
Using identical mounted paths is recommended.

## Arguments 

``--inputdir``

Path to the directory containing the split files to classify.

This argument is required.

``--latitude``

Name of the latitude column.

This argument is required.

``--longitude``

Name of the longitude column.

This argument is required.

``--index``

Name of the record-index column.

This argument is required.

``--control``

Name of an optional control column retained to verify record alignment during
the final filtering stage.

``-d``, ``--delimiter``

Field separator used in the split and processed files.

The default is a tab character. When specifying a tab explicitly in Bash,
$'\t' is recommended.

``--fileslist``

Path to an optional text file listing the split files to process, with one file
per line.

``--maskfile``

Path to an optional custom ``.npz`` land–sea–coast mask.

When omitted, the mask bundled with marinedb is used.

``--outputdir``

Base output directory used by island.py.

This directory must be shared by all machines.

``--cpu``

Maximum number of CPUs used by island.py on each machine.

The default is -1, which uses all CPUs available to the process. The number
of workers is automatically reduced when fewer files are available.

## Basic usage

!!! Example
    ```bash
    nice parallel-ssh \
        -h hosts.txt \
        -t 0 \
        parallel_island.sh \
        --inputdir marinedb/split \
        --latitude latitude \
        --longitude longitude \
        --index index \
        --control scientificName \
        --outputdir /shared/marinedb/processed \
        --cpu 8
    ```

``hosts.txt`` must contain the host names or addresses of the participating
machines, one per line.

The ``-t 0`` option disables the ``parallel-ssh`` timeout. ``nice`` lowers the
scheduling priority of the launcher process.

## Output

Each processed file is written using the naming pattern: ``<input_filename>_<hostname>``. 
The hostname suffix identifies the machine that produced the file.

Timing and classification-statistics reports are generated according to the
options configured in ``island.py``.

## Resuming interrupted processing

The same command may be run again after an interruption. Files with existing
processed outputs are skipped, while incomplete files remain available for
processing. The workflow can therefore resume without restarting from scratch.
