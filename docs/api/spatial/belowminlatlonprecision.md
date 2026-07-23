# belowminlatlonprecision

## API reference

<h3><code>marinedb.tools.spatial.belowminlatlonprecision</code></h3>

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