#!/bin/bash

# Set variables

while [[ $# -gt 0 ]]; do

   key="$1"
   case $key in
      -f|--file)
          filename="$2"
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

if [[ -z ${columns+x} ]]; then
    echo "-c: Enter column number(s), the format must be number or number-number range, separated by commas"
    exit 1
fi

if [[ -z ${outputname+x} ]]; then
    DIR="$(dirname "${filename}")"
    outputname="$(basename "${filename}")"
    outputname="${DIR}/${outputname%.*}_split.txt"
    echo "-o ${outputname}_split will be the output file name"
fi

if [[ -z ${delimiter+x} ]] || [[ ${delimiter} == '\t' ]]; then
    delimiter="	" # tab delimiter
    echo "-d ${delimiter} will be the delimiter of the output file"
fi

# Keep ${columns} columns

cut -d "${delimiter}" -f "${columns}" "${filename}" > "${outputname}"

