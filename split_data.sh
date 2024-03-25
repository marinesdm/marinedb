#!/bin/bash

dataset_name="data" 

# Set variables

while [[ $# -gt 0 ]]; do 

   key="$1"                      
   case $key in
      -n) dataset_name="$2"
          shift 2
          ;;
      *) if [[ $key = *.csv ]]; then 
             file_name="$key"
         elif [[ $key == ?(-)+([0-9]) ]]; then 
             nb_line="$key"
         else 
              echo "Unrecognized option $key"
              exit 1
         fi
         shift
         ;;
   esac
done

if [[ -z ${file_name+x} ]]; then 
    echo "Enter the name of the file to be split (must have a csv extension)"
    exit 1
fi

if [[ -z ${nb_line+x} ]]; then 
    echo "Enter the maximum number of lines per new file"
    exit 1
fi

# Keep latitude/longitude columns
# GBIF data: 
#- delimiter: tabulation, use default -d for cut
#- latitude / longitude: columns 22-23

cut -f 22-23 "${file_name}" > "${dataset_name}_locations.csv"

# Delete header & Add indexes

sed 1d "${dataset_name}_locations.csv" | nl -w1 -s"," > "${dataset_name}_locations_idx.csv" 

# Split into nb_lines-line files

split -l "${nb_line}" --numeric-suffixes --verbose -a 4 "${dataset_name}_locations_idx.csv" "${dataset_name}_split"
rm "${dataset_name}_locations_idx.csv"

# Add a header to all new files

header="index,$(head -n 1 ${dataset_name}_locations.csv)"
sed -i "1i$header" "${dataset_name}"_split*

# Convert to comma-separated value file

sed -i 's/\t\+/,/g' "${dataset_name}"_split* 

# Add a .csv extension (unnecessary)

#find . -name "*_split*" -exec mv {} {}.csv \; 
