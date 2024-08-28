#!/usr/bin/env python3

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
from urllib.error import HTTPError
import http


#WoRMS
wormscall = {
             'scientificname': 'species',
             'genus': 'genus',
             'family': 'family',
             'order': 'order',
             'cls': 'class',
             'phylum': 'phylum',
             'kingdom': 'kingdom',
             'match_type':'matchtype_species',
             'status': 'status',
             'valid_AphiaID':'valid_aphiaID',
             'isExtinct':'isExtinct'
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



def write_tsvfile(df, tsv_filename, init=False):

    print(f'            Storing in {tsv_filename} | {len(df)} observations')
    if init:
        df.to_csv(tsv_filename, mode='w', index=False, header=True, sep='\t')
    else:
        df.to_csv(tsv_filename, mode='a', index=False, header=False, sep='\t')

    return True



def get_uniqueSpecies(gzfile_path, store=False, outputpath='./', outputfile='species.tsv', overwrite=True):


    print(f'        ** Retrieving unique species from {gzfile_path}')


    if store and os.path.isfile(outputpath + outputfile):

        if overwrite:
            print(f"           WARNING | {outputpath + outputfile} already exists and will be overwritten")
        else:
            print(f"           INFO | {outputpath + outputfile} already exists and will be used")
            unique_species = list(pd.read_csv(outputpath + outputfile).values.flatten())
            return unique_species


    with gzip.open(gzfile_path,'r') as data:

        header = data.readline().decode("utf8").strip('\n').split('\t')
        species_index = header.index('species')

        unique_species = set()

        for idx, line in enumerate(data):

            species = line.decode("utf8").strip('\n').split('\t')[species_index]

            unique_species = update(unique_species,species)

            #Checkpoint

            if ((idx+1)%1000000)==0:
                print(f"           Processing | {idx + 1} lines done, {len(unique_species)} unique species")


    if store:
        print(f"           Storing in {outputpath + outputfile} [ {len(unique_species)} unique species")
        with open(outputpath + outputfile, 'w') as f:
            f.writelines('\n'.join(['species'] + list(unique_species)))


    return list(unique_species)



def _reconnect_matchAphiaRecordsByNames(scinames):

    global cl
    try:
        results = cl.service.matchAphiaRecordsByNames(scinames, marine_only="true")
    except (http.client.RemoteDisconnected, TimeoutError):
        cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
        _reconnect_matchAphiaRecordsByNames(scinames)

    return results


def match_ClassificationBySciname(species, wormscall=wormscall):

    print(f'            -- WoRMS API call --')
    scinames["scientificname"] = species

    results = _reconnect_matchAphiaRecordsByNames(scinames)

    wormscallK = list(wormscall.keys())
    wormscallV = list(itemgetter(*wormscallK)(wormscall))
    colnames = ['group'] + wormscallV

    classification = []

    print(f'            -- WoRMS/file match --')
    for idx,resultsBySciname in enumerate(results):

        if len(resultsBySciname)!=0:

            for taxon in resultsBySciname: 

                taxon = dict(items(taxon))
                classif = itemgetter(*wormscallK)(taxon)
                classification.append([species[idx]] + list(classif))

        else:

            classification.append([species[idx]] + [pd.NA]*len(wormscallK))


    classification = pd.DataFrame(classification, columns=colnames)


    return classification



def match_WoRMS(species, wormscall=wormscall, store=False, outputpath='./', outputfile='worms_matchfilter.tsv', overwrite=True):

    nspecies = len(species)
    print(f'        ** WoRMS filter (recognized marine taxa) | {nspecies} unique species')

    if os.path.isfile(outputpath + outputfile):

        if overwrite:
            print(f"           WARNING | {outputpath + outputfile} already exists and will be overwritten")
        else:
            print(f"           INFO | {outputpath + outputfile} already exists and will be used")
            matched_worms = pd.read_csv((outputpath + outputfile), sep='\t')
            return matched_worms


    nbatch = int(np.ceil(nspecies/50))
    for batch in range(nbatch):

        start_idx = batch*50
        if batch == (nbatch-1):
            end_idx = nspecies
        else:
            end_idx = start_idx + 50

        species_subset = species[start_idx:end_idx]
        classification = match_ClassificationBySciname(species_subset)

        if batch==0:
            matched_worms = classification
        else:
            matched_worms = pd.concat([matched_worms, classification], axis=0, ignore_index=True)

        # Display progress

        classification_print = classification.drop_duplicates(subset=['group'],keep='first')
        Nnomatch = len(classification_print[pd.isnull(classification_print["matchtype_species"])])
        Nmatch = len(classification_print[~pd.isnull(classification_print["matchtype_species"])])
        done = len(matched_worms['group'].unique())
        percentage_done = np.round(done/nspecies*100,2)
        print(f'            Processing | {done}/{nspecies} species done ({percentage_done}%): no_match={Nnomatch}, match={Nmatch}')

        # Save progress

        step = ((batch - 1)*50 + 50) + (end_idx-start_idx)
        if store and ((step%10000==0) or (batch==(nbatch-1))):

            matched_worms.loc[pd.isnull(matched_worms["matchtype_species"]),"matchtype_species"] = "nomatch"
            matched_worms["valid_aphiaID"] = matched_worms["valid_aphiaID"].astype('Int64')

            file = outputpath + outputfile
            write_tsvfile(matched_worms, file, init=True)

    matched_worms.loc[pd.isnull(matched_worms["matchtype_species"]),"matchtype_species"] = "nomatch"
    matched_worms["valid_aphiaID"] = matched_worms["valid_aphiaID"].astype('Int64')

    return matched_worms



def reconnect_getAphiaRecordsByIDs(aphiaID):

    global cl
    try:
        results = cl.service.getAphiaRecordsByIDs(aphiaID)
    except (http.client.RemoteDisconnected, TimeoutError):
        cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
        reconnect_getAphiaRecordsByIDs(aphiaID)

    return results


def get_AcceptedClassification(valid_aphiaID):

    aphiaID["aphiaids"] = valid_aphiaID
    results = reconnect_getAphiaRecordsByIDs(aphiaID)

    classification = []
    wormscallK = list(wormscall.keys())

    for idx, taxon in enumerate(results):

        classification.append([valid_aphiaID[idx]] + list(itemgetter(*wormscallK)(taxon)))

    classification = pd.DataFrame(classification, columns = ["group"] + list(itemgetter(*wormscallK)(wormscall)))

    return classification



def get_AcceptedWoRMS(valid_aphiaID, store=False, outputpath='./', outputfile='worms_acceptedfilter.tsv', overwrite=True):

    NaphiaID = len(valid_aphiaID)
    print(f'        ** WoRMS filter (accepted marine taxa) | {NaphiaID} unaccepted taxa')

    if os.path.isfile(outputpath + outputfile):

        if overwrite:
            print(f"           WARNING | {outputpath + outputfile} already exists and will be overwritten")
        else:
            print(f"           INFO | {outputpath + outputfile} already exists and will be used")
            accepted_worms = pd.read_csv((outputpath + outputfile), sep='\t')
            accepted_worms["valid_aphiaID"] = accepted_worms["valid_aphiaID"].astype('Int64')
            return accepted_worms


    #unaccepted_index = worms_filter[(worms_filter['status']!="accepted") & (~pd.isnull(worms_filter["aphiaID"]))].index
    #Nunaccepted = len(unaccepted_index)

    if NaphiaID!=0:

        nbatch = int(np.ceil(len(valid_aphiaID)/50))
        for batch in range(nbatch):

            start_idx = batch*50
            if batch == (nbatch-1):
                end_idx = NaphiaID
            else:
                end_idx = start_idx + 50

            #valid_aphiaID = list(worms_filter.loc[valid_aphiaID[start_idx:end_idx],"aphiaID"].values)
            #classification = get_AcceptedClassification(valid_aphiaID)
            classification = get_AcceptedClassification(valid_aphiaID[start_idx:end_idx])

            if batch==0:
                accepted_worms = classification
            else:
                accepted_worms = pd.concat([accepted_worms, classification], axis=0, ignore_index=True)

            done = len(accepted_worms)
            percentage_done = np.round(done/NaphiaID*100,2)
            print(f'            Processing | {done}/{NaphiaID} taxa done ({percentage_done}%)')

            step = ((batch - 1)*50 + 50) + (end_idx-start_idx)
            if store and ((step%10000==0) or (batch==(nbatch-1))):
                accepted_worms["valid_aphiaID"] = accepted_worms["valid_aphiaID"].astype('Int64')
                accepted_worms["group"] = accepted_worms["group"].astype('Int64')
                outputfile = outputpath + outputfile
                write_tsvfile(accepted_worms, outputfile, init=True)

    accepted_worms["valid_aphiaID"] = accepted_worms["valid_aphiaID"].astype('Int64')
    accepted_worms["group"] = accepted_worms["group"].astype('Int64')

    return accepted_worms



def get_WoRMSfilter(gzfile_path, store=False, outputpath='./', overwrite=True):

    # Get unique species

    unique_species = get_uniqueSpecies(gzfile_path, store=store, outputpath=outputpath, overwrite=overwrite)

    # Get WoRMS filter

    worms_matchfilter = match_WoRMS(unique_species, wormscall=wormscall, store=store, outputpath=outputpath, overwrite=overwrite)

    # Get accepted classifications

    worms_unaccepted = worms_matchfilter.loc[(worms_matchfilter['status']!="accepted") & (~pd.isnull(worms_matchfilter["valid_aphiaID"])), "valid_aphiaID"].unique().tolist()
    worms_acceptedfilter = get_AcceptedWoRMS(worms_unaccepted, store=store, outputpath=outputpath, overwrite=overwrite)

    return worms_matchfilter, worms_acceptedfilter



def _get_wormsfilter(unique_species):


    # Get WoRMS filter

    nspecies = len(unique_species)
    print(f'        ** WoRMS filter (recognized marine taxa) | {nspecies} unique species')
    

    #wormsranks = list(wormsrank_mapping.keys())
    #wormscall = wormsranks + ['match_type', 'status', 'valid_AphiaID']
    #worms2filter_mapping = list(itemgetter(*wormscall[:-3])(wormsrank_mapping)) + ["matchtype", "status"]
    #worms2filter_mapping = dict(zip(wormscall[:-1], worms2filter))
    #filter_colnames = list(itemgetter(*wormsranks)(wormsrank_mapping)) + ["matchtype_worms", "status", "valid_aphiaID"]

    #worms_filter = []
    #unaccepted_scinames = []


    nbatch = int(np.ceil(nspecies/50))
    for batch in range(nbatch):

        start_idx = batch*50
        if batch == (nbatch-1):
            end_idx = nspecies
        else:
            end_idx = start_idx + 50

        #species = pd.DataFrame(np.reshape(unique_species[start_idx:end_idx],(-1,1)), columns=RANK["species"])
        species = unique_species[start_idx:end_idx]
        #filtered, unaccepted = match_TaxaBySciname(taxa, wormscall, worms2filter_mapping)
        filter = match_ClassificationBySciname(species)
        #worms_filter = worms_filter | filtered
        
        #unaccepted_scinames = unaccepted_scinames + unaccepted
         
        if batch==0:
            worms_filter = filter
        else:
            worms_filter = pd.concat([worms_filter, filter], axis=0, ignore_index=True)

        Nnomatch = len(filter[pd.isnull(filter["matchtype_species"])])
        #Nmatch = len(filter) - Nnomatch
        Nmatch = len(filter[~pd.isnull(filter["matchtype_species"])])
        done = ((batch - 1)*50 + 50) + (end_idx-start_idx)
        percentage_done = np.round(done/nspecies*100,2)
        print(f'            Processing | {done}/{nspecies} species done ({percentage_done}%): no_match={Nnomatch}, match={Nmatch}')

    worms_filter.loc[pd.isnull(worms_filter["matchtype_species"]),"matchtype_species"] = "nomatch"
    worms_filter["valid_aphiaID"] = worms_filter["valid_aphiaID"].astype('Int64')


    # Get accepted classifications

    unaccepted_index = worms_filter[(worms_filter['status']!="accepted") & (~pd.isnull(worms_filter["valid_aphiaID"]))].index
    Nunaccepted = len(unaccepted_index)
    if len(unaccepted_index)!=0:

        print(f'        ** WoRMS filter (accepted marine taxa) | {Nunaccepted} unaccepted taxa')

        nbatch = int(np.ceil(len(unaccepted_index)/50))
        for batch in range(nbatch):

            start_idx = batch*50
            if batch == (nbatch-1):
                end_idx = Nunaccepted
            else:
                end_idx = start_idx + 50

            valid_aphiaID = worms_filter.loc[unaccepted_index[start_idx:end_idx],"valid_aphiaID"].tolist()
            classification = get_AcceptedClassification(valid_aphiaID)

            if batch==0:
                accepted_classification = classification
            else:
                accepted_classification = pd.concat([accepted_classification, classification], axis=0, ignore_index=True)

            done = ((batch - 1)*50 + 50) + (end_idx-start_idx)
            percentage_done = np.round(done/Nunaccepted*100,2)
            print(f'            Processing | {done}/{Nunaccepted} taxa done ({percentage_done}%)')


    return worms_filter, accepted_classification



if __name__ == '__main__':

    
    parser = argparse.ArgumentParser(description='Get WoRMS filter and accepted classification')
    parser.add_argument('gbif_tsv_gzfile', type=str, help='path to the tab-separated file from GBIF to be processed (must fit in RAM)')   
    parser.add_argument('--output_path', type=str, help='path to folder where output files will be stored', default='./')
    args = parser.parse_args()

    print(f'    * Creating the files needed for WoRMS filtering')
    
    start=time.time()

    #unique_species = get_uniqueSpecies(args.gbif_tsv_gzfile, store=True, outputpath=args.output_path)

    #worms_filter, worms_accepted = get_wormsfilter(unique_species)

    _ = get_WoRMSfilter(args.gbif_tsv_gzfile, store=True, outputpath=args.output_path, overwrite=False)
    
    #worms_matchfilter = pd.read_csv('/data/smartbiodiv/eberhocoi/worms_matchfilter.tsv',sep='\t')
    #worms_matchfilter['aphiaID'] = worms_matchfilter['aphiaID'].astype('Int64')
    # Get accepted classifications

    #worms_unaccepted = worms_matchfilter.loc[(worms_matchfilter['status']!="accepted") & (~pd.isnull(worms_matchfilter["aphiaID"])), "aphiaID"].tolist()
    #worms_acceptedfilter = get_AcceptedWoRMS(worms_unaccepted, store=True, outputpath=args.output_path)


    end=time.time()

    #filter_file = args.output_path + 'worms_filter.tsv'
    #accepted_file = args.output_path + 'worms_accepted.tsv'

    #print(f'        ** Storing {filter_file} | {len(worms_filter)} filtered species')
    #worms_filter.to_csv(filter_file, sep='\t', index=False)

    #print(f'        ** Storing {accepted_file} | {len(worms_accepted)} unaccepted species')
    #worms_accepted.to_csv(accepted_file, sep='\t', index=False)

    print(f'TIME : {np.round(end - start,0)}s')
