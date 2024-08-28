#!/bin/bash

# Set variables

while [[ $# -gt 0 ]]; do

   key="$1"
   case $key in
      -f|--file)
          filename="$2"
          shift 2
          ;;
      -l|--lines)
          lines="$2"
          shift 2
          ;;
      -c|--columns)
          columns="$2"
          shift 2
          ;;
      -o|--output)
          outputname="$2"
          shift 2
          ;;
      -d|--delimiter)
          delimiter="$2"
          shift 2
          ;;
      *)
          echo "Unrecognized option $key"
          exit 1
          ;;
   esac
done

if [[ -z ${filename+x} ]]; then
    echo "-f: Enter the name of the file to be split (must be tab-separated)"
    exit 1
fi

if [[ -z ${lines+x} ]]; then
    echo "-l: Enter the maximum number of lines per new file"
    exit 1
fi

if [[ -z ${columns+x} ]]; then
    echo "-c: Enter column number(s), the format must be number or number-number"
    exit 1
fi

DIR="$(dirname "${filename}")"
mkdir "${DIR}/split/"
if [[ -z ${outputname+x} ]]; then
    outputname="$(basename "${filename}")"
    outputname="${DIR}/split/${outputname%.*}" 
    echo "-o ${outputname}_split will be the prefix of the output file names"
else
    outputname="${DIR}/split/${outputname}"
fi

if [[ -z ${delimiter+x} ]]; then 
    delimiter="\t"
    echo "-d ${delimiter} will be the delimiter of the output file"
fi


# Keep ${columns} columns
#- delimiter: tabulation, use default -d for cut
#- latitude / longitude: columns 22-23 of GBIF file

cut -f "${columns}" "${filename}" > "${outputname}2split.tsv"

# Delete header & Add indexes
# -b a : number all lines, including empty lines
# -v 0 : first line number = 0
# -w 1 : column for line numbers = 1

sed 1d "${outputname}2split.tsv" | nl -w1 -b a -v 0 > "${outputname}2split_idx.tsv" 

# Split into ${lines}-line files

split -l "${lines}" --numeric-suffixes --verbose -a 4 "${outputname}2split_idx.tsv" "${outputname}_split"
rm "${outputname}2split_idx.tsv"

# Add a header to all new files

header="index\t$(head -n 1 ${outputname}2split.tsv)"
sed -i "1i$header" "${outputname}"_split*

if [[ ${delimiter} != '\t' ]]; then
    # Convert to ${delimiter}-separated value file
    sed -i "s/\t\+/${delimiter}/g" "${outputname}"_split* 
fi
