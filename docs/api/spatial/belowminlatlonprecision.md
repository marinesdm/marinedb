# belowminlatlonprecision

::: marinedb.tools.spatial.belowminlatlonprecision

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