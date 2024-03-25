# Data Pipeline for SDM

Code for retrieving all the data needed to train a Species Distribution Model (SDM).

## How to use

#### 1. Download data from the GBIF website (see [here](https://www.gbif.org/occurrence/search))  
   
**Filters**   
```
Has coordinate = True   
Has geospatial issue = False   
Basis of record = Observation ; Machine observation ; Human observation ; Material sample ; Occurrence      
```
**Output** Text file with a `.csv` extension (delimiter : tabulation)  
   
#### 2. Use `split_data.sh` if the file is too large, or to speed up the process  
   
**Command**
```
bash split_data.sh -n prefix_new_files gbif_file.csv nb_lines_per_new_file   
```
**Output** *N* new files with 3 columns: `index` | `decimalLatitude` | `decimalLongitude`      

#### 3. Use `get_mask.py` to create the land/sea/coast mask required for the next step   
   Requirements: `globe_combined_mask_compressed.npz`   
   
**Command**   
```
python get_mask.py
```
**Output** `globe_mask_coastline.npz` (0:land, 1:sea, 2:coast)     
   
#### 4. Use `parallel_is_land.sh` (or `is_land.py`) to identify locations in the ocean    
**Command**
```
parallel-ssh -h hosts_file -t 0 parallel_is_land.sh
```
**Output** *N* new files stored in `processed/` with 5 columns: `id_land` (True/False) | `latitude` | `longitude` | `mask` (0,1,2) | `index`
       
## Data

- GLOBE dataset
- GSHHS dataset
- GBIF database

## References

Karin, Todd. Global Land Mask. October 5, 2020. https://doi.org/10.5281/zenodo.4066722 (see [here](https://github.com/toddkarin/global-land-mask/tree/master))   
   
Basemap documentation (see [here](https://basemaptutorial.readthedocs.io/en/latest/utilities.html#is-land))

## Project status
Work in progress.
