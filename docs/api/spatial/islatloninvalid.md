# islatloninvalid

## API reference

<h3>
  <code>marinedb.tools.spatial.islatloninvalid</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/spatial/islatloninvalid.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.spatial.islatloninvalid.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - tool:
        - islatloninvalid:
            latkey: 'decimalLatitude'
            lonkey: 'decimalLongitude'
            flag: False
            dropna: True
    ```

!!! tip "Advanced usage"

    Use `isna` and `isboundedby` instead of `islatloninvalid` to apply
    missing-value and boundary checks separately to latitude and longitude. 
    See [Advanced utilities](advanced.md#advanced-utilities).