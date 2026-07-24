# isna

## API reference

<h3>
  <code>marinedb.tools.isna</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/isna.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

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
            nan_values: 'nd'
            stdnan_additional_policy: 'contains_digits'
    ```