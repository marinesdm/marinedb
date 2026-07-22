# islatloninvalid

::: marinedb.tools.spatial.islatloninvalid

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