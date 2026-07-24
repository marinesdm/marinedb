# belowminlatlonprecision

## API reference

<h3>
  <code>marinedb.tools.spatial.belowminlatlonprecision</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/spatial/belowminlatlonprecision.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.spatial.belowminlatlonprecision.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - tool:
        - belowminlatlonprecision:
            latkey: 'decimalLatitude'
            lonkey: 'decimalLongitude'
            value: 2
            flag: False
            dropna: True
    ```

!!! tip "Advanced usage"

    Use `belowminfloatprecision` instead of `belowminlatlonprecision` to assess
    latitude and longitude precision separately. See
    [Advanced utilities](advanced.md#belowminfloatprecision).