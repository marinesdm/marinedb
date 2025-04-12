#!/bin/bash

# Use this script to execute `island.py` across multiple machines with the command:
# `nice parallel-ssh -h [hosts_file] -t 0 parallel_is_land.sh [args]`,
# where `hosts_file` lists the available machines.

# Providing the same arguments to all machines — including the list of files
# to process — is intentional: since all machines attempt to process all files,
# the workflow is more robust. If the process is interrupted on one machine,
# all files will still eventually be processed by the others.

# To limit redundancy and prevent two machines from processing the same file simultaneously,
# `island.py` checks whether a file has already been processed before proceeding. However,
# since processing time per file is relatively high, this check does not fully eliminate
# the possibility of overlap. You can monitor progress using the `display_progress()` function
# and terminate the process once all files have been processed.

while [[ $# -gt 0 ]]; do

   key="$1"
   case $key in
      --inputdir)
          inputdir="$2"
          shift 2
          ;;
      --latitude)
          latitude="$2"
          shift 2
          ;;
      --longitude)
          longitude="$2"
          shift 2
          ;;
      --index)
          index="$2"
          shift 2
          ;;
      -d|--delimiter)
          delimiter="$2"
          shift 2
          ;;
      --fileslist)
          fileslist="$2"
          shift 2
          ;;
      --cpu)
          cpu="$2"
          shift 2
          ;;
      --outputdir)
          outputdir="$2"
          shift 2
          ;;
      *)
          echo "Unrecognized option $key"
          exit 1
          ;;
   esac
done

if [[ -z ${inputdir+x} ]]; then
    echo "--inputdir: Enter the path to the directory containing the files to be processed"
    exit 1
fi

if [[ -z ${latitude+x} ]]; then
    echo "--latitude: Enter the latitude column name"
    exit 1
fi

if [[ -z ${longitude+x} ]]; then
    echo "--longitude: Enter the longitude column name"
    exit 1
fi

if [[ -z ${index+x} ]]; then
    echo "--index: Enter the index column name"
    exit 1
fi

if [[ -z ${delimiter+x} ]]; then
    delimiter="	"
fi

if [[ -z ${fileslist+x} ]]; then
    fileslist=""
fi

if [[ -z ${cpu+x} ]]; then
    cpu=-1
fi

if [[ -z ${outputdir+x} ]]; then
    outputdir=""
fi

python3 island.py "${inputdir}" --latitude_column "${latitude}" --longitude_column "${longitude}" --index_column "${index}" --files_list_path "${fileslist}" --delimiter "${delimiter}" --cpu "${cpu}" --outputdir_path "${outputdir}"
