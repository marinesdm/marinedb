# split_pandas_parquet

## API reference

<h3>
  <code>marinedb.tools.marineloc.split_pandas_parquet</code> 
  <a href="{{ source_base_url }}/src/marinedb/tools/marineloc/split_pandas_parquet.py?ref_type=heads" 
     target="_blank" 
     rel="noopener noreferrer"
     style="font-weight:normal;font-size:0.8em;">[source]</a>
</h3> 

::: marinedb.tools.marineloc.split_pandas_parquet.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## Command-line usage

```bash
python split_pandas_parquet.py INPUTFILE [OPTIONS]
```

### Arguments

``INPUTFILE``

Path to the file to split.

### Options

``--split-type``

Splitting method to use. Accepted values are:  

- ``pandas`` for formats supported by ``pandas.read_csv``; 

- ``parquet`` for Parquet files;  

- ``uncompressed_gzip`` for plain-text or gzip-compressed files.  

If omitted, the available methods are attempted successively.

``--columns``

Names of the columns to retain in the split files. 

Provide the column names separated by spaces. 
If omitted, all columns are retained. 
An ``index`` column is always included, either selected from the input file or created. 

``--delimiter``

Field separator used in text-based input files. 
The default is a tab character. When specifying a tab explicitly from the terminal, 
enclose the escaped separator in quotes.

``--chunksize``

Maximum number of rows written to each split file. The default is 100,000. 

``--outputdir``

Directory in which to write the split files. A ``split`` subdirectory is added 
unless the supplied path already points to a ``split`` directory. 
The default is the current directory.

## Basic usage

!!! Example
    ```bash
    python split_pandas_parquet.py /path/to/JeDI.csv 
        --split-type "pandas" 
        --columns lat lon rank_species 
        --delimiter "," 
        --outputdir /path/to/output/directory
    ```



