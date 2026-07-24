# contains

## API reference

<h3>
  <code>marinedb.tools.contains</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/contains.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

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