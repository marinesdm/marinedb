#!/usr/bin/env python3r

import argparse
import gzip
import pandas as pd
import numpy as np
import time
import os

from operator import itemgetter

from suds import null, WebFault
from suds.client import Client
from suds.sudsobject import items
import http


#WoRMS
WORMSCALL = {
             'scientificname': 'species',
             'genus': 'genus',
             'family': 'family',
             'order': 'order',
             'cls': 'class',
             'phylum': 'phylum',
             'kingdom': 'kingdom',
             'match_type':'worms_matchtype',
             'status': 'worms_status',
             'valid_AphiaID':'valid_aphiaID',
             'isExtinct':'isextinct',
             'rank':'rank',
             'authority':'authority'
            }


cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)

scinames = cl.factory.create('scientificnames')
scinames["_arrayType"] = "string[]"

aphiaID = cl.factory.create("aphiaids")
aphiaID["_arrayType"] = "int[]"



def update(myset,key):

    if key == '':
        return myset

    else:

        try:
            if pd.isnull(float(key)):
                return myset
            else:
                myset.add(key)
                return myset

        except (ValueError,TypeError):
            if pd.isnull(key):
                return myset
            else:
                myset.add(key)
                return myset


def resume_process(filter, values):

    valuesprocessed = set(filter['group'].tolist())
    values2process = set(values) - valuesprocessed

    return list(values2process)


def write_tsvfile(df, tsv_filename, init=False):

    print(f'            Storing in {tsv_filename} | {len(df)} observations')
    if init:
        df.to_csv(tsv_filename, mode='w', index=False, header=True, sep='\t')
    else:
        df.to_csv(tsv_filename, mode='a', index=False, header=False, sep='\t')

    return True



def get_uniqueSpecies(gzfile_path, store=False, outputpath='./', outputfile='species.tsv', overwrite=False):


    print(f'            ** Retrieving unique species from {gzfile_path}')


    if store and os.path.isfile(outputpath + outputfile):

        if overwrite:
            print(f"            WARNING | {outputpath + outputfile} already exists and will be overwritten")
        else:
            print(f"            INFO | {outputpath + outputfile} already exists and will be used")
            unique_species = list(pd.read_csv(outputpath + outputfile).values.flatten())
            return unique_species


    with gzip.open(gzfile_path,'r') as data:

        header = data.readline().decode("utf8").strip('\n').split('\t')
        species_index = header.index('species')

        unique_species = set()

        for idx, line in enumerate(data):

            species = line.decode("utf8").strip('\n').split('\t')[species_index]

            unique_species = update(unique_species,species)

            # Display progress

            if ((idx+1)%1000000)==0:
                print(f"            Processing | {idx + 1} lines done, {len(unique_species)} unique species")

    # Save progress

    if store:
        print(f"            Storing in {outputpath + outputfile} [ {len(unique_species)} unique species")
        with open(outputpath + outputfile, 'w') as f:
            f.writelines('\n'.join(['species'] + list(unique_species)))


    return list(unique_species)



def process_rank_dirty(worms_dict):

    rank = worms_dict['rank'].lower()
    if rank!='species':
        if rank=='subspecies':
            name=worms_dict['scientificname'].split(' ')
            if len(name)>2:
                worms_dict['scientificname']=' '.join(name[:2])
                worms_dict['rank']='Species'
            else:
                print(f"WARNING | Unexpected subspecies name: {worms_dict['scientificname']}")
        else: #rank higher than species
            worms_dict['scientificname']=pd.NA

    return worms_dict


def process_rank(worms_dict):

    #other version: use "parentNameUsageID"

    rank = worms_dict['rank'].lower()
    if rank!='species':
        if rank=='subspecies':
            parent_aphiaID = worms_dict['parentNameUsageID']
            if not pd.isnull(parent_aphiaID):
                worms_dict['status']='subspecies'
                worms_dict['valid_AphiaID']=parent_aphiaID
            #else:
                #worms_dict=process_rank_dirty(worms_dict)
        else: #rank higher than species
            worms_dict['scientificname']=pd.NA

    return worms_dict


#def _reconnect_matchAphiaRecordsByNames(scinames):
#
#    global cl
#    try:
#        return cl.service.matchAphiaRecordsByNames(scinames, marine_only="true")
#    except (http.client.RemoteDisconnected, TimeoutError):
#        cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
#        return _reconnect_matchAphiaRecordsByNames(scinames)


def _connect_matchAphiaRecordsByNames(scinames, max_attempt=10, pause_duration=5):

    global cl

    attempt = 0
    while attempt < max_attempt:
        try:
            return cl.service.matchAphiaRecordsByNames(scinames, marine_only="true")
        except (http.client.RemoteDisconnected, TimeoutError):
            attempt += 1
            if attempt < max_attempt:
                time.sleep(pause_duration)
                cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
            else:
                raise


def match_ClassificationBySciname(species, wormscall=WORMSCALL):

    print(f'            -- WoRMS API call --')
    if isinstance(species,str):
        species=[species]
    scinames["scientificname"] = species

    results = _connect_matchAphiaRecordsByNames(scinames)

    wormscallK = list(wormscall.keys())
    wormscallV = list(itemgetter(*wormscallK)(wormscall))
    colnames = ['group'] + wormscallV

    classification = []

    print(f'            -- WoRMS/file match --')
    for idx,resultsBySciname in enumerate(results):

        if len(resultsBySciname)!=0:

            for taxon in resultsBySciname:

                taxon = dict(items(taxon))
                taxon = process_rank(taxon)
                classif = itemgetter(*wormscallK)(taxon)
                classification.append([species[idx]] + list(classif))

        else:

            classification.append([species[idx]] + [pd.NA]*len(wormscallK))


    classification = pd.DataFrame(classification, columns=colnames)


    return classification



def match_WoRMS(species, wormscall=WORMSCALL, store=False, outputpath='./', outputfile='worms_matchfilter.tsv', overwrite=False):

    nspecies_print = len(species)
    resume=False
    print(f'            ** WoRMS filter (recognized marine taxa) | {nspecies_print} unique species')

    if os.path.isfile(outputpath + outputfile):

        if overwrite:
            print(f"            WARNING | {outputpath + outputfile} already exists and will be overwritten")
        else:
            print(f"            INFO | {outputpath + outputfile} already exists and will be used")
            matched_worms = pd.read_csv((outputpath + outputfile), sep='\t')

            species = resume_process(matched_worms, species)

            if len(species)==0:
                return matched_worms
            else:
                print(f'            UPDATE | {len(species)}/{nspecies_print} ({np.round(len(species)/nspecies_print*100,2)}%) remaining species to be processed')
                resume=True

    nspecies = len(species)
    nbatch = int(np.ceil(nspecies/50))
    done = nspecies_print - nspecies
    for batch in range(nbatch):

        start_idx = batch*50
        if batch == (nbatch-1):
            end_idx = nspecies
        else:
            end_idx = start_idx + 50

        species_subset = species[start_idx:end_idx]
        classification = match_ClassificationBySciname(species_subset, wormscall=wormscall)

        if batch==0 and not resume:
            matched_worms = classification
        else:
            matched_worms = pd.concat([matched_worms, classification], axis=0, ignore_index=True)

        # Display progress

        classification_print = classification.drop_duplicates(subset=['group'],keep='first')
        Nnomatch = len(classification_print[pd.isnull(classification_print["worms_matchtype"])])
        Nmatch = len(classification_print[~pd.isnull(classification_print["worms_matchtype"])])
        #done = len(matched_worms['group'].unique())
        done = done + (end_idx - start_idx)
        percentage_done = np.round(done/nspecies_print*100,2)
        print(f'            Processing | {done}/{nspecies_print} species done ({percentage_done}%): no_match={Nnomatch}, match={Nmatch}')

        # Save progress

        step = ((batch - 1)*50 + 50) + (end_idx-start_idx)
        if store and ((step%10000==0) or (batch==(nbatch-1))):

            matched_worms.loc[pd.isnull(matched_worms["worms_matchtype"]),"worms_matchtype"] = "nomatch"

            if 'valid_aphiaID' in wormscall.keys():
                matched_worms["valid_aphiaID"] = matched_worms["valid_aphiaID"].astype('Int64')

            file = outputpath + outputfile
            write_tsvfile(matched_worms, file, init=True)

    matched_worms.loc[pd.isnull(matched_worms["worms_matchtype"]),"worms_matchtype"] = "nomatch"
    if 'valid_aphiaID' in wormscall.keys():
        matched_worms["valid_aphiaID"] = matched_worms["valid_aphiaID"].astype('Int64')

    return matched_worms



#def _reconnect_getAphiaRecordsByIDs(aphiaID):
#
#    global cl
#    try:
#        return cl.service.getAphiaRecordsByIDs(aphiaID)
#    except (http.client.RemoteDisconnected, TimeoutError):
#        cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
#        return _reconnect_getAphiaRecordsByIDs(aphiaID)

def _connect_getAphiaRecordsByIDs(aphiaID, max_attempt=10, pause_duration=5):

    global cl

    attempt = 0
    while attempt < max_attempt:
        try:
            return cl.service.getAphiaRecordsByIDs(aphiaID)
        except (http.client.RemoteDisconnected, TimeoutError):
            attempt += 1
            if attempt < max_attempt:
                time.sleep(pause_duration)
                cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
            else:
                raise


def get_AcceptedClassification(valid_aphiaID, wormscall=WORMSCALL):

    if isinstance(valid_aphiaID, int):
        valid_aphiaID=[valid_aphiaID]

    aphiaID["aphiaids"] = valid_aphiaID
    results = _connect_getAphiaRecordsByIDs(aphiaID)

    wormscallK = list(wormscall.keys())
    wormscallV = list(itemgetter(*wormscallK)(wormscall))
    colnames = ['group'] + wormscallV

    classification = []

    for idx, taxon in enumerate(results):

        taxon=process_rank(taxon)
        classif = itemgetter(*wormscallK)(taxon)
        classification.append([valid_aphiaID[idx]] + list(classif))

    classification = pd.DataFrame(classification, columns=colnames)

    return classification


def get_AcceptedWoRMS(valid_aphiaID, wormscall=WORMSCALL, store=False, outputpath='./', outputfile='worms_acceptedfilter.tsv', overwrite=False):

    NaphiaID_print = len(valid_aphiaID)
    resume=False
    print(f'            ** WoRMS filter (accepted marine taxa) | {NaphiaID_print} unaccepted taxa')

    if os.path.isfile(outputpath + outputfile):

        if overwrite:
            print(f"            WARNING | {outputpath + outputfile} already exists and will be overwritten")
        else:
            print(f"            INFO | {outputpath + outputfile} already exists and will be used")
            accepted_worms = pd.read_csv((outputpath + outputfile), sep='\t')
            accepted_worms["valid_aphiaID"] = accepted_worms["valid_aphiaID"].astype('Int64')

            valid_aphiaID = resume_process(accepted_worms, valid_aphiaID)

            if len(valid_aphiaID)==0:
                return accepted_worms
            else:
                print(f'            UPDATE | {len(valid_aphiaID)}/{NaphiaID_print} ({np.round(len(valid_aphiaID)/NaphiaID_print*100,2)}%) remaining unaccepted taxa to be processed')
                resume=True

    NaphiaID = len(valid_aphiaID)
    if NaphiaID!=0:

        nbatch = int(np.ceil(NaphiaID/50))
        for batch in range(nbatch):

            start_idx = batch*50
            if batch == (nbatch-1):
                end_idx = NaphiaID
            else:
                end_idx = start_idx + 50

            classification = get_AcceptedClassification(valid_aphiaID[start_idx:end_idx], wormscall=wormscall)

            if batch==0 and not resume:
                accepted_worms = classification
            else:
                accepted_worms = pd.concat([accepted_worms, classification], axis=0, ignore_index=True)

            # Display progress

            done = len(accepted_worms)
            percentage_done = np.round(done/NaphiaID_print*100,2)
            print(f'            Processing | {done}/{NaphiaID_print} taxa done ({percentage_done}%)')

            # Save progress

            step = ((batch - 1)*50 + 50) + (end_idx-start_idx)
            if store and ((step%10000==0) or (batch==(nbatch-1))):
                accepted_worms["valid_aphiaID"] = accepted_worms["valid_aphiaID"].astype('Int64')
                accepted_worms["group"] = accepted_worms["group"].astype('Int64')
                outputfile = outputpath + outputfile
                write_tsvfile(accepted_worms, outputfile, init=True)

    accepted_worms["valid_aphiaID"] = accepted_worms["valid_aphiaID"].astype('Int64')
    accepted_worms["group"] = accepted_worms["group"].astype('Int64')

    return accepted_worms



def get_WoRMSfilter(gzfile_path, wormscall=WORMSCALL, store=False, outputpath='./', overwrite=False):

    # Get unique species

    unique_species = get_uniqueSpecies(gzfile_path, store=store, outputpath=outputpath, overwrite=overwrite)

    # Get WoRMS filter

    worms_matchfilter = match_WoRMS(unique_species, wormscall=wormscall, store=store, outputpath=outputpath, overwrite=overwrite)

    # Process subspecies

    #worms_subspecies = worms_matchfilter.loc[worms_matchfilter['worms_status']=="subspecies"]

    # Get accepted classifications

   #boucle jusqu'à plus subspecies ?
    worms_unaccepted = worms_matchfilter.loc[(worms_matchfilter['worms_status']!="accepted") & (~pd.isnull(worms_matchfilter["valid_aphiaID"])), "valid_aphiaID"].unique().tolist()
    worms_acceptedfilter = get_AcceptedWoRMS(worms_unaccepted, wormscall=wormscall, store=store, outputpath=outputpath, overwrite=overwrite)


    return worms_matchfilter, worms_acceptedfilter



if __name__ == '__main__':


    parser = argparse.ArgumentParser(description='Get WoRMS filter and accepted classification')
    parser.add_argument('gbif_tsv_gzfile', type=str, help='path to the tab-separated file from GBIF to be processed')   
    parser.add_argument('--output_path', type=str, help='path to folder where output files will be stored', default='./')
    args = parser.parse_args()

    print(f'    * Creating the files needed for WoRMS filtering')

    start=time.time()

    _ = get_WoRMSfilter(args.gbif_tsv_gzfile, wormscall=WORMSCALL, store=True, outputpath=args.output_path, overwrite=False)

    end=time.time()

    print(f'TIME : {np.round(end - start,0)}s')
