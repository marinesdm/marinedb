# contains

## API reference

<h3><code>marinedb.tools.contains</code></h3>

::: marinedb.tools.contains.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - flags:
        - contains:
            values:
              - 'NOT_MARINE'
              - 'ON_LAND'
            flag: True
            minimize_flagname: True
            flagname_mapping:
              'NOT_MARINE': 0
              'ON_LAND': 1
    ```