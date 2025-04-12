#!/usr/bin/env python3r

# External import

import argparse
import gzip
import pandas as pd
import math
import yaml
import json
import time
import os
from unidecode import unidecode
from operator import itemgetter
import itertools
import re
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from tqdm import tqdm

from suds import null, WebFault
from suds.client import Client
from suds.sudsobject import items
import http

# Internal import

from marinedb.filters import subsetranks
from marinedb.utils import regexstrip
from marinedb.utils.standardizenan import isnan

# Global variables

PATH = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(PATH,'ignoreWords.yaml'),'r') as f:
    file = yaml.safe_load(f)
    IGNOREWORDS = file['SCN_IGNORE'] + file['AUTHORSHIP_IGNORE']
IGNOREWORDS = sorted(IGNOREWORDS, key=len, reverse=True)
IGNOREWORDS = '|'.join([fr'{word}' for word in IGNOREWORDS])

YEAR_NOW = datetime.now().year

LOWER_THAN_SPECIES = subsetranks.apply('species', lower=True, strict=True)

WORMSCALL = {
             'scientificname': 'species', #`scientificname` must never be removed from `WORMSCALL`
             'genus': 'genus',
             'family': 'family',
             'order': 'order',
             'cls': 'class',
             'phylum': 'phylum',
             'kingdom': 'kingdom',
             'match_type':'worms_matchtype', #`match_type` must never be removed from `WORMSCALL`
             'status': 'worms_status', #`status` must never be removed from `WORMSCALL`
             'valid_AphiaID':'valid_aphiaID', #`valid_AphiaID` must never be removed from `WORMSCALL`
             'isExtinct':'isextinct',
             'isMarine':'ismarine',
             'rank':'rank', #`rank` must never be removed from `WORMSCALL`
             'authority':'authority'
            }


cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)

scinames = cl.factory.create('scientificnames')
scinames["_arrayType"] = "string[]"

aphiaID = cl.factory.create("aphiaids")
aphiaID["_arrayType"] = "int[]"


def write_dataframe2txtfile(df, txt_filename, init=False, verbose=False):

    if verbose:
        print(f'            Storing in {txt_filename} | {len(df)} observations')

    if init:
        df.to_csv(txt_filename, mode='w', index=False, header=True, sep='\t')
    else:
        df.to_csv(txt_filename, mode='a', index=False, header=False, sep='\t')

    return True

def printv(message, verbose=True):

    if verbose:
        print(message)

    return True


### Get unique raw scientific names ###


def _update_set(myset,key):

    if isnan(key):
        return myset

    if not re.search(r'[a-zA-Z]',str(key)):
        return myset

    else:
        myset.add(key)
        return myset

def _store_uniqueRawSciname(unique_rawsciname, outputfile):

    print(f"            Storing in {outputfile} | {len(unique_rawsciname)} unique raw scientific names")

    with open(outputfile, 'w') as f:
        f.writelines('\n'.join(['raw_sciname'] + list(unique_rawsciname)))

def _strip_rawSciname(rawsciname):

    rawsciname = regexstrip.apply(rawsciname, pattern=r'["\s]+')
    rawsciname = regexstrip.apply(rawsciname, pattern=r"['\s]+")

    return rawsciname

def get_uniqueRawSciname(gzfile_path, colname, store=False, overwrite=False, outputpath='./', outputfile=''):

    print(f'            ** Retrieving unique raw scientific names from {gzfile_path}')

    unique_rawsciname = set()

    if len(outputfile)==0:
        outputfile=f'unique_{colname}.txt'
    outputfile = os.path.join(outputpath,outputfile)

    if store and os.path.isfile(outputfile):

        if overwrite:
            print(f"            WARNING | {outputfile} already exists and will be overwritten (new values will be added to the file)")
            unique_rawsciname = set(pd.read_csv(outputfile, sep='\t').values.flatten())

        else:
            print(f"            INFO | {outputfile} already exists and will be used")
            unique_rawsciname = list(pd.read_csv(outputfile, sep='\t').values.flatten())
            return unique_rawsciname

    start=time.time()

    with gzip.open(gzfile_path,'r') as data:

        header = data.readline().decode("utf8").strip('\n').split('\t')
        sciname_index = header.index(colname)
        count=len(unique_rawsciname)

        for idx, line in enumerate(data):

            # Pre-process the raw scientific names
            # to avoid quotation problems with pandas

            sciname = line.decode("utf8").strip('\n').split('\t')[sciname_index]
            sciname = _strip_rawSciname(sciname)

            # Update the set of unique raw scientific names

            unique_rawsciname = _update_set(unique_rawsciname,sciname)
            Nunique = len(unique_rawsciname)

            # Display progress

            if ((idx+1)%1000000)==0:
                print(f"            Processing | {idx + 1} lines done ({round(time.time()-start)}s), {len(unique_rawsciname)} unique raw scientific names")

            # Save progress

            if store and ((Nunique-count)==100000):
                _store_uniqueRawSciname(unique_rawsciname, outputfile)
                count = Nunique


    # Store list of unique raw scientific names

    if store:
        _store_uniqueRawSciname(unique_rawsciname, outputfile)

    print(f"            TIME: {round(time.time()-start)}s")

    return list(unique_rawsciname)


### Pre-process scientific names for WoRMS queries ###


def _format_scinamesForWoRMS_elementwise(raw_sciname, identification_level='species', min_length=3, min_words=2):

    # Delete any words in ignoreWords.yaml
    # e.g. "Leccinum scabrum sl, incl. cyaneobasileucum, melaneum"
    # e.g. "Dactylorhiza incarnatavar.lobelii"
    # e.g. "Makaira spp"
    # e.g. "Tambja cf. verconis"

    pattern1 = fr'((?<=[\s\._:\-])|(?<=^))(notho)?({IGNOREWORDS})([^a-zA-Z]|$)' #e.g. " sl,", " incl.", "s.l.", "sp1"
    pattern2 = fr'({IGNOREWORDS})(\.)' #e.g. "incarnatavar.lobelii"
    sciname = re.sub(fr'{pattern1}|{pattern2}', ' ', raw_sciname, flags=re.IGNORECASE) #re.IGNORECASE e.g. "Van" in "Dreissena Van Beneden, 1835"

    # Remove special characters

    pattern = r'[^a-zA-Z\s\-\.]|\-(?=[^a-zA-Z])|(?<=[^a-zA-Z])\-' #e.g. do not remove "-" in "Blechnum novae-zelandiae", but remove dates
    sciname = re.sub(pattern,' ',sciname).strip()

    # Delete parts of the string containing a .

    pattern = r'(?:(?<=^)|(?<=\s))[^\s]*?\.[^\s]*?(?:(?=\s)|(?=$))'
    sciname = re.sub(pattern,' ',sciname)

    if not re.search(r'[a-zA-Z]',sciname):

        ## Empty string

        next=True
        keep=False

        return sciname, next, keep

    # Capitalise the first letter, if necessary

    sciname = sciname[0].upper() + sciname[1:]

    # Standardise whitespace

    sciname = re.sub(r'\s+',' ',sciname)

    # Check whether the scientific name is defined at species level or not
    # and check that it meets the minimum word length criterion

    sciname_split = sciname.split()

    if len(sciname_split)==1:

        ## Rank higher than species

        if (identification_level=='species') or (min_words==2):

            next=True
            keep=False

        elif len(sciname)<min_length:

            ## Do not meet minimum word length criterion

            next=True
            keep=False

        elif (identification_level=='best'): #i.e also len(sciname)>=min_length and min_words==1

            next=True
            keep=True

        else: #i.e identification_level=='first' and len(sciname)>=min_length and min_words==1

            next=False
            keep=True

    else:

        if len(sciname_split[0])<min_length:

            ## Do not meet minimum word length criterion

            next=True
            keep=False

        else:

            if len(sciname_split[1])<min_length:

                ## Do not meet minimum word length criterion

                if (identification_level=='species') or (min_words==2):

                    next=True
                    keep=False

                elif (identification_level=='first'):

                    ## Keep only the first word

                    sciname=sciname_split[0]
                    next=False
                    keep=True

                else: #i.e identification_level=='best' and min_words==1:

                    ## Keep only the first word

                    sciname=sciname_split[0]
                    next=True
                    keep=True

            else:

                ## Rank less than or equal to species
                ## and minimum word length criterion met

                next=False
                keep=True

    return sciname, next, keep


def _format_scinamesForWoRMS(raw_scinames, identification_level='species', min_length=3, doublecheck=True): # 'best', 'species', 'first'

    wormsscinames=[]

    if identification_level=='species':
        min_words=2
        min_stringlength=min_words*min_length+1
    else:
        min_words=1
        min_stringlength=min_words*min_length


    if (pd.isnull(raw_scinames)) or (len(raw_scinames)==0):
        return wormsscinames

    # Do not proceed with the code if hybrid name
    # e.g. "Branta hutchinsii x Branta leucopsis"
    # e.g. "Branta hutchinsii xBranta leucopsis"
    # e.g. "Junco X Zonotrichia hyemalis X albicollis"

    if re.search(r'(^|\s)x([A-Z\s]|$)|×|\sX\s',raw_scinames):
        return wormsscinames

    scinames2process=raw_scinames

    # Solve any encoding problems

    try:
        scinames2process = scinames2process.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError,UnicodeDecodeError):
        pass

    # Delete parts of the string containing a number:
    # - greater than the current year or lower than 1600
    # - less than 3 digits
    # - or more than 4 digits
    # i.e a number that cannot be the authorship year
    # i.e a word that probably refers to a sequenced-based observation
    # e.g. "Megaselia sp. BIOUG27368-A01"
    # e.g. "BOLD:AEF8294"

    pattern=r'(?:(?<=^)|(?<=[(\[\s]))[^(\[\)\]\s]*?(?P<number>[0-9]+)[^)\](\[\s]*?(?:(?=[)\]\s])|(?=$))'
    finditer=re.finditer(pattern,scinames2process)

    cut=[0]
    for match in finditer:
        number=match['number']
        Ndigits=len(number)
        if (Ndigits<=3) or (Ndigits>4) or (int(number)>YEAR_NOW) or (int(number)<1600):
            cut.append(match.start())
            cut.append(match.end())
    cut.append(len(scinames2process))

    if len(cut)>2:
        scinames2process = ' '.join([scinames2process[i:j] for i,j in zip(cut[0::2],cut[1::2])])

    # Detect two common format errors and process the string accordingly

    if identification_level!='first':

        ## "String1 STRING2 STRING3 ..." to "String1 string2"
        # e.g. "Neotoma CINEREA ACRAEA" to "Neotoma cinerea"
        pattern=r'^[^a-zA-Z0-9]*([A-Z][a-z]{2,}\s+[A-Z]{3,})\s+[A-Z]{3,}' #minimum word length: 3 characters
        match=re.search(pattern,scinames2process)
        if match is not None:
            match=match.group(1).lower()
            match=match[0].upper()+match[1:]
            match, _, keep = _format_scinamesForWoRMS_elementwise(match, identification_level=identification_level, min_length=min_length, min_words=2)
            if keep:
                wormsscinames.append(match)

        ## "String1 String2[.] string3 ..." to "String1 string3"
        # e.g. "Graneledone Eledoninae verrucosa" to "Graneledone verrucosa"
        # e.g. "Pseudobarbella Nog. levieri" to "Pseudobarbella levieri"
        pattern=r'^[^a-zA-Z0-9]*([A-Z][a-z]{2,})\s+[A-Z][a-z]{2,}\.*\s+([a-z]{3,}\.?)'
        match=re.search(pattern,scinames2process)
        if match is not None:
            match=match.group(1) + ' ' + match.group(2)
            match, _, keep = _format_scinamesForWoRMS_elementwise(match, identification_level=identification_level, min_length=min_length, min_words=2)
            if keep:
                wormsscinames.append(match)

    # Delete everything in parentheses
    # e.g. "Haliclona (Rhizoniera) viscosa"
    # e.g. "Cygnus olor (Gmelin, 1789)"
    # e.g. "Centaurea nigra sens. lat. (=nigra/debeauxii)"
    # e.g. " Lepidotrigla cf grandis (A) [Gomon, pers comm]"

    pattern = r'\(.*?(\)|$)|\[.*?(\]|$)' #e.g. "Rusa timorensis (de"
    scinames2process = re.sub(pattern,' ',scinames2process)

    # Convert to ASCII format

    scinames2process=unidecode(scinames2process)

    # Delete numbers

    pattern = r'[0-9]'
    scinames2process = re.sub(pattern,' ',scinames2process)

    if not re.search(r'[a-zA-Z]',scinames2process):

        ## Empty string

        return wormsscinames

    # Convert uppercase words so that only the first letter is capitalised
    # (not always a problem for WoRMS, but necessary at a later stage)
    # assumption:
    #   when an uppercase word and a lowercase word are joined,
    #   the uppercase at the intersection is considered to belong to the uppercase word
    #   and the two words are considered separately (i.e as two distinct items in the list below)
    # explanation:
    #   - WoRMS seems more robust to the absence of a letter at the beginning of a word
    #     (and to the addition of a letter at the end of a word)
    #     than to the addition of a letter at the beginning of a word
    #     (and the absence of a letter at the end of a word)
    #   - we will only consider the next item in the list if the first is empty after processing
    #     or is not defined at species level when `identification_level` is 'species' or 'best'
    #     (that's why it is more important to ensure that the first item is as complete as possible)
    # e.g. "HALICLONA (RHIZONERIA) VISCOSA" to "Haliclona (rhizoneria) viscosa"
    # e.g. "HALICLONA VISCOSAsardina pilchardus" to "Haliclona viscosa Sardina pilchardus"
    # e.g. "HALICLONA VISCOSASardina pilchardus" to "Haliclona viscosas Ardina pilchardus"
    # Note: undesirable result if "Haliclona (RHIZONERIA) viscosa" (to "Haliclona (Rhizoneria)  Viscosa")
    #       (but this function doesn't take into account what's in parentheses anyway)

    pattern = r'((?<=[A-Z])[A-Z][^a-z]*?)((?<=[^a-zA-Z])[A-Z](?=[a-z])|[a-z]|$)'
    scinames2process, Ncaps = re.subn(pattern, lambda m: (m.group(1).lower() + ' ' + m.group(2).upper()), scinames2process)

    # Standardize whitespace

    scinames2process = re.sub(r'\s+',' ',scinames2process)

    # Split by +, |, /, \, &, ;, comma and capital letters
    # e.g. "Tringa (Heteroscelus) brevipesEopsaltria (Eopsaltria) griseogularis" (capital, no more parentheses at this stage)
    # e.g. "Clupea harengus/Sprattus sprattus" (/ and capital)
    # e.g. "decapterus macarellus+carcharhinus spp" (+)
    # e.g. "Centroberyx affinis, Centroberyx gerrardi & Centroberyx australis [Soviet Fishery Data, 1998]" (&, comma and capital)

    pattern = r'[&,+|/;\\]|(?=[A-Z])'
    scinames2process = re.split(pattern, scinames2process)

    # Keep only one scientific name if there are several, and standardise it
    # assumption:
    #  if several species are listed for an occurrence and the first one is not marine,
    #  the others won't be either

    next=True
    idx=0
    preprocessed=[]
    Nscinames=len(scinames2process)

    while next and (idx<Nscinames):

        # Standardise the scientific name

        sciname = regexstrip.apply(scinames2process[idx], pattern=r'^[^a-zA-Z]|[^a-zA-Z\.]$')

        Nwords=len(re.split(r'[\s_]+',sciname))
        stringlength=len(sciname)

        if (Nwords>=min_words) and (stringlength>=min_stringlength):

            # Meets minimum word count and minimum string length criteria

            sciname, next, keep = _format_scinamesForWoRMS_elementwise(sciname, identification_level=identification_level, min_length=min_length, min_words=min_words)

            if keep:

                sciname=sciname.split()

                if (len(sciname)>2) and (len(sciname[2])<min_length):
                    sciname=' '.join(sciname[:2])
                else:
                    sciname=' '.join(sciname[:3])

                preprocessed.append(sciname)

                if identification_level=='best':
                    min_words=2
                    min_stringlength=min_words*min_length+1

            if next:

                # Not a scientific name (or not at the species level)

                idx+=1

        else:

            # Empty string or too short to be a scientific name (or not at the species level)

            idx+=1

    if len(preprocessed)!=0:
        wormsscinames+=preprocessed

    # Delete duplicates & Sort by number of words (subspecies-species-higher order)

    wormsscinames = list(set(wormsscinames))  # e.g. "Helius Helius mainensis" to ["Helius mainensis","Helius mainensis"]
    wormsscinames = sorted(wormsscinames,key=(lambda string: string.count(' ')),reverse=True)

    if (len(wormsscinames)>=2):

        # Two or more candidates for the WoRMS API call

        if (wormsscinames[0].count(' ')>1) and (wormsscinames[1].count(' ')==1) and (wormsscinames[1] in wormsscinames[0]):

            # The two-word candidate string corresponds to the start of the three-word candidate string
            # This case is only taken into account in the rest of the code if `doublecheck`
            # Delete the two-word candidate string

            del wormsscinames[1]

    if doublecheck:

        # When the pre-processed string contains more than two words,
        # try again with only the first two words

        wormsscinames = [item for string in wormsscinames for item in ([string,' '.join(string.split()[:2])] if (string.count(' ')>1) else [string])]

    return wormsscinames

###########################################
############## WoRMS filters ##############
###########################################


def _resume(values2process, valuesprocessed):

    # Return only unprocessed values

    valuesprocessed = set(valuesprocessed)
    values2process = set(values2process) - valuesprocessed

    return list(values2process)

def _resume_matchWoRMS(values2process, outputfile):

    Nsciname = len(values2process)

    valuesprocessed = pd.read_csv(outputfile, sep='\t')
    values2process = _resume(values2process, valuesprocessed['group'].convert_dtypes().tolist())

    return values2process, valuesprocessed

def _process_rank(worms_results, ismatchfilter, species_only=True): #no NaN

    rank = worms_results['rank']

    if pd.isnull(rank):
        print(worms_results)
        return worms_results
    else:
        rank = rank.lower()

    if rank!='species':

        if rank in LOWER_THAN_SPECIES:

            parent_aphiaID = worms_results['parentNameUsageID']

            condition = (not ismatchfilter) or (ismatchfilter and (worms_results['status']=='accepted'))

            if not pd.isnull(parent_aphiaID):
                worms_results['status']='subspecies'
                if condition:
                    worms_results['valid_AphiaID']=parent_aphiaID

        elif species_only:

            # The identification level must be the species
            # but the rank is higher than species

            worms_results['scientificname']=pd.NA

    return worms_results


### Match WoRMS by pre-processed scientific names ###

def preprocess_quotationMarks(raw_scinames):

    # Pre-process the raw scientific names
    # to avoid quotation mark problems with pandas

    raw_scinames=pd.Series(raw_scinames).str.replace('^["\s]+|["\s]+$','',regex=True)
    raw_scinames=raw_scinames.str.replace("^['\s]+|['\s]+$",'',regex=True)
    raw_scinames=list(set(raw_scinames.tolist()))

    return raw_scinames

def _connect_matchAphiaRecordsByNames(wormsscinames, max_attempt=10, pause_duration=5):

    global cl

    attempt = 0
    while attempt < max_attempt:
        try:
            return cl.service.matchAphiaRecordsByNames(wormsscinames)
        except (http.client.RemoteDisconnected, TimeoutError):
            attempt += 1
            if attempt < max_attempt:
                time.sleep(pause_duration)
                cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
            else:
                raise

def _parse_matchAphiaRecordsByNames(sciname, worms_results, keys, species_only=True):

    # Extract the match information specified in `keys`

    classification=[]

    if len(worms_results)!=0:

        for taxon in worms_results: #may be more than one candidate

            taxon = dict(items(taxon))
            taxon = _process_rank(taxon, ismatchfilter=True, species_only=species_only)

            if pd.isnull(taxon['scientificname']):
                classification.append([sciname] + [pd.NA]*len(keys))

            else:
                classification.append([sciname] + list(itemgetter(*keys)(taxon)))

    else:

        classification.append([sciname] + [pd.NA]*len(keys))

    return classification


def _match50_WoRMSBySciname(wormsscinames, wormscallK, species_only=True):

    if isinstance(wormsscinames,str):
        wormsscinames=[wormsscinames]

    scinames["scientificname"] = wormsscinames
    worms_results=_connect_matchAphiaRecordsByNames(scinames)

    # Keep only the match information specified in `wormscallK`

    classification=[]

    for idx,res in enumerate(worms_results):

        classification += _parse_matchAphiaRecordsByNames(wormsscinames[idx], res, wormscallK, species_only=species_only)

    return classification


def match_WoRMSBySciname(raw_scinames, wormscall=WORMSCALL, identification_level='species', min_length=3, doublecheck=True, store=True, overwrite=False, return_filename=False, outputpath='./', outputfile='worms_matchfilter.txt', verbose=True, parallel=False, version=None):


    species_only=(identification_level=='species')
    init=True
    processed=False
    if parallel:
        store=True
        verbose=False
        return_filename=True
        if version is not None:
            outputfile=outputfile.split('.')[0]+f'{version}.txt'

    wormscallK = list(wormscall.keys())
    wormscallV = list(itemgetter(*wormscallK)(wormscall))
    colnames = ['group'] + wormscallV

    outputfile = os.path.join(outputpath,outputfile)

    if len(raw_scinames)==0:
        if return_filename:
            return outputfile, pd.DataFrame([],columns=colnames)
        else:
            return pd.DataFrame([],columns=colnames)

    # Pre-process the raw scientific names
    # to avoid quotation mark problems with pandas

    raw_scinames = preprocess_quotationMarks(raw_scinames)
    #raw_scinames=pd.Series(raw_scinames).str.replace('^["\s]+|["\s]+$','',regex=True)
    #raw_scinames=raw_scinames.str.replace("^['\s]+|['\s]+$",'',regex=True)
    #raw_scinames=list(set(raw_scinames.tolist()))

    Nsciname = len(raw_scinames)

    printv(f'            ** WoRMS filter (recognized marine taxa) | {Nsciname} unique scientific names', verbose=verbose)

    if ((not parallel) or (version is not None)) and os.path.isfile(outputfile):

        if overwrite:

            print(f"            WARNING | {outputfile} already exists and will be overwritten")

        else:

            print(f"            INFO | {outputfile} already exists and will be used")

            # Remaining raw scientific names

            raw_scinames, previous_wormsmatch = _resume_matchWoRMS(raw_scinames, outputfile)

            #previous_wormsmatch=pd.read_csv(outputfile, sep='\t')

            # Remaining raw scientific names

            #raw_scinames = _resume(raw_scinames, previous_wormsmatch['group'].tolist())

            if len(raw_scinames)==0:
                if return_filename:
                    return outputfile, previous_wormsmatch
                else:
                    return previous_wormsmatch

            else:
                printv(f'            UPDATE | {len(raw_scinames)}/{Nsciname} ({round(len(raw_scinames)/Nsciname*100,2)}%) remaining scientific names to be processed', verbose=verbose)
                init=False

    elif parallel and (version is None):

        # Search for an unused file name

        isfile=True
        version=random.randint(0,1000)
        output=outputfile.split('.')[0]
        while isfile:
            outputfile=output+f'{version}.txt'
            if not os.path.isfile(outputfile):
                isfile=False
            else:
                version=random.randint(0,1000)

    # Pre-process scientific names for WoRMS queries

    printv(f'            -- Scientific names pre-processing --', verbose=verbose)

    raw2worms_scinames=[]
    for idx,sci in enumerate(raw_scinames):

        preprocessing = _format_scinamesForWoRMS(sci, identification_level=identification_level, min_length=min_length, doublecheck=doublecheck)

        if len(preprocessing)==0:
            raw2worms_scinames+=[[sci,pd.NA]]
        else:
            raw2worms_scinames+=[[sci,proc] for proc in preprocessing]

    raw2worms_scinames=pd.DataFrame(raw2worms_scinames,columns=['rawsciname','wormssciname'])
    #print(raw2worms_scinames)
    #print("Length after pre-processing:",len(raw2worms_scinames))
    #unique=set(raw2worms_scinames.rawsciname.values)
    #print("Check number of unique raw scinames:",len(unique))
    #print()
    unique_wormsscinames = raw2worms_scinames.loc[~pd.isnull(raw2worms_scinames['wormssciname']),'wormssciname'].unique().tolist()

    #print("length:",len(unique_wormsscinames))
    #print()

    if len(unique_wormsscinames)==0:

        wormsmatch=raw2worms_scinames.copy()
        wormsmatch=wormsmatch.rename(columns={'rawsciname':'group'})
        wormsmatch[wormscallV]=pd.NA
        wormsmatch=wormsmatch[colnames]
        processed=True

    # Query WoRMS

    if not processed:

        fullwormsmatch=[]

        if parallel:
            tempfile=os.path.join(outputpath,f'wormsmatch{version}.temp')
        else:
            tempfile=os.path.join(outputpath,'wormsmatch.temp')

        if os.path.isfile(tempfile):

            ## Remaining pre-processed scientific names

            fullwormsmatch = pd.read_csv(tempfile,sep='\t')
            unique_wormsscinames = _resume(unique_wormsscinames, fullwormsmatch['wormssciname'].tolist())
            fullwormsmatch = fullwormsmatch.values.tolist()

        Nwormsscinames=len(unique_wormsscinames)

        printv(f'            -- WoRMS API call --', verbose=verbose)
        printv(f'            {Nwormsscinames} WoRMS-formatted scientific names to process', verbose=verbose)

        ## Break down the query into queries of 50 raw scientific names (WoRMS limit)

        nbatch = math.ceil(Nwormsscinames/50)

        if verbose:
            process=tqdm(range(nbatch), desc='            Progress')
        else:
            process=range(nbatch)

        for batch in process:

            start = batch*50
            if batch==(nbatch-1):
                end = Nwormsscinames
            else:
                end = start + 50

            ## WoRMS API call

            fullwormsmatch += _match50_WoRMSBySciname(unique_wormsscinames[start:end], wormscallK=wormscallK, species_only=species_only)

            ## Save progress

            if (((batch+1)%200)==0) or (end==Nwormsscinames):
                store_fullwormsmatch = pd.DataFrame(fullwormsmatch, columns=['wormssciname']+wormscallV)
                write_dataframe2txtfile(store_fullwormsmatch, tempfile, init=True)

        fullwormsmatch = pd.DataFrame(fullwormsmatch, columns=['wormssciname']+wormscallV)
        fullwormsmatch = pd.merge(raw2worms_scinames,fullwormsmatch,how='left',on=['wormssciname'])

        #print(fullwormsmatch)
        #print("length:",len(fullwormsmatch))
        #print()

        # Match WoRMS

        printv(f'            -- WoRMS match filter construction --', verbose=verbose)

        isduplicated = fullwormsmatch.duplicated(subset=['rawsciname'],keep=False)

        ## Unduplicated raw scientific name
        ## i.e associated with a unique WoRMS-formatted string

        wormsmatch = fullwormsmatch[~isduplicated]
        #print("(not NaN & NaN) unique:",len(wormsmatch))

        ## Duplicated raw scientific name
        ## i.e associated with more than one WoRMS-formatted string

        duplicated_wormsmatch = fullwormsmatch[isduplicated]

        isduplicated_match = (~pd.isnull(duplicated_wormsmatch[WORMSCALL['match_type']])) #duplicated match
        isduplicated_NaN = duplicated_wormsmatch[(~isduplicated_match)].duplicated(subset=['rawsciname'],keep=False) #duplicated NaN

        if sum(isduplicated_NaN)>0:

            ## For a given scientific name, several associated pre-processed strings do not match
            ## Keep only one (by default, the first one)

            duplicated_wormsNaN = duplicated_wormsmatch[(~isduplicated_match) & isduplicated_NaN]
            deduplicate_NaN = set(duplicated_wormsNaN.index) - set(duplicated_wormsNaN.drop_duplicates(subset=['rawsciname'],keep='first').index)
            deduplicate_NaN = list(set(duplicated_wormsmatch.index)-deduplicate_NaN)
            duplicated_wormsmatch = duplicated_wormsmatch.loc[deduplicate_NaN,:]

            isduplicated = duplicated_wormsmatch.duplicated(subset=['rawsciname'],keep=False)
            if sum(~isduplicated)>0:

                ## Unduplicated raw scientific name

                wormsmatch = pd.concat([wormsmatch,duplicated_wormsmatch[~isduplicated]],axis=0)
                #print("NaN duplicat:",len(duplicated_wormsmatch[~isduplicated]))

            ## Duplicated raw scientific name

            duplicated_wormsmatch = duplicated_wormsmatch[isduplicated]
            #bli=set(duplicated_wormsmatch.rawsciname.values)
            #print("match duplicat:",len(bli))

            isduplicated_match = (~pd.isnull(duplicated_wormsmatch[WORMSCALL['match_type']]))

        if sum(isduplicated_match)>0:

            ## For a given scientific name, several associated pre-processed strings match
            ## Keep only the first one (i.e the one with the best identification level, by construction)

            duplicated_wormsmatch = duplicated_wormsmatch[isduplicated_match]
            #print(duplicated_wormsmatch)
            #bli=set(duplicated_wormsmatch.rawsciname.values)
            #print("n sciname left:",len(bli))
            deduplicate_wormsmatch = duplicated_wormsmatch[['rawsciname','wormssciname']].set_index(['rawsciname','wormssciname']).index.unique().to_frame().drop_duplicates(subset=['rawsciname'],keep='first').values
            deduplicate_wormsmatch = pd.DataFrame(deduplicate_wormsmatch,columns=['rawsciname','wormssciname'])
            deduplicated_wormsmatch = pd.merge(duplicated_wormsmatch, deduplicate_wormsmatch, on=['rawsciname','wormssciname'])
            #bli=set(deduplicated_wormsmatch.rawsciname.values)
            #print(bli)
            #print("duplicat:",len(deduplicated_wormsmatch))

            wormsmatch=pd.concat([wormsmatch,deduplicated_wormsmatch],axis=0)

        wormsmatch=wormsmatch.rename(columns={'rawsciname':'group'})
        wormsmatch=wormsmatch[colnames]
        #print("final:",len(wormsmatch))

    # Store

    if store:

        printv(f'            -- Storing in {outputfile} --', verbose=verbose)

        wormsmatch.loc[pd.isnull(wormsmatch['worms_matchtype']),'worms_matchtype'] = 'nomatch'

        if 'valid_AphiaID' in wormscallK:
            wormsmatch[WORMSCALL['valid_AphiaID']] = wormsmatch[WORMSCALL['valid_AphiaID']].astype('Int64')

        write_dataframe2txtfile(wormsmatch, outputfile, init=init)

    # Clean

    os.remove(tempfile)

    if not init:
        wormsmatch=pd.concat([previous_wormsmatch,wormsmatch],axis=0).reset_index(drop=True)

    if return_filename:
        return outputfile, wormsmatch
    else:
        return wormsmatch


### Match WoRMS by valid aphiaIDs to get accepted scientific names ###


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


def _match50_WoRMSByAcceptedSciname(valid_aphiaID, wormscallK, species_only=True):

    if isinstance(valid_aphiaID, int):
        valid_aphiaID=[valid_aphiaID]

    aphiaID["aphiaids"] = valid_aphiaID
    worms_results = _connect_getAphiaRecordsByIDs(aphiaID)

    classification = []

    for idx,taxon in enumerate(worms_results):

        taxon = _process_rank(taxon, ismatchfilter=False, species_only=species_only)

        if pd.isnull(taxon['scientificname']):
            classification.append([valid_aphiaID[idx]] + [pd.NA]*len(wormscallK))
        else:
            classification.append([valid_aphiaID[idx]] + list(itemgetter(*wormscallK)(taxon)))

    return classification


def match_WoRMSByAcceptedSciname(valid_aphiaID, wormscall=WORMSCALL, species_only=True, store=True, overwrite=False, return_filename=False, outputpath='./', outputfile='worms_acceptedfilter.txt', verbose=True, parallel=False, version=None):

    if parallel:
        store=True
        verbose=False
        return_filename=True
        if version is not None:
            outputfile=outputfile.split('.')[0]+f'{version}.txt'

    wormscallK = list(wormscall.keys())
    wormscallV = list(itemgetter(*wormscallK)(wormscall))
    colnames = ['group'] + wormscallV
    outputfile = os.path.join(outputpath,outputfile)

    init=True
    NaphiaID = len(valid_aphiaID)

    printv(f'            ** WoRMS filter (accepted marine taxa) | {NaphiaID} unaccepted taxa',verbose=verbose)

    if NaphiaID==0:
        if return_filename:
            return outputfile, pd.DataFrame([],columns=colnames)
        else:
            return pd.DataFrame([],columns=colnames)

    if ((not parallel) or (version is not None)) and os.path.isfile(outputfile):

        if overwrite:

            print(f"            WARNING | {outputfile} already exists and will be overwritten")

        else:

            print(f"            INFO | {outputfile} already exists and will be used")

            print(len(valid_aphiaID))
            valid_aphiaID, previous_wormsaccepted = _resume_matchWoRMS(valid_aphiaID, outputfile)
            print(len(valid_aphiaID))
            print(previous_wormsaccepted[previous_wormsaccepted['species']=='Parastenhelia spinosa'])

            #previous_wormsaccepted = pd.read_csv(outputfile, sep='\t')
            #previous_wormsaccepted['valid_aphiaID'] = previous_wormsaccepted['valid_aphiaID'].astype('Int64')

            #valid_aphiaID = _resume(valid_aphiaID, previous_wormsaccepted['group'].tolist())

            if len(valid_aphiaID)==0:
                if return_filename:
                    return outputfile, previous_wormsaccepted
                else:
                    return previous_wormsaccepted
            else:
                printv(f'            UPDATE | {len(valid_aphiaID)}/{NaphiaID} ({round(len(valid_aphiaID)/NaphiaID*100,2)}%) remaining unaccepted taxa to be processed',verbose=verbose)
                init=False
                NaphiaID = len(valid_aphiaID)

    elif parallel and (version is None):

        # Search for an unused file name

        isfile=True
        version=random.randint(0,1000)
        output=outputfile.split('.')[0]
        while isfile:
            outputfile=output+f'{version}.txt'
            if not os.path.isfile(outputfile):
                isfile=False
            else:
                version=random.randint(0,1000)

    wormsaccepted=[]

    printv(f'            -- WoRMS API call --',verbose=verbose)
    printv(f'            {NaphiaID} valid scientific names to retrieve',verbose=verbose)

    nbatch = math.ceil(NaphiaID/50)

    #verbose_storage=False
    if verbose:
        #process=tqdm(range(nbatch))
        process=tqdm(range(nbatch), desc='            Progress')
    else:
        process=range(nbatch)

    for batch in process:

        start = batch*50
        if batch == (nbatch-1):
            end = NaphiaID
            #verbose_storage=True
        else:
            end = start + 50

        wormsaccepted += _match50_WoRMSByAcceptedSciname(valid_aphiaID[start:end], wormscallK=wormscallK)

        ## Save progress

        if store and ((((batch+1)%200)==0) or (end==NaphiaID)):
            store_wormsaccepted=pd.DataFrame(wormsaccepted,columns=colnames)
            store_wormsaccepted['valid_aphiaID']=store_wormsaccepted['valid_aphiaID'].astype('Int64')
            store_wormsaccepted['group']=store_wormsaccepted['group'].astype('Int64')
            write_dataframe2txtfile(store_wormsaccepted, outputfile, init=init) #, verbose=verbose_storage)

    wormsaccepted=pd.DataFrame(wormsaccepted,columns=colnames)
    if not init:
        wormsaccepted=pd.concat([previous_wormsaccepted,wormsaccepted],axis=0).reset_index(drop=True)

    wormsaccepted["valid_aphiaID"] = wormsaccepted["valid_aphiaID"].astype('Int64')
    wormsaccepted["group"] = wormsaccepted["group"].astype('Int64')

    if return_filename:
        return outputfile, wormsaccepted
    else:
        return wormsaccepted


### Parallel version of WoRMS match functions ###


def _retry_WoRMSmatch(func, future, tasks, executor, **params):

    # Retry a task that failed

    ## Get the associated data for the task
    data = tasks[future]["data"]
    id = tasks[future]["id"]
    count = tasks[future]["count"]

    ## Submit the task again
    retry = executor.submit(func,data,version=id[1],**params)

    ## Store to track the retries
    tasks[retry] = {}
    tasks[retry]["id"] = id
    tasks[retry]["data"] = data
    tasks[retry]["count"] = count+1

    return tasks[future]["id"], tasks[retry]["count"]


def _parallel_WoRMSmatch(func_WoRMSmatch, data, cpu, max_attempt=3, outputfile='', outputpath='./', resume_parallel=True, store_parallel=True, overwrite_parallel=False, **params):

    params['outputpath']=outputpath
    params['outputfile']=outputfile

    if len(outputfile)==0:
        outputfile=f'{func_WoRMSmatch}_results.txt'
        resume_parallel=False

    outputfile = os.path.join(outputpath,outputfile)

    results=[]
    tempfiles=[]

    if os.path.isfile(outputfile):
            if resume_parallel:
                print(f"            INFO | {outputfile} already exists and will be used (`resume_parallel`={resume_parallel})")
                if func_WoRMSmatch.__name__=='match_WoRMSBySciname':
                    data = preprocess_quotationMarks(data)
                data, previous = _resume_matchWoRMS(data, outputfile)
                results.append(previous)
            else:
                print(f"            INFO | {outputfile} already exists but won't be used (`resume_parallel`={resume_parallel})")

    Ndata=len(data)
    index=list(range(Ndata))

    if Ndata!=0:

        # Dispatch the scientific names to be processed

        length=math.ceil(Ndata/cpu)
        cpu_split=[subset for subset in zip(index[::length],index[length::length]+[len(index)])]

        print_slices=[f'slice n°{i+1}: {slice},' for i,slice in enumerate(cpu_split)]
        Nlines=math.ceil(len(print_slices)/3)
        for line in range(Nlines):
            print('            ' + ' '.join(print_slices[line*3:line*3+3]))

        completed=0

        # Create a process pool

        with ProcessPoolExecutor(max_workers=cpu) as executor:

            start=time.time()

            # Submit the tasks into the pool

            tasks = {executor.submit(func_WoRMSmatch,data[i:j],version=j,**params):{'id':(i,j),'data':data[i:j],'count':1} for i,j in cpu_split}

            # Retry until all tasks have been completed,
            # or the maximum number of attempts has been reached for failed tasks

            while completed<cpu:

               for future in as_completed(tasks):

                   if future.exception():
                       id, count = _retry_WoRMSmatch(func_WoRMSmatch, future, tasks, executor, **params)
                       if count==max_attempt:
                           print(f'            Failure: More than {max_attempt} attempts, slice {id} will not be processed. Please try again later.')
                           print(f'            Exception: {future.exception()}')
                           cpu-=1
                           future.result()
                       else:
                           print(f'            Failure: Retrying slice {id} (attempt n°{count})')
                           print(f'            Exception: {future.exception()}')
                           future.result()
                   else:
                       end=time.time()
                       res=future.result()
                       tempfiles.append(res[0])
                       results.append(res[1])
                       print(f'            Success: slice {tasks[future]["id"]} completed ({tasks[future]["count"]} attempt(s)) | TIME: {round(end-start)}s')
                       completed+=1

                   tasks.pop(future)

    wormsmatch=pd.concat(results,axis=0).reset_index(drop=True)

    # Store

    if store_parallel and (Ndata!=0):

        #if len(outputfile)==0:
        #    outputfile=f'{func_WoRMSmatch}_results.txt'

        #outputfile = os.path.join(outputpath,outputfile)

        if os.path.isfile(outputfile):

            if overwrite_parallel:
                print(f"            WARNING | {outputfile} already exists and will be overwritten")
                write_dataframe2txtfile(wormsmatch, outputfile, init=True, verbose=True)

            else:
                print(f"            INFO | {outputfile} already exists and will be modified")
                write_dataframe2txtfile(wormsmatch, outputfile, init=False, verbose=True)

        else:
            write_dataframe2txtfile(wormsmatch, outputfile, init=True, verbose=True)

    # Clean

    for file in tempfiles:
        os.remove(file)

    return outputfile, wormsmatch


def parallel_match_WoRMSBySciname(raw_scinames, cpu, wormscall=WORMSCALL, identification_level='species', min_length=3, doublecheck=True, max_attempt=3, outputpath='./', outputfile='worms_matchfilter.txt', resume_parallel=True, overwrite=False, store_parallel=True, overwrite_parallel=False, **ignored):

    params_match_WoRMSBySciname = {
                                   'wormscall':wormscall,
                                   'identification_level':identification_level,
                                   'min_length':min_length,
                                   'doublecheck':doublecheck,
                                   'store':True,
                                   'overwrite':overwrite,
                                   'verbose':False,
                                   'parallel':True,
                                   'return_filename':True
                                  }

    params_parallel = {
                       'cpu':cpu,
                       'max_attempt':max_attempt,
                       'outputfile':outputfile,
                       'outputpath':outputpath,
                       'resume_parallel':resume_parallel,
                       'store_parallel':store_parallel,
                       'overwrite_parallel':overwrite_parallel
                      }

    if len(outputfile)==0:
        outputfile='worms_matchfilter.txt'

    outputfile, wormsmatch = _parallel_WoRMSmatch(match_WoRMSBySciname, raw_scinames, **params_parallel, **params_match_WoRMSBySciname)

    return outputfile, wormsmatch


def parallel_match_WoRMSByAcceptedSciname(valid_aphiaID, cpu, wormscall=WORMSCALL, species_only=True, max_attempt=3, outputpath='./', outputfile='worms_acceptedfilter.txt', resume_parallel=True, overwrite=False, store_parallel=True, overwrite_parallel=False, **ignored):

    params_match_WoRMSByAcceptedSciname = {
                                           'wormscall':wormscall,
                                           'species_only':species_only,
                                           'store':True,
                                           'overwrite':overwrite,
                                           'verbose':False,
                                           'parallel':True,
                                           'return_filename':True
                                          }

    params_parallel = {
                       'cpu':cpu,
                       'max_attempt':max_attempt,
                       'outputfile':outputfile,
                       'outputpath':outputpath,
                       'resume_parallel':resume_parallel,
                       'store_parallel':store_parallel,
                       'overwrite_parallel':overwrite_parallel
                      }

    if len(outputfile)==0:
        outputfile='worms_acceptedfilter.txt'

    outputfile, wormsmatch = _parallel_WoRMSmatch(match_WoRMSByAcceptedSciname, valid_aphiaID, **params_parallel, **params_match_WoRMSByAcceptedSciname)

    return outputfile, wormsmatch


### Create WoRMS filters ###


def create_WoRMSfilter(gzfile_path, colname, wormscall=WORMSCALL, identification_level='species', min_length=3, doublecheck=True, store=True, outputpath='./', overwrite=False, parallel=True, resume_parallel=True, max_attempt=3, store_parallel=True, overwrite_parallel=False):

    if parallel:

        # To avoid compromising WoRMS performance to the detriment of other users, use a maximum of 2 CPUs
        # Inform WoRMS if necessary

        #if cpu is None:
        #    cpu=len(os.sched_getaffinity(0))
        cpu=2
        print(f'            INFO | {cpu} CPUs will be used')

        if parallel and (store!=store_parallel):
            raise ValueError(f'parallel={parallel} and store={store} but store_parallel={store_parallel}')

    storeparams = {
                   'store':store,
                   'outputpath':outputpath,
                   'overwrite':overwrite
                  }

    params_parallel = {
                       'cpu':cpu,
                       'max_attempt':max_attempt,
                       'resume_parallel':resume_parallel,
                       'store_parallel':store_parallel,
                       'overwrite_parallel':overwrite_parallel
                      }

    # Get unique species

    unique_rawscinames = get_uniqueRawSciname(gzfile_path, colname=colname, **storeparams)

    if len(unique_rawscinames)==0:
        print(f'            No scientific name. Is {gzfile_path} empty?')
        return None, None

    # Get WoRMS-recognized classifications

    params_func = {
                   'wormscall':wormscall,
                   'identification_level':identification_level,
                   'min_length':min_length,
                   'doublecheck':doublecheck
                  }

    params_func.update(storeparams)

    if parallel and (len(unique_rawscinames)>=1000):
        print(f'            ** WoRMS filter (recognized marine taxa) | {len(unique_rawscinames)} unique scientific names')
        params_func['verbose']=False
        _, worms_matchfilter = parallel_match_WoRMSBySciname(unique_rawscinames, **params_parallel, **params_func)
    else:
        params_func['verbose']=True
        worms_matchfilter = match_WoRMSBySciname(unique_rawscinames, **params_func)

    # Get WoRMS-accepted classifications

    params_func = {
                   'wormscall':wormscall,
                   'species_only':(identification_level=='species'),
                   'return_filename':True,
                  }

    params_func.update(storeparams)

    ## Find unaccepted scientific names

    isunaccepted = (worms_matchfilter['worms_status']!='accepted') & (~pd.isnull(worms_matchfilter['valid_aphiaID']))
    unaccepted_aphiaID = worms_matchfilter.loc[isunaccepted, 'valid_aphiaID'].unique().tolist()

    if len(unaccepted_aphiaID)==0:
        print(f'            ** WoRMS filter (accepted marine taxa) | {len(unaccepted_aphiaID)} unaccepted taxa')
        return worms_matchfilter, None

    if parallel and (len(unaccepted_aphiaID)>=1000):
        print(f'            ** WoRMS filter (accepted marine taxa) | {len(unaccepted_aphiaID)} unaccepted taxa')
        params_func['verbose']=False
        filename, worms_acceptedfilter = parallel_match_WoRMSByAcceptedSciname(unaccepted_aphiaID, **params_parallel, **params_func)
    else:
        params_func['verbose']=True
        filename, worms_acceptedfilter = match_WoRMSByAcceptedSciname(unaccepted_aphiaID, **params_func)

    # Process subspecies

    params_func['store']=False
    params_func['return_filename']=False

    ## Find subspecies
    issubspecies = (worms_acceptedfilter['worms_status']=="subspecies") & (~pd.isnull(worms_acceptedfilter["valid_aphiaID"]))

    temp=worms_acceptedfilter[(worms_acceptedfilter['worms_status']=="subspecies") & (pd.isnull(worms_acceptedfilter["valid_aphiaID"]))] #SUPPRESS
    if len(temp)!=0:
        print()
        print(temp)
        print()

    subspecies = worms_acceptedfilter.loc[issubspecies,['valid_aphiaID']].rename(columns={'valid_aphiaID':'group'})
    parent_aphiaID = subspecies['group'].unique().tolist()

    ## Retrieve species associated with subspecies.
    print(f'            ** WoRMS filter (subspecies) | {len(parent_aphiaID)} subspecies')

    if parallel and (len(parent_aphiaID)>=1000):
        params_func['verbose']=False
        _, parent_classification = parallel_match_WoRMSByAcceptedSciname(parent_aphiaID, cpu=cpu, max_attempt=max_attempt, store_parallel=False, **params_func)
    else:
        params_func['verbose']=True
        parent_classification = match_WoRMSByAcceptedSciname(parent_aphiaID, **params_func)

    subspecies = subspecies.reset_index().merge(parent_classification,how='inner',on='group').set_index('index')

    ## Ensure consistency of identifiers
    # In most cases there should be equality,
    # but sometimes there is circularity between identifiers
    # e.g. for “Parastenhelia spinosa”: valid_AphiaID=116446 to parentNameUsageID=116446 to valid_AphiaID=1164466

    subspecies['valid_aphiaID']=subspecies['group']

    ## Replace subspecies classification with associated species classification in the WoRMS-accepted filter

    index, columns = subspecies.index, list(set(worms_acceptedfilter.columns) - set(['group']))
    worms_acceptedfilter.loc[index, columns] = subspecies.loc[index, columns]

    # Store WoRMS-accepted filter

    ## Ensure consistency of identifiers

    print(worms_acceptedfilter[worms_acceptedfilter['valid_aphiaID']!=worms_acceptedfilter['group']])
    worms_acceptedfilter['valid_aphiaID']=worms_acceptedfilter['group']

    ## Store

    if store:
        write_dataframe2txtfile(worms_acceptedfilter, filename, init=True, verbose=True)

    return worms_matchfilter, worms_acceptedfilter


################ Tests ################

def test():

    start=time.time()
    worms_matchfilter, worms_acceptedfilter=create_WoRMSfilter('/mnt/smartbiodiv/gbifbuilding/gbif.txt.gz', colname='verbatimScientificName', wormscall=WORMSCALL, identification_level='species', min_length=3, doublecheck=True, store=True, outputpath='/data/smartbiodiv/eberhocoi/source/debug/', overwrite=False, parallel=True, max_attempt=3, store_parallel=True, overwrite_parallel=False)
    end=time.time()

    print(f'TIME : {round(end - start,0)}s')

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Create WoRMS filters')
    parser.add_argument('gbif_tsv_gzfile', type=str, help='path to the gzip tab-separated file to be processed')
    parser.add_argument('colname', type=str, help='column containing raw scientific names')
    parser.add_argument('--wormscall', type=json.loads, help='dictionary containing the WoRMS variables to keep and the names under which to store them', default=str(WORMSCALL))
    parser.add_argument('--identification_level', type=str, help="should be 'best', 'species' or 'first'", default='species')
    parser.add_argument('--min_length', type=int, help='minimum length of the terms comprising the scientific name', default=3)
    parser.add_argument('--doublecheck', action=argparse.BooleanOptionalAction, help='double-check or not three-word scientific names by querying only the first two words', default=True)
    parser.add_argument('--store', action=argparse.BooleanOptionalAction, help='whether to store the filters', default=True)
    parser.add_argument('--output_path', type=str, help='path to folder where files will be stored', default='./')
    parser.add_argument('--overwrite', action=argparse.BooleanOptionalAction, help='overwrite existing filters', default=False)
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='parallelize requests (maximum 2 CPUs)', default=False)
    parser.add_argument('--resume_parallel', action=argparse.BooleanOptionalAction, help='reuse existing filters in parallelized mode', default=True)
    parser.add_argument('--max_attempt', type=int, help='maximum number of retries in case of errors when running in parallelized mode', default=3)
    parser.add_argument('--store_parallel', action=argparse.BooleanOptionalAction, help='whether to store the filters in parallelized mode', default=True)
    parser.add_argument('--overwrite_parallel', action=argparse.BooleanOptionalAction, help='overwrite existing filters in parallelized mode', default=False)

    args = parser.parse_args()
    params = {
              'wormscall': args.wormscall,
              'identification_level': args.identification_level,
              'min_length': args.min_length,
              'doublecheck': args.doublecheck,
              'store': args.store,
              'output_path': args.output_path,
              'resume_parallel': args.resume_parallel,
              'overwrite': args.overwrite,
              'parallel': args.parallel,
              #'cpu': args.cpu,
              'max_attempt': args.max_attempt,
              'store_parallel': args.store_parallel,
              'overwrite_parallel': args.overwrite_parallel
             }

    print(f'    * Creating the files needed for WoRMS filtering')

    start=time.time()

    _ = create_WoRMSfilter(args.gbif_tsv_gzfile, args.colname, **params)

    end=time.time()

    print(f'TIME : {round(end - start,0)}s')
