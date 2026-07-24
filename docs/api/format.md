# Input data requirements

Compatibility with `marinedb` requires input datasets to contain a small set of
fields in supported formats. When necessary, users can implement
dataset-specific adjustments in `format.py`, which is always executed before
the main curation workflow.

By isolating these preparatory transformations, `marinedb` retains a
general-purpose core while remaining flexible enough to accommodate
heterogeneous datasets.

Input datasets should meet the following requirements:

- **Coordinates**  
  Two columns must provide latitude and longitude in decimal degrees using the
  EPSG:4326 (WGS84) spatial reference system.

- **Scientific name**  
  A column containing the complete binomial scientific name, including both 
  genus and specific epithet, is required.

- **Higher taxonomic ranks**  
  When taxonomic harmonization is enabled, columns for higher taxonomic ranks
  must also be present, i.e., genus, family, order, class, phylum, and kingdom.

      These columns must exist, but their values may be left empty when authorship
  information is available, either in a dedicated column or appended to the
  scientific name.

- **Observation date**  
  When temporal processing is enabled, a column containing the observation 
  date is required.

      This column may be left empty when separate year, month, and day fields are
  available, as `marinedb` can reconstruct complete dates from those
  components.

## API reference

<h3>
  <code>marinedb.tools.format</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/format.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.format.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Basic usage

!!! example
    ```
    - tool:
        - format:
            dataset_name: 'jedi'
            overwrite: False
    ```