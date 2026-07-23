# marineloc

## API reference

<h3><code>marinedb.tools.marineloc.marineloc</code></h3>

::: marinedb.tools.marineloc.marineloc.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - tool:
        - marineloc:
            latkey: 'decimalLatitude'
            lonkey: 'decimalLongitude'
            inputfile_format: 'pandas'
            parallel: True
    ```