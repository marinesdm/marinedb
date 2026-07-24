# isboundedby

## API reference

<h3>
  <code>marinedb.tools.isboundedby</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/isboundedby.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.isboundedby.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - year:
        - isboundedby:
            operator: '<'
            value: 1950
            flag: True
    ```