#!/bin/bash

# Warning:
# Only non-compressed files can be split using this script,
# which assumes sufficient disk space is available to store
# the uncompressed file during execution

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
      -o|--outputfile)
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
    echo "-c: Enter column number(s), the expected format is: number[-number][,number[-number]]... (e.g. '1-2,7,9-12')"
    exit 1
fi

echo "* Parameters"
DIR="$(dirname "${filename}")"
mkdir "${DIR}/split/"
if [[ -z ${outputname+x} ]]; then
    outputname="$(basename "${filename}")"
    outputname="${DIR}/split/${outputname%.*}"
    echo "-o ${outputname}_split will be the prefix of the output file names"
else
    outputname="${DIR}/split/${outputname}"
fi

if [[ -z ${delimiter+x} ]] || [[ ${delimiter} == '\t' ]]; then
    #delimiter=$'\t'
    delimiter="	"
    echo "-d ${delimiter} will be the delimiter of the output file"
fi


# Keep ${columns} columns
# note:
# - GBIF interpreted file: latitude and longitude correspond to columns 22 & 23
# - GBIF interpreted file: the delimiter is a tabulation

echo "* Extract column(s) ${columns}"
cut -d "${delimiter}" -f "${columns}" "${filename}" > "${outputname}2split"

# Delete header & Add indexes
# -b a : number all lines, including empty lines
# -v 0 : start line numbering at 0
# -w 1 : use 1 column for line numbers

echo "* Temporarily remove the header"
echo "* Add a column containing row indices"
sed 1d "${outputname}2split" | nl -w 1 -b a -v 0 > "${outputname}2split_idx"

# Split into ${lines}-line files

echo "* Split into ${lines}-line(s) files"
split -l "${lines}" --numeric-suffixes --verbose -a 4 "${outputname}2split_idx" "${outputname}_split"
rm "${outputname}2split_idx"

# Add a header to all new files

echo "* Add the header to all new files"
header="index	$(head -n 1 ${outputname}2split)"
sed -i "1i$header" "${outputname}"_split*
rm "${outputname}2split"

if [[ ${delimiter} != '\t' ]]; then
    # Convert to ${delimiter}-separated value file
    sed -i "s/\t/${delimiter}/g" "${outputname}"_split*
    # or see tr command
fi
