# MarineDB: a Python package for curating marine occurrence data

This site contains the documentation for the *marinedb* package.

## Installation

`marinedb` is intended primarily for Linux environments. Windows users can run
it through the Windows Subsystem for Linux. 

!!! warning

    **Python 3.12 is currently strongly recommended.**

    Installation tests with more recent Python versions have exposed
    compatibility errors in some of the package versions currently required by
    `marinedb`. Support for newer Python versions and broader platform
    portability will be improved in future releases.

1. Clone the repository using SSH:

    ```bash
    git clone git@gitlab-research.centralesupelec.fr:smartbiodiv/sdm-data.git
    ```
    or HTTPS:

    ```bash
    git clone https://gitlab-research.centralesupelec.fr/smartbiodiv/sdm-data.git
    ```


2. Move to the repository root:
```bash
cd /path/to/sdm-data
```

3. Install the package in editable mode:
```bash
pip install -e .
```

    Editable installation links the Python environment to the local repository.
    Updates retrieved with `git pull` are therefore generally available without
    reinstalling `marinedb`. Reinstallation may still be required when package
    dependencies or installation settings change.

## Getting started

Curation workflows are defined in a YAML configuration file and executed with
`clean.py`. See the [API overview](api/index.md) for instructions on building
and running a complete workflow.

!!! warning "Early-stage software"

    `marinedb` is highly modular, and only a small fraction of the possible
    combinations of modules, parameters, execution orders, and input-data
    structures has been tested so far.

    During the early stages of the package's use, previously undetected errors
    may therefore appear when it is applied to new datasets or configurations.
    Users are encouraged to report unexpected behavior by opening an issue or
    contacting the maintainer.

## Sections

- [API overview](api/index.md)
- [Pre-processing](api/format.md)
- [Generic](api/generic/index.md)
- [Spatial](api/spatial/index.md)
- [Temporal](api/temporal/index.md)
- [Taxonomic](api/taxonomic/index.md)
