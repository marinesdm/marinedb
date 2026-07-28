# createwormsfilters

## API reference

<h3>
  <code>marinedb.tools.taxonomic.createwormsfilters</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/taxonomic/createwormsfilters.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.taxonomic.createwormsfilters.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
        - createwormsfilters:
            skip_uniques_rebuild: True
            wormscall:
              - 'AphiaID'
              - 'scientificname'
              - 'genus'
              - 'family'
              - 'order'
              - 'cls'
              - 'phylum'
              - 'kingdom'
              - 'match_type'
              - 'status'
              - 'valid_AphiaID'
              - 'lsid'
              - 'isMarine'
              - 'isBrackish'
              - 'authority'
            doublecheck: True
            overwrite: True
            resume: True
            parallel: True
            max_attempt: 20
    ```

## Lightweight WoRMS querying

`createwormsfilters` is intended for taxonomic harmonization workflows. In
addition to querying WoRMS, it extracts unique scientific names, preprocesses
input values, manages multiple candidate matches, and resolves unaccepted or
infraspecific names to species-level accepted names when possible.

For simpler use cases requiring only direct WoRMS matching of scientific
names, the package also includes the standalone `worms_match_by_sciname.py` 
script. This utility submits names directly to the WoRMS 
`AphiaRecordsByMatchNames` endpoint in batches and stores the returned
taxonomic and environmental information.

The output is written next to the input file using the suffix `_worms`. 
By default, the script requests marine and extant taxa only.

```bash
python worms_match_by_sciname.py INPUTFILE [OPTIONS]
```

### Arguments

``INPUTFILE``

Path to a tab-separated file containing a ``species`` column.

### Options

``--marine-only`` / ``--no-marine-only``

Whether to restrict WoRMS results to marine taxa. Enabled by default.

``--extant-only`` / ``--no-extant-only``

Whether to restrict WoRMS results to extant taxa. Enabled by default.
