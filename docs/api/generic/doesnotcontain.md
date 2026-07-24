
# doesnotcontain

## API reference

<h3>
  <code>marinedb.tools.doesnotcontain</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/doesnotcontain.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.doesnotcontain.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - issue:
        - doesnotcontain:
            values:
              - 'COORDINATE_INVALID'
              - 'COORDINATE_OUT_OF_RANGE'
              - 'ZERO_COORDINATE'
            flag: False 
    ```