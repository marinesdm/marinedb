# temporal

## API reference

<h3>
  <code>marinedb.tools.temporal.temporal</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/temporal/temporal.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.temporal.temporal.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - tool:
        - temporal:
            # parse dates
            datekey: 'eventDate'
            yearkey: 'year'
            monthkey: 'month'
            daykey: 'day'
            inplace_parse: True

            # process date intervals
            flag_interval: True
            drop_interval: False
            strategy_interval: 'overlap'
            inplace_interval: False
            
            # split dates
            split_date: 'all'
            drop_mismatch_split: True
            inplace_components_split: True
            inplace_date_split: True
            dropna_date: True
    ```
