# doeslateqlon

## API reference

<h3>
  <code>marinedb.tools.spatial.doeslateqlon</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/spatial/doeslateqlon.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.spatial.doeslateqlon.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - tool:
        - doeslateqlon:
            latkey: 'decimalLatitude'
            lonkey: 'decimalLongitude'
            flag: False
            dropna: True
    ```
