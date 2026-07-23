# islatlonzero

## API reference

<h3><code>marinedb.tools.spatial.islatlonzero</code></h3>

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