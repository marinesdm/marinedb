# islatlonzero

::: marinedb.tools.spatial.islatlonzero

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