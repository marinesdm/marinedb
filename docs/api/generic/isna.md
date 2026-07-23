# isna

## API reference

<h3><code>marinedb.tools.contains</code></h3>

::: marinedb.tools.isna.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - verbatimDepth:
        - isna:
            flag: True
            stdnan: True
            nan_values='nd'
            stdnan_additional_policy: 'contains_digits'
    ```