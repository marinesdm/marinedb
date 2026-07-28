# taxasubset

## API reference

<h3>
  <code>marinedb.tools.taxonomic.taxasubset</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/taxonomic/taxasubset.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.taxonomic.taxasubset.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

### Related implementations

The lower- and upper-bound operations are implemented separately:

- <a href="{{ source_base_url }}/src/marinedb/tools/taxonomic/taxasubset_lowerbound.py?ref_type=heads"
     target="_blank"
     rel="noopener noreferrer">
    <code>taxasubset_lowerbound.py</code>
  </a>

- <a href="{{ source_base_url }}/src/marinedb/tools/taxonomic/taxasubset_upperbound.py?ref_type=heads"
     target="_blank"
     rel="noopener noreferrer">
    <code>taxasubset_upperbound.py</code>
  </a>

## Basic usage

!!! example
    ```
    - tool:
      - taxasubset:
          speciesidkey: 'lsid_generatedby_isinworms'
          latkey: 'decimalLatitude'
          lonkey: 'decimalLongitude'
          lowerbound: 50
          upperbound: 1000
          export_process: True
          export_type: 'gif'
    ```