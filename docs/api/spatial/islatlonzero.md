# islatlonzero

## API reference

<h3>
  <code>marinedb.tools.spatial.islatlonzero</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/spatial/islatlonzero.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.spatial.islatlonzero.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - tool:
        - islatlonzero:
            latkey: 'decimalLatitude'
            lonkey: 'decimalLongitude'
            flag: False
            dropna: True
    ```

!!! tip "Advanced usage"

    Use `iszero` instead of `islatlonzero` to flag latitude and longitude
    separately. See [Advanced utilities](advanced.md#iszero).