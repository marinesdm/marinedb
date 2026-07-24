# marineloc

## API reference

<h3>
  <code>marinedb.tools.marineloc.marineloc</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/marineloc/marineloc.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

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