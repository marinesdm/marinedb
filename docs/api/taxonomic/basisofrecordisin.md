# basisofrecordisin

## API reference

<h3>
  <code>marinedb.tools.taxonomic.basisofrecordisin</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/taxonomic/basisofrecordisin.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.taxonomic.basisofrecordisin.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - samplingProtocol:
        - basisofrecordisin:
            std: True
            std_inplace: True
            values: ['OCCURRENCE']
            flag: True
    ```