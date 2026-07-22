# doesnotcontain

::: marinedb.tools.contains

!!! example
    ```
    - flags:
        - contains:
            values:
              - 'NOT_MARINE'
              - 'ON_LAND'
            flag: True
            minimize_flagname: True
            flagname_mapping:
              'NOT_MARINE': 0
              'ON_LAND': 1
    ```