#!/usr/bin/env python3r

# External import

import argparse
import gzip
import pandas as pd
import numpy as np
import yaml
import time
import os
from unidecode import unidecode
from operator import itemgetter
import re
from datetime import datetime

from suds import null, WebFault
from suds.client import Client
from suds.sudsobject import items
import http

# Internal import

from marinedb.filters import subsetranks
from marinedb.utils import regexstrip

# Global variables

PATH = os.path.dirname(os.path.abspath(__file__))

YEAR_NOW = datetime.now().year

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
             'isMarine':'ismarine',
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

def write_dataframe_txtfile(df, txt_filename, init=False):

    print(f'            Storing in {txt_filename} | {len(df)} observations')
    if init:
        df.to_csv(txt_filename, mode='w', index=False, header=True, sep='\t')
    else:
        df.to_csv(txt_filename, mode='a', index=False, header=False, sep='\t')

    return True

def _store_uniqueRawSciname(unique_rawsciname, outputfile):

    print(f"            Storing in {outputfile} | {len(unique_rawsciname)} unique raw scientific names")
    with open(outputfile, 'w') as f:
        f.writelines('\n'.join(['raw_sciname'] + list(unique_rawsciname)) + '\n')

def get_uniqueRawSciname(gzfile_path, colname, store=False, overwrite=False, outputpath='./', outputfile=''):

    print(f'            ** Retrieving unique raw scientific names from {gzfile_path}')

    unique_rawsciname = set()
    if len(outputfile)==0:
        outputfile=f'unique_{colname}.txt'
    outputfile = os.path.join(outputpath,outputfile)

    if store and os.path.isfile(outputfile):

        if overwrite:
            print(f"            WARNING | {outputfile} already exists and will be overwritten (new values will be added at the end of the file)")
            unique_rawsciname = set(pd.read_csv(outputfile, sep='\t').values.flatten())
        else:
            print(f"            INFO | {outputfile} already exists and will be used")
            unique_rawsciname = list(pd.read_csv(outputfile, sep='\t').values.flatten())
            return unique_rawsciname

    with gzip.open(gzfile_path,'r') as data:

        header = data.readline().decode("utf8").strip('\n').split('\t')
        sciname_index = header.index(colname)
        count=len(unique_rawsciname)

        for idx, line in enumerate(data):

            sciname = line.decode("utf8").strip('\n').split('\t')[sciname_index]

            unique_rawsciname = update(unique_rawsciname,sciname)
            Nunique = len(unique_rawsciname)

            # Display progress

            if ((idx+1)%1000000)==0:
                print(f"            Processing | {idx + 1} lines done, {len(unique_rawsciname)} unique raw scientific names")

            if store and ((Nunique-count)==100000):
                _store_uniqueRawSciname(unique_rawsciname, outputfile)
                count = Nunique

    # Save progress

    if store:
        _store_uniqueRawSciname(unique_rawsciname, outputfile)

    return list(unique_rawsciname)


def _format_scinamesForWoRMS_elementwise(sciname, identification_level='best'):

    empty=False
    next=False

    # Delete any words in ignoreWords.yaml
    # e.g. "Leccinum scabrum sl, incl. cyaneobasileucum, melaneum"
    # e.g. "Dactylorhiza incarnatavar.lobelii"
    # e.g. "Makaira spp"
    # e.g. "Tambja cf. verconis"

    with open(os.path.join(PATH,'ignoreWords.yaml'),'r') as f:
        file = yaml.safe_load(f)
        ignoreWordsIn = file['SCN_IGNORE'] + file['AUTHORSHIP_IGNORE']

    ignoreWordsIn = sorted(ignoreWordsIn, key=len, reverse=True)
    ignoreWordsIn = '|'.join([fr'{word}' for word in ignoreWordsIn])
    pattern1 = fr'((?<=\s|\.)|(?<=^))(notho)?({ignoreWordsIn})([^a-zA-Z]|$)' #e.g. " sl,", " incl.", "s.l.", "sp1"
    pattern2 = fr'({ignoreWordsIn})(\.)' #e.g. "incarnatavar.lobelii"
    sciname = re.sub(fr'{pattern1}|{pattern2}', ' ', sciname, flags=re.IGNORECASE) #re.IGNORECASE e.g. "Van" in "Dreissena Van Beneden, 1835"

    # Remove special characters

    pattern = r'[^a-zA-Z\s\-]' #e.g. do not remove "-" in "Blechnum novae-zelandiae", but remove date
    sciname = re.sub(pattern,' ',sciname).strip()

    if not re.search(r'[a-zA-Z]',sciname):

        ## Empty string

        empty=True
        next=True

        return sciname, empty, next

    # Capitalise the first letter, if necessary

    sciname = sciname[0].upper() + sciname[1:]

    # Standardise whitespace

    sciname = re.sub(r'\s+',' ',sciname)

    # Check whether the scientific name is defined at species level

    #sciname_split = re.split(r'\s',sciname)
    sciname_split = sciname.split()

    if len(sciname_split)==1:

        ## Rank higher than species

        if (identification_level=='best') or (identification_level=='species'):

            next=True

        else: #identification_level=='first'

            next=False

    return sciname, empty, next


def _format_scinamesForWoRMS(raw_scinames, identification_level='best'): # 'best', 'species', 'first'

    if (pd.isnull(raw_scinames)) or (len(raw_scinames)==0):
        return '', 0, False

    # Do not proceed with the code if hybrid name
    # e.g. "Branta hutchinsii x Branta leucopsis"
    # e.g. "Branta hutchinsii xBranta leucopsis"

    if re.search(r'(^|\s)x([A-Z\s]|$)|×',raw_scinames):
        return '', 0, False

    # Delete everything in parentheses
    # e.g. "Haliclona (Rhizoniera) viscosa"
    # e.g. "Cygnus olor (Gmelin, 1789)"
    # e.g. "Centaurea nigra sens. lat. (=nigra/debeauxii)"
    # e.g. " Lepidotrigla cf grandis (A) [Gomon, pers comm]"

    pattern = r'\(.*?(\)|$)|\[.*?(\]|$)' #e.g. "Rusa timorensis (de"
    scinames2process = re.sub(pattern,' ',raw_scinames)

    # Convert to ASCII format

    scinames2process=unidecode(scinames2process)

    # Delete parts of the string containing a number:
    # - greater than the current year
    # - less than 3 digits
    # - or more than 4 digits
    # i.e a number that cannot be the authorship year
    # e.g. "Megaselia sp. BIOUG27368-A01"
    # e.g. "BOLD:AEF8294"

    pattern=r'(?:(?<=^)|(?<=\s))[^\s]*?(?P<number>[0-9]+)[^\s]*?(?:(?=\s)|(?=$))'
    finditer=re.finditer(pattern,scinames2process)

    cut=[0]
    for match in finditer:
        number=match['number']
        Ndigits=len(number)
        if (Ndigits<=3) or (Ndigits>4) or (int(number)>YEAR_NOW):
            cut.append(match.start())
            cut.append(match.end())
    cut.append(-1)

    if len(cut)>2:
        scinames2process = ' '.join([scinames2process[i:j] for i,j in zip(cut[0::2],cut[1::2])])

    # Delete numbers

    pattern = r'[0-9]'
    scinames2process = re.sub(pattern,' ',scinames2process)

    if not re.search(r'[a-zA-Z]',scinames2process):
        return '', 0, False

    # Convert uppercase words so that only the first letter is capitalised
    # (not always a problem for WoRMS, but necessary at a later stage)
    # assumption:
    #   when an uppercase word and a lowercase word are joined,
    #   the uppercase at the intersection is considered to belong to the uppercase word
    #   and the two words are considered separately (i.e as two distinct items in the list below)
    # explanation:
    #   - WoRMS seems more robust to the absence of a letter at the beginning of a word
    #     (and the addition of a letter at the end of a word)
    #     than to the addition of a letter at the beginning of a word
    #     (and the absence of a letter at the end of a word)
    #   - we will only consider the next item in the list if the first is empty after processing
    #     or is not defined at species level when identification_level is 'species or 'best'
    # e.g. "HALICLONA (RHIZONERIA) VISCOSA" to "Haliclona (rhizoneria) viscosa"
    # e.g. "HALICLONA VISCOSAsardina pilchardus" to "Haliclona viscosa Sardina pilchardus"
    # e.g. "HALICLONA VISCOSASardina pilchardus" to "Haliclona viscosas Ardina pilchardus"
    # Note: undesirable result if "Haliclona (RHIZONERIA) viscosa" (but this function doesn't take into account what's in parentheses anyway)

    pattern = r'((?<=[A-Z])[A-Z][^a-z]*?)([a-z]|$)'
    scinames2process, Ncaps = re.subn(pattern, lambda m: (m.group(1).lower() + ' ' + m.group(2).upper()), scinames2process)

    # Standardize whitespace

    scinames2process = re.sub(r'\s+',' ',scinames2process)

    # Split by +, |, /, \, &, comma and capital letters
    # e.g. "Tringa (Heteroscelus) brevipesEopsaltria (Eopsaltria) griseogularis" (capital, no more parentheses at this stage)
    # e.g. "Clupea harengus/Sprattus sprattus" (/)
    # e.g. "Branta hutchinsii x Branta leucopsis" (capital)
    # e.g. "Populus nigra + Populus x canadensis" (+ and capital)
    # e.g. "Centroberyx affinis, Centroberyx gerrardi & Centroberyx australis [Soviet Fishery Data, 1998]" (&, comma and capital)

    pattern = r'[&,+|/\\]|(?=[A-Z])'
    scinames2process = re.split(pattern, scinames2process)

    # Keep only one scientific name if there are several, and standardise it
    # assumption:
    #  if several species are listed for an occurrence and the first one is not marine,
    #  the others won't be either

    next=True
    first=True
    idx=0
    first_sciname=''

    count=0 #À SUPPRIMER APRÈS DEBUG

    minlength=3
    if identification_level=='species':
        minwords=2
        minlength=minlength*minwords+1
        first=False
    else:
        minwords=1

    Nscinames=len(scinames2process)
    while next and (idx<Nscinames):

        # Standardise the scientific name

        sciname = regexstrip.apply(scinames2process[idx], pattern=r'^[^a-zA-Z]|[^a-zA-Z\.]$')

        Nwords=len(sciname.split())
        length=len(sciname)
        if (Nwords>=minwords) and (length>=minlength):
            count+=1
            sciname, empty, next = _format_scinamesForWoRMS_elementwise(sciname, identification_level=identification_level)

            if first and (not empty):

                # First scientific name in `raw_sciname`

                first_sciname=sciname
                first=False

            if next or (len(sciname)<minlength):

                # Not a scientific name / species

                idx+=1

        else:

            # Empty string or too short to be a scientific name / species

            idx+=1

    if (idx==Nscinames):
        sciname=first_sciname

    if len(sciname)<minlength:
        sciname=''

    #sciname=re.split(r'\s',sciname)
    sciname=sciname.split()

    if len(sciname)>3: #SUPRESS AFTER DEBUG
        morethan3=True
    else:
        morethan3=False

    return ' '.join(sciname[:3]), count, morethan3


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


def _parse_matchAphiaRecordsByNames(species, results, keys):

    classification=[]

    if len(results)!=0:

        for taxon in results: #may be more than one candidate

            taxon = dict(items(taxon))
            classif = itemgetter(*keys)(taxon)
            classification.append([species] + list(classif))

    else:

        classification.append([species] + [pd.NA]*len(keys))

    return classification


def match_ClassificationBySciname(species, wormscall=WORMSCALL, doublecheck=False):

    if isinstance(species,str):
        species=[species]

    print(f'            -- Scientific name pre-processing --')

    for idx in range(len(species)):
        species[idx] = _standardize_scinames(species[idx])

    print(f'            -- WoRMS API call --')

    scinames["scientificname"] = species

    results = _connect_matchAphiaRecordsByNames(scinames)

    wormscallK = list(wormscall.keys())
    wormscallV = list(itemgetter(*wormscallK)(wormscall))
    colnames = ['group'] + wormscallV

    classification=[]

    print(f'            -- Format WoRMS match & Double-check --')
    for idx,resultsBySciname in enumerate(results):

        if len(resultsBySciname)!=0:

            classification += _parse_matchAphiaRecordsByNames(species[idx],resultsBySciname,wormscallK)

        else:

            spe = re.split(r'\s',specie[idx])
            if doublecheck and len(spe)>2:

                scinames["scientificname"] = [' '.join(spe[:2])]
                res = _connect_matchAphiaRecordsByNames(scinames)
                classification += _parse_matchAphiaRecordsByNames(spe,res,wormscallK)

            else:

                classification.append([species[idx]] + [pd.NA]*len(wormscallK))


    classification = pd.DataFrame(classification, columns=colnames)


    return classification


def match_WoRMS(species, wormscall=WORMSCALL, doublecheck=False, store=False, outputpath='./', outputfile='worms_matchfilter.tsv', overwrite=False):

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
        if batch==(nbatch-1):
            end_idx = nspecies
        else:
            end_idx = start_idx + 50

        species_subset = species[start_idx:end_idx]
        classification = match_ClassificationBySciname(species_subset, wormscall=wormscall, doublecheck=doublecheck)

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
            write_dataframe_txtfile(matched_worms, file, init=True)

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
                write_dataframe_txtfile(accepted_worms, outputfile, init=True)

    accepted_worms["valid_aphiaID"] = accepted_worms["valid_aphiaID"].astype('Int64')
    accepted_worms["group"] = accepted_worms["group"].astype('Int64')

    return accepted_worms



def get_WoRMSfilter(gzfile_path, wormscall=WORMSCALL, store=False, outputpath='./', overwrite=False):

    params={'store':store,
            'outputpath':outputpath,
            'overwrite':overwrite}

    # Get unique species

    unique_rawsciname = get_uniqueRawSciname(gzfile_path, **params)

    params['wormscall']=wormscall

    # Get WoRMS filter

    worms_matchfilter = match_WoRMS(unique_rawsciname, **params)

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

    df = pd.read_csv('/data/smartbiodiv/eberhocoi/source/unique_verbatimScientificName.txt', sep='\t')
    print(f"{len(df)} lines to process")
    print()

    start=time.time()

    results=[fr'verbatim	processed	more']
    outputfile='/data/smartbiodiv/eberhocoi/source/verbatimScientificName_processed.txt'

    count=[]
    full_time=0
    for i,sciname in enumerate(df['raw_sciname']):
        res, icount, morethan3=_format_scinamesForWoRMS(sciname, identification_level='best')
        results.append(fr'{sciname}	{res}	{morethan3}')
        count.append(icount)

        if ((i+1)%10000==0):
            print('SAMPLE RES')
            print('-----------------------')
            print(f'Line n°{i}:', sciname)
            print("Result |",res,icount,morethan3)
            print('GLOBAL RES')
            print('-----------------------')
            old_time=full_time
            full_time=time.time()-start
            time_10000=full_time-old_time
            print("Time (last display) |", f'{np.round(time_10000,0)}s')
            print("Time (beginning) |", f'{np.round(full_time,0)}s')
            print(f'Average nb of processing | {np.round(np.mean(count),0)}')
            print()

        if ((i+1)%100000==0):
            print('Storing')
            print()
            with open(outputfile, 'a') as f:
                f.writelines('\n'.join(results)+'\n')
            results.clear()

    end=time.time()

    print(f'AVERAGE NB OF PROCESSING: {np.round(np.mean(count),0)}')
    print(f'TIME : {np.round(end - start,0)}s')


if __name__ == '__main__':

     test()
#    parser = argparse.ArgumentParser(description='Get WoRMS filter and accepted classification')
#    parser.add_argument('gbif_tsv_gzfile', type=str, help='path to the tab-separated file from GBIF to be processed')   
#    parser.add_argument('--output_path', type=str, help='path to folder where output files will be stored', default='./')
#    args = parser.parse_args()

#    print(f'    * Creating the files needed for WoRMS filtering')

#    start=time.time()

#    _ = get_WoRMSfilter(args.gbif_tsv_gzfile, wormscall=WORMSCALL, store=True, outputpath=args.output_path, overwrite=False)

#    end=time.time()

#    print(f'TIME : {np.round(end - start,0)}s')
