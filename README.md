# marinedb

`marinedb` is a modular Python package for curating large marine biodiversity
datasets for downstream ecological analyses, with a particular focus on 
Species Distribution Models (SDMs). The package provides taxonomic, temporal, spatial, 
and occurrence-data cleaning tools.

## Documentation

Full documentation is available at: https://marinesdm.github.io/marinedb/

The documentation includes: 

- installation and workflow configuration
- module-specific reference pages
- examples

## Installation

`marinedb` is primarily developed for Linux environments. Windows users can run it through the Windows Subsystem for Linux. 

**Python 3.12 is strongly recommended**.

1. Clone the repository using SSH:

    ```bash
    git clone git@github.com:marinesdm/marinedb.git
    ```
    or HTTPS:

    ```bash
    git clone https://github.com/marinesdm/marinedb.git
    ```

2. Move to the repository root:
```bash
cd /path/to/marinedb
```

3. Install the package in editable mode:
```bash
pip install -e .
```

## Getting started

Curation workflows are defined in a YAML configuration file and executed with
`clean.py`.

```bash
python clean.py CONFIG_FILE [OPTIONS]
```

For example:
```
python clean.py configuration/config_jedi.yaml --parallel --cleanup
```

See the [workflow overview](https://marinesdm.github.io/marinedb/api/) for instructions on building and running a complete workflow.

## Main capabilities

- taxonomic harmonization against WoRMS
- temporal parsing, validation, and standardization
- geographic-coordinate validation and marine-location filtering
- basis-of-record standardization and selection
- configurable filtering and annotation
- taxon-level record selection and spatial subsampling
- block-wise and optional parallel processing of large datasets

## Software maturity

`marinedb` is highly modular, and only a small fraction of the possible
combinations of modules, parameters, execution orders, and input-data
structures has been tested so far.

During the early stages of the package's use, previously undetected errors may
therefore appear when it is applied to new datasets or configurations. Users
are encouraged to report unexpected behavior by opening an issue or contacting
the maintainer.

## License

This project is licensed under the [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

## Citation

Citation information will be provided with the first archived release.
