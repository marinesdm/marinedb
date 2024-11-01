#!/usr/bin/env python3r

# External import

import argparse
import gzip
import pandas as pd
import numpy as np
import yaml
import time
import os

from operator import itemgetter
import re

from suds import null, WebFault
from suds.client import Client
from suds.sudsobject import items
import http

# Internal import

from marinedb.filters import subsetranks

PATH = os.path.dirname(os.path.abspath(__file__))

# WoRMS call
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

def _standardize_singleSciname(sciname):

    issue=False
    next=False

    # Do not proceed with the code if hybrid name
    # e.g. "Branta hutchinsii x Branta leucopsis"

    if re.search(r'(^|\s)x(\s|$)|×',sciname):
        return sciname, issue, next

    # Convert uppercase words to lowercase
    # (not always a problem for WoRMS but necessary for the next step)
    # e.g. "HALICLONA (RHIZONERIA) VISCOSA" to "haliclona (rhizoneria) viscosa"

    #pattern = r'([A-Z]{2,})'
    #sciname = re.sub(pattern, lambda m: m.group(0).lower(), sciname)

    # Remove special characters at the beginning of `sciname`
    # including parenthesis and quotation marks

    pattern = r'^[^a-zA-Z]+'
    sciname = re.sub(pattern,'',sciname)

    # Check for the presence of a string in parentheses that could correspond to a subgenus or a superspecies
    # and that does not match the pattern (r'[A-Z][a-z]{2,}')
    # e.g. "Charadrius (charadrius) ruficapillus"
    # Check for consecutive strings in parentheses or for consecutive strings in square brackets
    # followed by strings not in parentheses
    # if one of these conditions is met, WoRMS cannot process the string properly
    # try again without the string(s) in parentheses

    if re.search(r'^[a-zA-Z]*\s*\((?![A-Z][a-z]{2,}\))',sciname):
        issue=True
    elif re.search(r'(([\[(].*?[\])]\s*){2,}|([\[{].*?[\]}]\s*))[a-z]',sciname): #EN FAIT ÇA ÇA N'A PAS L'AIR DE POSER PROBLÈME ... le problème c'est quand minuscules sans parethèses
        issue=True

    # Delete everything in parentheses
    # e.g. "Haliclona (Rhizoniera) viscosa"
    # e.g. "Cygnus olor (Gmelin, 1789)"

    pattern = r'\(.*?(\)|$)|\[.*?(\]|$)'
    sciname = re.sub(pattern,' ', sciname)

    # Delete the words in ignoreWords.yaml
    # e.g. "Leccinum scabrum sl, incl. cyaneobasileucum, melaneum"
    # e.g. "Dactylorhiza incarnatavar.lobelii"
    # e.g. "Makaira spp"
    # e.g. "Tambja cf. verconis"

    sciname_withIgnoreWords = sciname

    with open(os.path.join(PATH,'ignoreWords.yaml'),'r') as f:
        file = yaml.safe_load(f)
        ignoreWordsIn = file['SCN_IGNORE'] + file['AUTHORSHIP_IGNORE']

    ignoreWordsIn = sorted(ignoreWordsIn, key=len, reverse=True)
    ignoreWordsIn = '|'.join([fr'{word}' for word in ignoreWordsIn])
    pattern1 = fr'(?<=\s|\.)({ignoreWordsIn})([^a-zA-Z]|$)' #e.g. " sl,", " incl.", "s.l."
    pattern2 = fr'({ignoreWordsIn})(\.)' #e.g. "incarnatavar.lobelii"
    sciname = re.sub(fr'{pattern1}|{pattern2}', ' ', sciname)

    # Remove special characters

    #ATTENTION METTRE ISSUE SI "?" !!

    pattern = r'[^a-zA-Z\s\-]' #e.g. do not remove "-" in "Blechnum novae-zelandiae", remove date
    sciname = re.sub(pattern,' ',sciname).strip()
    sciname_withIgnoreWords = re.sub(pattern,' ',sciname_withIgnoreWords).strip()

    # Standardize whitespace

    sciname = re.sub(r'\s+',' ',sciname)
    sciname_withIgnoreWords = re.sub(r'\s+',' ',sciname_withIgnoreWords)

    #cappattern = re.compile(r'.*?(?=[A-Z]|$)')

    # Do not proceed with the code if the (first) scientific name is:
    # - already standardized
    # - and defined at species level
    # assumption: if several species are listed for an occurrence and the first one is not marine,
    # the others won't be either

    # PROBLEME : Centaurea nigra sens. lat. (=nigra/debeauxii), Mesapamea secalis agg., Rusa timorensis (de Blainville, 1822) ?, Nocardioides sp. MMH1-2, Pelagic octopoda sp1 (ajouter pelagic aux mots)
#Cuspidaria sp. sp., Bivalvia inc. sed., Lepidotrigla cf grandis (A) [Gomon, pers comm], Clausinella fasciata (da Costa, 1778), Bodotriidae sp12 c8 cs, auteur avec van aussi ? => revoir genre à 2 lettres,
# ou spprimer moins de 4 lettres ailleurs qu'en première position ?

    #if (len(sciname)==0) or (sciname[0].isupper()): #empty string or capitalized

    if not sciname[0].isupper()

    sciname_split = re.split(r'\s',sciname)

    if len(sciname_split)==1: #empty string or rank higher than species

        next=True

    else:

        if len(sciname)!=len(sciname_withIgnoreWords): #taxonomic abbreviations/terms

            issue=True

    return sciname, issue, next


def _standardize_scinames(raw_scinames): #REFAIRE et process directement, ne pas donner la chaîne brute, ce sera moins coûteux et complexe finalement


    if (pd.isnull(raw_scinames)) or (len(raw_scinames)==0):
        return False

    # Standardize whitespace

    scinames2process = re.sub(r'\s+',' ',raw_scinames)

    # Check for the prsence of "?"

    isquestionmark = re.search(r'\?',raw_scinames)

    # Check for the presence of a lowercase string not preceded by a special character
    # anywhere other than at the beginning of `raw_scinames`
    # e.g. Clupea harengus/Sprattus sprattus
    # e.g. Prosthechea cochleata (L.) W.E.Higgins var. grandiflora (Mutel) Christenson

    truncated_scinames = ' '.join(re.split(r'\s',raw_scinames)[3:])
    lwrc_match = re.search(r'([\s\"\']|^)[a-z]+',truncated_scinames)
    if lwrc_match:
        lwrc_start = lwrc_match.start()
        spec_match = re.search(r'\s[^a-zA-Z0-9"\']+?\s',raw_scinames)
        if spec_match:
            if spec_match.start()<lwrc_start:
                islowercase=False
            else:
                islowercase=True
    else:
        islowercase=False


    # Convert uppercase words so that only the first letter is capitalised
    # (not always a problem for WoRMS, but necessary at a later stage)
    # assumption: when an uppercase word and a lowercase word are joined,
    # the uppercase at the intersection is considered to belong to the uppercase word
    # and the two words are considered separately (i.e as two distinct items in the list below)
    # (WoRMS seems more robust to the absence of a letter at the end of a word
    # than to the addition of a letter at the beginning, moreover,
    # we will only consider the next item in the list if the first is not defined at species level)
    # e.g. "HALICLONA (RHIZONERIA) VISCOSA" to "Haliclona (rhizoneria) viscosa"
    # e.g. "HALICLONA VISCOSAsardina pilchardus" to "Haliclona viscosa Sardina pilchardus"
    # e.g. "HALICLONA VISCOSASardina pilchardus" to "Haliclona viscosas Ardina pilchardus"

    #Ncaps = len(re.findall(r'[A-Z]',raw_scinames))

    #pattern = r'((?<=[A-Z])[A-Z]+(?:[\s\-]+[A-Z]+)*)'
    #pattern = r'((?<=[A-Z])[A-Z][^a-z]*?)([A-Z]?[a-z]|$)'
    pattern = r'((?<=[A-Z])[A-Z][^a-z]*?)([a-z]|$)'
    scinames2process, Ncaps = re.subn(pattern, lambda m: (m.group(1).lower() + ' ' + m.group(2).upper()), scinames2process)
    print(scinames2process)

    if Ncaps>0:
        isallcaps=True

    # Split by +, |, /, \ and capital letters (unless preceded by an opening parenthesis (see below))
    # e.g. "Tringa (Heteroscelus) brevipesEopsaltria (Eopsaltria) griseogularis"
    # e.g. "Clupea harengus/Sprattus sprattus"
    # e.g. "Branta hutchinsii x Branta leucopsis"
    # e.g. "Populus nigra + Populus x canadensis"

    #pattern = r'[+|/\\]|(?<=[^\[(])(?<![A-Z])(?=[A-Z])'
    pattern = r'[+|/\\]|(?<=[^\[(])(?=[A-Z])'
    #pattern = r'[+|/\\]|(?<![A-Z]{2}\s)(?<=[^\[(A-Z])(?=[A-Z])|(?<=[A-Z]{2})\s?(?=[a-z])'
    #pattern = r'[+|/\\]|(?<![A-Z]{2})(?:[^a-zA-Z])*?(?<![\[(A-Z])(?=[A-Z])|(?<=[A-Z]{2})[^a-zA-Z]*?(?=[a-z])'
    scinames2process = re.split(pattern, scinames2process)
    if isallcaps:
        sciname_withAllCaps = re.split(pattern, raw_scinames)[0]
    print(scinames2process)

    try_again=True
    new_candidate=False
    idx=0

    while (try_again) and (not new_candidate) and (idx<len(scinames2process)):

        # Standardize the scientific name

        sciname = scinames2process[idx]

        if len(sciname)>5:

            sciname, issue, next = _standardize_singleSciname(sciname)
            print(sciname)
            if next:
                idx+=1

            elif idx==0:
                if issue:
                    new_candidate=True
                if isallcaps:
                    if scinames2process[idx]==sciname_withAllCaps:
                        print('HERE')
                        try_again=False
                    else:
                        new_candidate=True
                if islowercase:

                else:
                    try_again=False

            else:
                new_candidate=True

        else:

            idx+=1

    if try_again and new_candidate:
        return sciname
    else:
        return ''


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

            for taxon in resultsBySciname: #may be more than one candidate

                taxon = dict(items(taxon))
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


def _process_rank(worms_dict):

    rank = worms_dict['rank'].lower()
    lowerthanspecies = subsetranks.apply('species', lower=True, strict=True)

    if rank!='species':

        if rank in lowerthanspecies:

            parent_aphiaID = worms_dict['parentNameUsageID']

            if not pd.isnull(parent_aphiaID):
                worms_dict['status']='subspecies'
                worms_dict['valid_AphiaID']=parent_aphiaID

        else: #rank higher than species

            worms_dict['scientificname']=pd.NA

    return worms_dict


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

        taxon = _process_rank(taxon)
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

    params={'store':store,
            'outputpath':outputpath,
            'overwrite':overwrite}

    # Get unique species

    unique_species = get_uniqueSpecies(gzfile_path, **params)

    params['wormscall']=wormscall

    # Get WoRMS filter

    worms_matchfilter = match_WoRMS(unique_species, **params)

    # Get accepted classifications

    isnotaccepted = (worms_matchfilter['worms_status']!="accepted") & (~pd.isnull(worms_matchfilter["valid_aphiaID"]))
    unaccepted_aphiaID = worms_matchfilter.loc[isnotaccepted, "valid_aphiaID"].unique().tolist()
    worms_acceptedfilter = get_AcceptedWoRMS(unaccepted_aphiaID, **params)

    # Process subspecies

    #worms_subspecies = worms_acceptedfilter.loc[(worms_acceptedfilter['worms_status']=="subspecies"]) & (~pd.isnull(worms_acceptedfilter["valid_aphiaID"]), "valid_aphiaID"]
    #index = worms_subspecies.index.tolist()
    #parent_aphiaID = worms_subspecies.tolist()
    #columns = list(set(worms_acceptedfilter.columns) - set(["group"]))
    #worms_acceptedfilter.loc[index, columns] = get_AcceptedWoRMS(parent_aphiaID, **params)[columns]

    issubspecies = (worms_acceptedfilter['worms_status']=="subspecies") & (~pd.isnull(worms_acceptedfilter["valid_aphiaID"]))
    subspeciesByaphiaID = worms_acceptedfilter.loc[issubspecies, "valid_aphiaID"].groupby("valid_aphiaID")
    parent_aphiaID = list(worms_subspecies.groups.keys())

    species_aphiaID = get_AcceptedWoRMS(parent_aphiaID, **params)

    columns = list(set(worms_acceptedfilter.columns) - set(["group"]))
    for idx,group in enumerate(species_aphiaID['group']):

        indexes = subspeciesByaphiaID.get_group(group).index
        worms_acceptedfilter.loc[indexes,columns] = species_aphiaID.loc[idx,columns]

    return worms_matchfilter, worms_acceptedfilter


def test():

    df = pd.read_csv('/home/GPU/eberhocoi/verbatimScientificName_more.txt', sep='\t')
    print(f"{len(df)} lines to process")

    start=time.time()

    total=0
    count=0
    for i,sciname in enumerate(df['verbatimScientificName']):
        if standardize_sciname(sciname):
            count+=1
        else:
            print(sciname)
        total+=1

        if ((i+1)%100000)==0:
            print(f'PROCESSING | {i+1} lines ({count}/{total} not processed, i.e {np.round(count/total*100,2)})')

    print(f'PROCESSING | {i+1} lines ({count}/{total} not processed, i.e {np.round(count/total*100,2)})')

    end=time.time()

    print(f'TIME : {np.round(end - start,0)}s')


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
