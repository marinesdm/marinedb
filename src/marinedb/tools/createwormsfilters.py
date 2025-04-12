#!/usr/bin/env python3
# coding: utf-8

# External import

import argparse
import gzip
import pandas as pd
import math
import yaml
import time
import glob
import os
from unidecode import unidecode
from operator import itemgetter
import re
from datetime import datetime
from datetime import date
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from tqdm import tqdm

from suds.client import Client
from suds.sudsobject import items
import http

# Internal import

from marinedb.utils import readfile
from marinedb.utils import regexstrip
from marinedb.utils import standardizenan
from marinedb.utils import writedataframe
from marinedb.utils.allexport import export
from marinedb.utils.standardizenan import isnan
from marinedb.utils import preprocessquotationmark
from marinedb.tools import subsetranks

# Global variables

__all__ = [] # populated using the @export decorator

PATH = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(PATH,'ignoreWords.yaml'),'r') as f:
    file = yaml.safe_load(f)
    IGNOREWORDS = file['SCN_IGNORE'] + file['AUTHORSHIP_IGNORE']
IGNOREWORDS = sorted(IGNOREWORDS, key=len, reverse=True)
IGNOREWORDS = '|'.join([fr'{word}' for word in IGNOREWORDS])

YEAR_NOW = datetime.now().year

LOWER_THAN_SPECIES = subsetranks.apply('species', lower=True, strict=True)

## Map custom vocabulary to WoRMS vocabulary

 ###########################################
 # Do not remove starred dictionary keys #
 ###########################################

WORMSCALL = [
             'scientificname', #*
             'genus',
             'family',
             'order',
             'cls',
             'phylum',
             'kingdom',
             'match_type', #*
             'status', #*
             'valid_AphiaID', #*
             'isExtinct',
             'isMarine',
             'rank', #*
             'authority'
            ]

## Instantiate a client and objects to serve as arguments for the WoRMS functions

cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)

scinames = cl.factory.create('scientificnames')
scinames['_arrayType'] = 'string[]'

aphiaID = cl.factory.create('aphiaids')
aphiaID['_arrayType'] = 'int[]'


def printv(message, verbose=True):
    if verbose:
        print(message)
    return True


### Get unique raw scientific names ###


def update_set(myset,key):
    if isnan(key, letters_only=True):
        return myset
    myset.add(key)
    return myset

def store_uniqueRawSciname(unique_rawsciname, outputfile, indent=''):
    print(indent + f'Storing in {outputfile} | {len(unique_rawsciname)} unique raw scientific names')
    with open(outputfile, 'w') as f:
        f.writelines('\n'.join(['raw_sciname'] + list(unique_rawsciname)))

@export
def get_uniqueRawSciname(filepath, colname, resume=True, store=False, overwrite=False, outputpath='./', outputfile='', indent=''):

    print(indent + f'** Retrieving unique raw scientific names from {filepath}')

    unique_rawsciname = set()

    if len(outputfile) == 0:
        outputfile = f'unique_{colname}.txt'
    outputfile = os.path.join(outputpath,outputfile)

    if os.path.isfile(outputfile):

        if resume:
            print(indent + f'INFO | {outputfile} already exists and will be used (`resume`={resume})')
            unique_rawsciname = set(pd.read_csv(outputfile, sep='\t').values.flatten())

        if store:
            if overwrite:
                print(indent + f'WARNING | {outputfile} exists and will be overwritten (`overwrite`={overwrite})')
            else:
                previous_outputfile = outputfile
                left = outputfile.split('.')[0]
                right = outputfile.split('.')[1]
                outputfile = left + f'{date.today().strftime("_%Y%m%d")}.' + right
                print(indent + f'INFO | unique raw scinames will be stored in {outputfile} (`overwrite`={overwrite})')

    start = time.time()

    open_file, decode_line = readfile.apply(filepath)

    with open_file(filepath,'r') as data:

        header = decode_line(data.readline()).strip('\n').split('\t')
        sciname_index = header.index(colname)
        count = len(unique_rawsciname)

        for idx, line in enumerate(data):

            # Pre-process the raw scientific names
            # to avoid quotation problems with pandas

            sciname = decode_line(line).strip('\n').split('\t')[sciname_index]
            sciname = preprocessquotationmark.apply(sciname)

            # Update the set of unique raw scientific names

            unique_rawsciname = update_set(unique_rawsciname,sciname)
            Nunique = len(unique_rawsciname)

            # Display progress

            if ((idx+1)%1000000) == 0:
                print(indent + f'Processing | {idx + 1} lines done ({round(time.time()-start)}s), {len(unique_rawsciname)} unique raw scientific names')

            # Save progress

            if store and ((Nunique-count) == 100000):
                store_uniqueRawSciname(unique_rawsciname, outputfile, indent=indent)
                count = Nunique


    # Store list of unique raw scientific names

    if store:
        store_uniqueRawSciname(unique_rawsciname, outputfile, indent=indent)

    print(indent + f'TIME: {round(time.time()-start)}s')

    return list(unique_rawsciname)


### Pre-process scientific names for WoRMS queries ###


def format_scinamesForWoRMS_elementwise(raw_sciname, identification_level='species', min_length=3, min_words=2):

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

        next = True
        keep = False

        return sciname, next, keep

    # Capitalise the first letter, if necessary

    sciname = sciname[0].upper() + sciname[1:]

    # Standardise whitespace

    sciname = re.sub(r'\s+',' ',sciname)

    # Check whether the scientific name is identified at species level or not
    # and check that it meets the minimum word length criterion

    sciname_split = sciname.split()

    if len(sciname_split) == 1:

        ## Rank higher than species

        if (identification_level == 'species') or (min_words == 2):

            next = True
            keep = False

        elif len(sciname) < min_length:

            ## Do not meet minimum word length criterion

            next = True
            keep = False

        elif (identification_level == 'best'): #i.e also len(sciname)>=min_length and min_words==1

            next = True
            keep = True

        else: #i.e identification_level=='first' and len(sciname)>=min_length and min_words==1

            next = False
            keep = True

    else:

        if len(sciname_split[0]) < min_length:

            ## Do not meet minimum word length criterion

            next = True
            keep = False

        else:

            if len(sciname_split[1]) < min_length:

                ## Do not meet minimum word length criterion

                if (identification_level == 'species') or (min_words == 2):

                    next = True
                    keep = False

                elif (identification_level == 'first'):

                    ## Keep only the first word

                    sciname = sciname_split[0]
                    next = False
                    keep = True

                else: #i.e identification_level=='best' and min_words==1:

                    ## Keep only the first word

                    sciname = sciname_split[0]
                    next = True
                    keep = True

            else:

                ## Rank less than or equal to species
                ## and minimum word length criterion met

                next = False
                keep = True

    return sciname, next, keep


def format_scinamesForWoRMS(raw_scinames, identification_level='species', min_length=3, doublecheck=True): # 'best', 'species', 'first'

    wormsscinames = []

    if identification_level == 'species':
        min_words = 2
        min_stringlength = min_words*min_length+1
    else:
        min_words = 1
        min_stringlength = min_words*min_length


    if (pd.isnull(raw_scinames)) or (len(raw_scinames) == 0):
        return wormsscinames

    # Do not proceed with the code if hybrid name
    # e.g. "Branta hutchinsii x Branta leucopsis"
    # e.g. "Branta hutchinsii xBranta leucopsis"
    # e.g. "Junco X Zonotrichia hyemalis X albicollis"

    if re.search(r'(^|\s)x([A-Z\s]|$)|×|\sX\s',raw_scinames):
        return wormsscinames

    scinames2process = raw_scinames

    # Solve any encoding problems

    try:
        scinames2process = scinames2process.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # Delete parts of the string containing a number:
    # - greater than the current year or lower than 1600
    # - less than 3 digits
    # - or more than 4 digits
    # i.e a number that cannot be the authorship year
    # i.e a word that probably refers to a sequenced-based observation
    # e.g. "Megaselia sp. BIOUG27368-A01"
    # e.g. "BOLD:AEF8294"

    pattern = r'(?:(?<=^)|(?<=[(\[\s]))[^(\[\)\]\s]*?(?P<number>[0-9]+)[^)\](\[\s]*?(?:(?=[)\]\s])|(?=$))'
    finditer = re.finditer(pattern,scinames2process)

    cut = [0]
    for match in finditer:
        number = match['number']
        Ndigits = len(number)
        if (Ndigits <= 3) or (Ndigits>4) or (int(number)>YEAR_NOW) or (int(number)<1600):
            cut.append(match.start())
            cut.append(match.end())
    cut.append(len(scinames2process))

    if len(cut)>2:
        scinames2process = ' '.join([scinames2process[i:j] for i,j in zip(cut[0::2],cut[1::2])])

    # Detect two common format errors and process the string accordingly

    if identification_level != 'first':

        ## "String1 STRING2 STRING3 ..." to "String1 string2"
        # e.g. "Neotoma CINEREA ACRAEA" to "Neotoma cinerea"
        pattern = r'^[^a-zA-Z0-9]*([A-Z][a-z]{2,}\s+[A-Z]{3,})\s+[A-Z]{3,}' #minimum word length: 3 characters
        match = re.search(pattern,scinames2process)
        if match is not None:
            match = match.group(1).lower()
            match = match[0].upper()+match[1:]
            match, _, keep = format_scinamesForWoRMS_elementwise(match, identification_level=identification_level, min_length=min_length, min_words=2)
            if keep:
                wormsscinames.append(match)

        ## "String1 String2[.] string3 ..." to "String1 string3"
        # e.g. "Graneledone Eledoninae verrucosa" to "Graneledone verrucosa"
        # e.g. "Pseudobarbella Nog. levieri" to "Pseudobarbella levieri"
        pattern = r'^[^a-zA-Z0-9]*([A-Z][a-z]{2,})\s+[A-Z][a-z]{2,}\.*\s+([a-z]{3,}\.?)'
        match = re.search(pattern,scinames2process)
        if match is not None:
            match = match.group(1) + ' ' + match.group(2)
            match, _, keep = format_scinamesForWoRMS_elementwise(match, identification_level=identification_level, min_length=min_length, min_words=2)
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

    scinames2process = unidecode(scinames2process)

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
    #     or is not identified at species level when `identification_level` is 'species' or 'best'
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

    next = True
    idx = 0
    preprocessed = []
    Nscinames = len(scinames2process)

    while next and (idx<Nscinames):

        # Standardise the scientific name

        sciname = regexstrip.apply(scinames2process[idx], pattern=r'^[^a-zA-Z]|[^a-zA-Z\.]$')

        Nwords = len(re.split(r'[\s_]+',sciname))
        stringlength = len(sciname)

        if (Nwords >= min_words) and (stringlength >= min_stringlength):

            # Meets minimum word count and minimum string length criteria

            sciname, next, keep = format_scinamesForWoRMS_elementwise(sciname, identification_level=identification_level, min_length=min_length, min_words=min_words)

            if keep:

                sciname = sciname.split()

                if (len(sciname)>2) and (len(sciname[2])<min_length):
                    sciname = ' '.join(sciname[:2])
                else:
                    sciname = ' '.join(sciname[:3])

                preprocessed.append(sciname)

                if identification_level == 'best':
                    min_words = 2
                    min_stringlength = min_words*min_length+1

            if next:

                # Not a scientific name (or not at the species level)

                idx += 1

        else:

            # Empty string or too short to be a scientific name (or not at the species level)

            idx += 1

    if len(preprocessed) != 0:
        wormsscinames += preprocessed

    # Delete duplicates & Sort by number of words (subspecies-species-higher order)

    wormsscinames = list(set(wormsscinames))  # e.g. "Helius Helius mainensis" to ["Helius mainensis","Helius mainensis"]
    wormsscinames = sorted(wormsscinames,key=(lambda string: string.count(' ')),reverse=True)

    if (len(wormsscinames) >= 2):

        # Two or more candidates for the WoRMS API call

        if (wormsscinames[0].count(' ')>1) and (wormsscinames[1].count(' ') == 1) and (wormsscinames[1] in wormsscinames[0]):

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


def resume(values2process, valuesprocessed):

    # Return processed and unprocessed values

    remaining_values = set(values2process) - set(valuesprocessed)
    completed_values = set(values2process) - remaining_values

    return list(completed_values), list(remaining_values)

def resume_matchWoRMS(values2process, keys, outputfile, isrecognizedmatch, resume_mode='soft'):

    valuesprocessed = pd.read_csv(outputfile, sep='\t', dtype=object)
    if not isrecognizedmatch:
        valuesprocessed['group'] = valuesprocessed['group'].astype('Float64').astype('Int64')

    if len(set(keys)-set(valuesprocessed.columns)) == 0:
        valuesprocessed_list, values2process = resume(values2process, valuesprocessed['group'].tolist())
        if resume_mode == 'hard':
            if len(valuesprocessed_list) == 0:
                valuesprocessed = None
            else:
                valuesprocessed = valuesprocessed.reset_index().set_index('group').loc[valuesprocessed_list,:]
                valuesprocessed = valuesprocessed.reset_index().set_index('index').rename_axis(None,axis=0)
    else:
        # missing required WoRMS keys
        valuesprocessed = None

    return values2process, valuesprocessed

def astype_Int64(wormsmatch, wormscall, isrecognizedmatch):

    if isrecognizedmatch:
        IDcolnames = []
    else:
        IDcolnames = ['group']

    IDcolnames += [col for col in wormscall if ('ID' in col) or (col[:2] == 'is')]

    wormsmatch[IDcolnames] = wormsmatch[IDcolnames].astype('Float64').astype('Int64')

    return wormsmatch

def remove_worms_escapecharacters(worms_results):

    freetext_wormskeys = set(['scientificname','authority','valid_authority','citation'])
    wormscallK = set(worms_results.keys())
    process = list(freetext_wormskeys.intersection(wormscallK))

    for key in process:
        if not pd.isnull(worms_results[key]):
            worms_results[key] = re.sub(r'(\n)|(\t)',' ',worms_results[key])
            worms_results[key] = worms_results[key].strip()

    return worms_results

def process_rank(worms_results, isrecognizedmatch):

    rank = worms_results['rank']

    if pd.isnull(rank):
        return worms_results
    else:
        rank = rank.lower()

    if rank != 'species':

        if rank in LOWER_THAN_SPECIES:

            # The taxon is identified at a rank lower than species

            parent_aphiaID = worms_results['parentNameUsageID']

            subcondition = ((worms_results['status'] == 'accepted') or pd.isnull(worms_results['valid_AphiaID'])) # e.g. Megaptera novaeangliae australis
            condition = ((not isrecognizedmatch) or (isrecognizedmatch and subcondition))

            if not pd.isnull(parent_aphiaID):

                # Mark the taxon as a subspecies for later processing

                worms_results['status'] = 'subspecies'

                if condition:

                    # Resolve unaccepted status before addressing ranks below species
                    # in scientific name matching
                    # i.e leave the identifier unchanged:
                    #     - unless the taxon is accepted
                    #     - lack a valid AphiaID
                    #     - or during the creation of the WoRMS accepted filter
                    # e.g. The matching process of "Isodictya delicata var. megachela"
                    #      could result in:
                    #      - either valid_aphiaID=1731907 "Isodictya megachela" (unaccepted status first)
                    #      - or parentNameUsageID=168450 "Isodictya delicata" (subspecies first)
                    #      depending on the processing order

                    worms_results['valid_AphiaID'] = parent_aphiaID

        else:

            # The taxon is identified at a rank higher than species

            worms_results['scientificname'] = pd.NA
            worms_results['match_type'] = 'match_abovespecies'

    return worms_results


### Match WoRMS by pre-processed scientific names ###


def connect_matchAphiaRecordsByNames(wormsscinames, max_attempt=10, pause_duration=5):

    global cl

    attempt = 0
    while attempt < max_attempt:
        try:
            return cl.service.matchAphiaRecordsByNames(wormsscinames)
        except (http.client.RemoteDisconnected, TimeoutError) as err:
            attempt += 1
            if attempt < max_attempt:
                time.sleep(pause_duration)
                cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
            else:
                raise Exception(f'`createwormsfilters.py` | {type(err).__name__}: {err}')

from difflib import get_close_matches #DEBUG
def parse_matchAphiaRecordsByNames(sciname, worms_results, wormscall, species_only=True):

    # Extract the match information specified in `wormscall`

    match_idx = wormscall.index('match_type')
    classification = []
    error=False #DEBUG

    if len(worms_results) != 0:

        for taxon in worms_results: # may be more than one candidate

            taxon = dict(items(taxon))
            taxon = remove_worms_escapecharacters(taxon)
            taxon = process_rank(taxon, isrecognizedmatch=True)

            if pd.isnull(taxon['scientificname']) and species_only:
                values = [sciname] + [pd.NA]*len(wormscall)
                values[match_idx+1] = taxon['match_type']
                classification.append(values)

            else:
                classification.append([sciname] + list(itemgetter(*wormscall)(taxon)))
                if not pd.isnull(taxon['scientificname']): #DEBUG
                    resc = get_close_matches(taxon['scientificname'],[sciname],cutoff=0.5) # DEBUG
                    if len(resc)==0: #DEBUG
                        print(f"ERROR: sciname={sciname} & worms={taxon['scientificname']}") #DEBUG
                        error=True #DEBUG
    else:
        values = [sciname] + [pd.NA]*len(wormscall)
        values[match_idx+1] = 'nomatch'
        classification.append(values)

    return classification, error #DEBUG

def match50_WoRMSBySciname(wormsscinames, wormscall, species_only=True):

    if isinstance(wormsscinames,str):
        wormsscinames = [wormsscinames]

    scinames['scientificname'] = wormsscinames
    worms_results = connect_matchAphiaRecordsByNames(scinames)
    if len(worms_results) != len(wormsscinames): #DEBUG
        print('wormssciname')
        print(wormsscinames)
        print('result')
        print(worms_results)
        raise Exception
    # Keep only the match information specified in `wormscall`

    classification = []

    for idx,res in enumerate(worms_results):

#        classification += parse_matchAphiaRecordsByNames(wormsscinames[idx], res, wormscall, species_only=species_only)
        classif, error = parse_matchAphiaRecordsByNames(wormsscinames[idx], res, wormscall, species_only=species_only)
        classification += classif
        if error: #DEBUG
            print('request')
            print(wormsscinames)
            print(f'len: {len(wormsscinames)}')
            print('result')
            print([val[wormscall.index('scientificname') + 1] for val in classif])
            print(f'len: {len(classif)}')
            #print('result')
            #print(worms_results)
            print()
            print()

    return classification


def match_WoRMSBySciname(raw_scinames, wormscall=WORMSCALL, identification_level='species', min_length=3, doublecheck=True, resume=True, resume_mode='soft', store=True, overwrite=False, return_filename=False, outputpath='./', outputfile='worms_matchfilter.txt', verbose=True, indent='', parallel=False, version=None):

    # Parameters

    species_only = (identification_level == 'species')
    concat = False
    processed = False
    colnames = ['group'] + wormscall
    outputfile = os.path.join(outputpath,outputfile)

    if parallel:

        store = True
        verbose = False
        return_filename = True

        if version is not None:

            outputfile = outputfile.split('.')[0]+f'{version}.txt'

        else:

            # Search for an unused file name

            isfile = True
            version = random.randint(0,1000)
            left = outputfile.split('.')[0]
            right = outputfile.split('.')[1]

            while isfile:

                outputfile = left + f'{version}.' + right

                if not os.path.isfile(outputfile):
                    isfile = False
                else:
                    version = random.randint(0,1000)

    Nscinames = len(raw_scinames)

    printv(indent + f'** WoRMS filter (recognized marine taxa) | {Nscinames} unique scientific names', verbose=verbose)

    if Nscinames == 0:

        # No raw scientific name to process

        if return_filename:
            return outputfile, pd.DataFrame([],columns=colnames)
        else:
            return pd.DataFrame([],columns=colnames)

    # Pre-process the raw scientific names
    # to avoid quotation mark problems with pandas

    raw_scinames = preprocessquotationmark.apply(raw_scinames)
    raw_scinames = list(set(raw_scinames))

    if os.path.isfile(outputfile):

        if resume:

            printv(indent + f'INFO | {outputfile} already exists and will be used', verbose=verbose)

            # Remaining raw scientific names

            raw_scinames, previous_wormsmatch = resume_matchWoRMS(raw_scinames, colnames, outputfile, isrecognizedmatch=True, resume_mode=resume_mode)

            if previous_wormsmatch is None:
                printv(indent + f'INFO | {outputfile.split("/")[-1]} lacks required columns or shared scinames. Run from scratch.', verbose=verbose)

            else:

                previous_wormsmatch = astype_Int64(previous_wormsmatch, wormscall, isrecognizedmatch=True)

                if len(raw_scinames) == 0:
                    printv(indent + f'UPDATE | all scientific names processed', verbose=verbose)
                    if return_filename:
                        return outputfile, previous_wormsmatch
                    else:
                        return previous_wormsmatch

                else:
                    printv(indent + f'UPDATE | {len(raw_scinames)}/{Nscinames} ({round(len(raw_scinames)/Nscinames*100,2)}%) scientific names remaining to process', verbose=verbose)
                    concat = True

        if store:

            if overwrite:
                print(indent + f'WARNING | {outputfile} will be overwritten (`overwrite`={overwrite})')
            else:
                left = outputfile.split('.')[0]
                right = outputfile.split('.')[1]
                outputfile = left + f'{date.today().strftime("_%Y%m%d")}.' + right
                printv(indent + f'INFO | WoRMS match filter will be stored in {outputfile} (`overwrite`={overwrite})', verbose=verbose)


    # Pre-process scientific names for WoRMS queries

    printv(indent + f'-- Preprocessing of scientific names --', verbose=verbose)

    raw2worms_scinames = []
    for idx,sci in enumerate(raw_scinames):

        preprocessing = format_scinamesForWoRMS(sci, identification_level=identification_level, min_length=min_length, doublecheck=doublecheck)

        if len(preprocessing) == 0:
            raw2worms_scinames += [[sci,pd.NA]]
        else:
            raw2worms_scinames += [[sci,proc] for proc in preprocessing]

    raw2worms_scinames = pd.DataFrame(raw2worms_scinames,columns=['rawsciname','wormssciname'])
    unique_wormsscinames = raw2worms_scinames.loc[~pd.isnull(raw2worms_scinames['wormssciname']),'wormssciname'].unique().tolist()
    Nwormsscinames = len(unique_wormsscinames)

    if Nwormsscinames == 0:

        wormsmatch = raw2worms_scinames.copy()
        wormsmatch = wormsmatch.rename(columns={'rawsciname':'group'})
        wormsmatch[wormscall] = pd.NA
        wormsmatch = wormsmatch[colnames]
        processed = True

    # Query WoRMS

    if not processed:

        fullwormsmatch = []

        if parallel:
            tempfile = os.path.join(outputpath,f'wormsmatch{version}.temp')
        else:
            tempfile = os.path.join(outputpath,'wormsmatch.temp')

        if resume:

            ## If files with a `temp` extension exist and `resume` is True, use them

            previous_Nwormsscinames = Nwormsscinames
            resume_files = []

            temp_files = sorted(glob.glob(os.path.join(outputpath,f'*.temp')), key=os.path.getmtime, reverse=True)
            if os.path.isfile(tempfile):
                del temp_files[temp_files.index(tempfile)]
                temp_files.insert(0,tempfile)

            for filename in temp_files:

                tempdf = pd.read_csv(filename,sep='\t')

                if len(set(wormscall)-set(tempdf.columns)) == 0:

                    keep = list(set(unique_wormsscinames).intersection(tempdf['wormssciname'].astype('string').tolist()))
                    tempdf = tempdf.set_index('wormssciname').loc[keep,:].reset_index()

                    fullwormsmatch += tempdf[['wormssciname'] + wormscall].values.tolist()
                    unique_wormsscinames = list(set(unique_wormsscinames) - set(keep))

                    if (previous_Nwormsscinames-len(unique_wormsscinames) != 0):
                        resume_files.append(filename.split('/')[-1])
                        previous_Nwormsscinames = len(unique_wormsscinames)

            if len(resume_files) != 0:

                # Notify the user

                if len(resume_files) == 1:
                    string_files = resume_files[0]
                else:
                    string_files = ', '.join(resume_files[:-1]) + f' and {resume_files[-1]}'
                printv(indent + f'INFO | {string_files} will be used (`resume`={resume})', verbose=verbose)
                printv(indent + f'UPDATE | {len(unique_wormsscinames)}/{Nwormsscinames} ({round(len(unique_wormsscinames)/Nwormsscinames*100,2)}%) scientific names remaining to process (`resume`={resume})', verbose=verbose)

        Nwormsscinames = len(unique_wormsscinames)

        printv(indent + f'-- WoRMS API call --', verbose=verbose)
        printv(indent + f'{Nwormsscinames} WoRMS-formatted scientific names to process', verbose=verbose)

        ## Break down the query into queries of 50 raw scientific names (WoRMS limit)

        nbatch = math.ceil(Nwormsscinames/50)

        if verbose:
            process = tqdm(range(nbatch), desc=indent + 'Progress')
        else:
            process = range(nbatch)

        for batch in process:

            start = batch*50
            if batch == (nbatch-1):
                end = Nwormsscinames
            else:
                end = start + 50

            ## WoRMS API call

#            fullwormsmatch += match50_WoRMSBySciname(unique_wormsscinames[start:end], wormscall=wormscall, species_only=species_only)
            blo = match50_WoRMSBySciname(unique_wormsscinames[start:end], wormscall=wormscall, species_only=species_only) #DEBUG
            #bli = pd.DataFrame(blo, columns=['group']+wormscall) # DEBUG
            #print(bli.loc[bli['group'].isin(['Eriospermum capense', 'Antherotoma naudinii', 'Buteogallus anthracinus gundlachii', 'Naasarius olomea', 'Radula kegelii','Protographium philolaus','Xystonella longicauda']),['group','scientificname','genus']])
            fullwormsmatch += blo #DEBUG

            ## Save progress

            if (((batch+1)%200) == 0) or (end == Nwormsscinames):
                store_fullwormsmatch = pd.DataFrame(fullwormsmatch, columns=['wormssciname']+wormscall)
                store_fullwormsmatch = astype_Int64(store_fullwormsmatch, wormscall, isrecognizedmatch=True)
                writedataframe.to_txt(store_fullwormsmatch, tempfile, init=True, verbose=False, indent=indent)

        fullwormsmatch = pd.DataFrame(fullwormsmatch, columns=['wormssciname']+wormscall)
        fullwormsmatch = pd.merge(raw2worms_scinames, fullwormsmatch, how='left', on=['wormssciname'])

        # Match WoRMS

        printv(indent + f'-- Construction of the WoRMS match filter --', verbose=verbose)

        column = ('kingdom' if ('kingdom' in wormscall) else 'rank')

        isduplicated = fullwormsmatch.duplicated(subset=['rawsciname'], keep=False)

        ## Unduplicated raw scientific name
        ## i.e associated with a unique WoRMS-formatted string

        wormsmatch = fullwormsmatch[~isduplicated]

        ## Duplicated raw scientific name
        ## i.e associated with more than one WoRMS-formatted string

        duplicated_wormsmatch = fullwormsmatch[isduplicated]

        isduplicated_match = (~pd.isnull(duplicated_wormsmatch[column])) # duplicated match
        isduplicated_NaN = duplicated_wormsmatch[(~isduplicated_match)].duplicated(subset=['rawsciname'],keep=False) # duplicated NaN

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

                wormsmatch = pd.concat([wormsmatch,duplicated_wormsmatch.loc[~isduplicated,wormsmatch.columns]],axis=0)

            ## Duplicated raw scientific name

            duplicated_wormsmatch = duplicated_wormsmatch[isduplicated]

            isduplicated_match = (~pd.isnull(duplicated_wormsmatch[column]))

        if sum(isduplicated_match)>0:

            ## For a given scientific name, several associated pre-processed strings match
            ## Keep only the first one (i.e the one with the best identification level, by construction)

            duplicated_wormsmatch = duplicated_wormsmatch[isduplicated_match]
            isabovespecies = (duplicated_wormsmatch['match_type'] == 'match_abovespecies')
            duplicated_wormsmatch = pd.concat([duplicated_wormsmatch[~isabovespecies], duplicated_wormsmatch[isabovespecies]],axis=0).reset_index(drop=True) #NEW VÉRIFIER
            deduplicate_wormsmatch = duplicated_wormsmatch[['rawsciname','wormssciname']].set_index(['rawsciname','wormssciname']).index.unique().to_frame().drop_duplicates(subset=['rawsciname'],keep='first').values
            deduplicate_wormsmatch = pd.DataFrame(deduplicate_wormsmatch,columns=['rawsciname','wormssciname'])
            deduplicated_wormsmatch = pd.merge(duplicated_wormsmatch, deduplicate_wormsmatch, on=['rawsciname','wormssciname'], how='inner')

            wormsmatch = pd.concat([wormsmatch,deduplicated_wormsmatch[wormsmatch.columns]],axis=0)

        wormsmatch = wormsmatch.rename(columns={'rawsciname':'group'})
        wormsmatch = wormsmatch[colnames].reset_index(drop=True)

    wormsmatch = astype_Int64(wormsmatch, wormscall, isrecognizedmatch=True)
    wormsmatch.loc[pd.isnull(wormsmatch['match_type']),'match_type'] = 'nomatch'

    if concat:
        wormsmatch = pd.concat([previous_wormsmatch[wormsmatch.columns],wormsmatch],axis=0).reset_index(drop=True)

    # Store

    if store:
        printv(indent + f'-- Storing in {outputfile} --', verbose=verbose)
        writedataframe.to_txt(wormsmatch, outputfile, init=True, verbose=False, indent=indent)

    # Clean

    os.remove(tempfile)

    if return_filename:
        return outputfile, wormsmatch
    else:
        return wormsmatch


### Match WoRMS by valid aphiaIDs to get accepted scientific names ###


def connect_getAphiaRecordsByIDs(aphiaID, max_attempt=10, pause_duration=5):

    global cl

    attempt = 0
    while attempt < max_attempt:
        try:
            return cl.service.getAphiaRecordsByIDs(aphiaID)
        except (http.client.RemoteDisconnected, TimeoutError) as err:
            attempt += 1
            if attempt < max_attempt:
                time.sleep(pause_duration)
                cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
            else:
                raise Exception(f'`createwormsfilters.py` | {type(err).__name__}: {err}')

def match50_WoRMSByAcceptedSciname(valid_aphiaID, wormscall, species_only=True):

    if isinstance(valid_aphiaID, int):
        valid_aphiaID = [valid_aphiaID]

    aphiaID['aphiaids'] = valid_aphiaID
    worms_results = connect_getAphiaRecordsByIDs(aphiaID)

    classification = []
    match_idx = wormscall.index('match_type')

    quarantined = False
    if len(worms_results) != len(valid_aphiaID):
        quarantined = True
        success = []

    for idx,taxon in enumerate(worms_results):

        taxon = dict(items(taxon))
        taxon = remove_worms_escapecharacters(taxon)
        taxon = process_rank(taxon, isrecognizedmatch=False)

        if pd.isnull(taxon['scientificname']) and species_only:

            # The taxon is identified at a rank higher than species

            values = [taxon['AphiaID']] + [pd.NA]*len(wormscall)
            values[match_idx+1] = taxon['match_type']
            classification.append(values)

        else:

            classification.append([taxon['AphiaID']] + list(itemgetter(*wormscall)(taxon)))

        if quarantined:
            success.append(taxon['AphiaID'])

    if quarantined:

        if len(set(success) - set(valid_aphiaID)) != 0:
            raise Exception(f'`createwormsfilters.py` | {list(set(success) - set(valid_aphiaID))} not in `valid_aphiaID`: mismatch between requested and returned valid_AphiaIDs from WoRMS')

        failure = list(set(valid_aphiaID) - set(success))

        for taxon in failure:
            values = [taxon] + [pd.NA]*len(wormscall)
            values[match_idx+1] = 'match_quarantine'
            classification.append(values)

    return classification


def match_WoRMSByAcceptedSciname(valid_aphiaID, wormscall=WORMSCALL, species_only=True, resume=True, resume_mode='soft', store=True, overwrite=False, return_filename=False, outputpath='./', outputfile='worms_acceptedfilter.txt', verbose=True, indent='', parallel=False, version=None):

    # Parameters

    concat = False
    colnames = ['group'] + wormscall
    outputfile = os.path.join(outputpath,outputfile)

    if parallel:

        store = True
        verbose = False
        return_filename = True

        if version is not None:

            outputfile = outputfile.split('.')[0]+f'{version}.txt'

        else:

            # Search for an unused file name

            isfile = True
            version = random.randint(0,1000)
            output = outputfile.split('.')[0]

            while isfile:

                outputfile = output+f'{version}.txt'

                if not os.path.isfile(outputfile):
                    isfile = False
                else:
                    version = random.randint(0,1000)

    NaphiaID = len(valid_aphiaID)

    printv(indent + f'** WoRMS filter (accepted marine taxa) | {NaphiaID} unique WoRMS identifiers',verbose=verbose)

    if NaphiaID == 0:

        # No WoRMS identifiers to process

        if return_filename:
            return outputfile, pd.DataFrame([],columns=colnames)
        else:
            return pd.DataFrame([],columns=colnames)

    if os.path.isfile(outputfile):

        if resume:

            printv(indent + f'INFO | {outputfile} already exists and will be used', verbose=verbose)

            valid_aphiaID, previous_wormsaccepted = resume_matchWoRMS(valid_aphiaID, colnames, outputfile, isrecognizedmatch=False, resume_mode=resume_mode)

            if previous_wormsaccepted is None:
                printv(indent + f'INFO | {outputfile.split("/")[-1]} lacks required columns or shared WoRMS identifiers. Run from scratch.', verbose=verbose)

            else:

                previous_wormsaccepted = astype_Int64(previous_wormsaccepted, wormscall, isrecognizedmatch=False)

                if len(valid_aphiaID) == 0:
                    printv(indent + 'UPDATE | all unaccepted taxa processed', verbose=verbose)
                    if return_filename:
                        return outputfile, previous_wormsaccepted
                    else:
                        return previous_wormsaccepted
                else:
                    printv(indent + f'UPDATE | {len(valid_aphiaID)}/{NaphiaID} ({round(len(valid_aphiaID)/NaphiaID*100,2)}%) WoRMS identifiers remaining to process',verbose=verbose)
                    concat = True
                    NaphiaID = len(valid_aphiaID)
                    previous_outputfile = outputfile

        if store:

            if overwrite:
                print(indent + f'WARNING | {outputfile} will be overwritten (`overwrite`={overwrite})')
            else:
                left = outputfile.split('.')[0]
                right = outputfile.split('.')[1]
                outputfile = left + f'{date.today().strftime("_%Y%m%d")}.' + right
                printv(indent + f'INFO | WoRMS match filter will be stored in {outputfile} (`overwrite`={overwrite})', verbose=verbose)

    wormsaccepted = []

    if resume and parallel:

        ## If accepted filter files from a previous run exist and `resume` is True, use them

        resume_files = []
        previous_NaphiaID = NaphiaID

        stored = glob.glob(outputfile.split(str(version))[0] + '*')
        if concat:
            # the file has already been accounted for above
            del stored[stored.index(previous_outputfile)]
        stored = sorted([filename for filename in stored if re.search(r'[0-9]+',filename)], key=os.path.getmtime, reverse=True)

        for filename in stored:

            tempdf = pd.read_csv(filename,sep='\t')
            tempdf = astype_Int64(tempdf, wormscall, isrecognizedmatch=False)

            if len(set(colnames)-set(tempdf.columns)) == 0:

                keep = list(set(valid_aphiaID).intersection(tempdf['group'].tolist()))
                tempdf = tempdf.set_index('group').loc[keep,:].reset_index()

                wormsaccepted += tempdf[colnames].values.tolist()
                valid_aphiaID = list(set(valid_aphiaID) - set(keep))

                if (previous_NaphiaID-len(valid_aphiaID) != 0):
                    resume_files.append(filename.split('/')[-1])
                    previous_NaphiaID = len(valid_aphiaID)

        if len(resume_files) != 0:

            # Notify the user

            if len(resume_files) == 1:
                string_files = resume_files[0]
            else:
                string_files = ', '.join(resume_files[:-1]) + f' and {resume_files[-1]}'
            printv(indent + f'INFO | {string_files} will be used (`resume`={resume})', verbose=verbose)
            printv(indent + f'UPDATE | {len(valid_aphiaID)}/{NaphiaID} ({round(len(valid_aphiaID)/NaphiaID*100,2)}%) scientific names remaining to process (`resume`={resume})', verbose=verbose)

    NaphiaID = len(valid_aphiaID)

    printv(indent + f'-- WoRMS API call --', verbose=verbose)
    printv(indent + f'{NaphiaID} WoRMS identifiers to retrieve', verbose=verbose)

    nbatch = math.ceil(NaphiaID/50)

    if verbose:
        process = tqdm(range(nbatch), desc = indent + 'Progress')
    else:
        process = range(nbatch)

    for batch in process:

        start = batch*50
        if batch == (nbatch-1):
            end = NaphiaID
        else:
            end = start + 50

        wormsaccepted += match50_WoRMSByAcceptedSciname(valid_aphiaID[start:end], wormscall=wormscall, species_only=species_only)

        ## Save progress

        if store and (((batch+1)%200) == 0):
            store_wormsaccepted = pd.DataFrame(wormsaccepted,columns=colnames)
            store_wormsaccepted = astype_Int64(store_wormsaccepted, wormscall, isrecognizedmatch=False)
            writedataframe.to_txt(store_wormsaccepted, outputfile, init=True, verbose=False, indent=indent)

    wormsaccepted = pd.DataFrame(wormsaccepted,columns=colnames)
    wormsaccepted = astype_Int64(wormsaccepted, wormscall, isrecognizedmatch=False)

    if concat:
        wormsaccepted = pd.concat([previous_wormsaccepted[wormsaccepted.columns],wormsaccepted],axis=0).reset_index(drop=True)

    if store:
        printv(f'-- Storing in {outputfile} --', verbose=verbose)
        writedataframe.to_txt(wormsaccepted, outputfile, init=True, verbose=False, indent=indent)

    if return_filename:
        return outputfile, wormsaccepted
    else:
        return wormsaccepted


### Parallel version of WoRMS match functions ###


def retry_WoRMSmatch(func, future, tasks, executor, **params):

    # Retry a task that failed

    ## Get the associated data for the task
    data = tasks[future]['data']
    id = tasks[future]['id']
    count = tasks[future]['count']

    ## Submit the task again
    retry = executor.submit(func,data,version=id[1],**params)

    ## Store to track the retries
    tasks[retry] = {}
    tasks[retry]['id'] = id
    tasks[retry]['data'] = data
    tasks[retry]['count'] = count + 1

    return tasks[retry]['id'], tasks[retry]['count']


def parallel_WoRMSmatch(wormsfunc, data, wormscall, cpu, max_attempt=3, indent='', outputfile='', outputpath='./', resume_parallel=True, resume_mode='soft', store_parallel=True, overwrite_parallel=False, **params):

    # Parameters

    params['wormscall'] = wormscall
    params['outputpath'] = outputpath
    params['outputfile'] = outputfile
    params['resume'] = True
    params['resume_mode'] = resume_mode
    params['indent'] = indent

    if len(outputfile) == 0:
        outputfile = f'{wormsfunc}_results.txt'
    outputfile = os.path.join(outputpath,outputfile)

    concat = False
    preprocess = False
    isrecognizedmatch = (wormsfunc.__name__ == 'match_WoRMSBySciname')
    colnames = ['group'] + wormscall

    Ndata = len(data)

    if os.path.isfile(outputfile):

            if resume_parallel:

                print(indent + f'INFO | {outputfile} already exists and will be used (`resume_parallel`={resume_parallel})')

                if isrecognizedmatch:
                    data = preprocessquotationmark.apply(data)
                    preprocess = True

                data, previous_wormsmatch = resume_matchWoRMS(data, colnames, outputfile, isrecognizedmatch=isrecognizedmatch, resume_mode=resume_mode)

                if previous_wormsmatch is None:
                    print(indent + f'INFO | {previous_filename} lacks required columns or shared values. Run from scratch.')

                else:
                    print(indent + f'UPDATE | {len(data)}/{Ndata} ({round(len(data)/Ndata*100,2)}%) lines remaining to process (`resume_parallel`={resume_parallel})')
                    concat = True
                    Ndata = len(data)
                    previous_wormsmatch = astype_Int64(previous_wormsmatch, wormscall, isrecognizedmatch=isrecognizedmatch)

            else:
                print(indent + f"INFO | {outputfile} already exists but won't be used (`resume_parallel`={resume_parallel})")

            if store_parallel:
                if overwrite_parallel:
                    print(indent + f'WARNING | {outputfile} will be overwritten')
                else:
                    previous_filename = outputfile
                    left = outputfile.split('.')[0]
                    right = outputfile.split('.')[1]
                    outputfile = left + f'{date.today().strftime("_%Y%m%d")}.' + right
                    params['outputfile'] = outputfile.split('/')[-1]


    results = []
    tempfiles = []

    if Ndata != 0:

        # Distribute the scientific names for processing

        index = list(range(Ndata))

        length = math.ceil(Ndata/cpu)
        cpu_split = [subset for subset in zip(index[::length],index[length::length]+[len(index)])]
        cpu = min(cpu,len(cpu_split))

        ## Notify the user

        print_slices = [f'slice n°{i+1}: {slice},' for i,slice in enumerate(cpu_split)]
        Nlines = math.ceil(len(print_slices)/3)
        for line in range(Nlines):
            string = indent + ' '.join(print_slices[line*3:line*3+3])
            print(string[:-1])

        # Create a process pool

        completed = 0
        failure = []

        with ProcessPoolExecutor(max_workers=cpu) as executor:

            start = time.time()

            # Submit the tasks into the pool

            tasks = {executor.submit(wormsfunc,data[i:j],version=j,**params):{'id':(i,j),'data':data[i:j],'count':1} for i,j in cpu_split}

            # Retry until all tasks have been completed,
            # or the maximum number of attempts has been reached for failed tasks

            while completed<cpu:

               for future in as_completed(tasks):

                   if future.exception():
                       #future.result() #DEBUG
                       id, count = retry_WoRMSmatch(wormsfunc, future, tasks, executor, **params)

                       if count>max_attempt:

                           cpu -= 1

                           print(indent + f'FAILURE | More than {max_attempt} attempts, slice {id} will not be processed. Please try again later | TIME: {round(time.time()-start)}s')
                           print(indent + f'Exception: {future.exception()}')

                       else:

                           print(indent + f'FAILURE | Retrying slice {id} (attempt n°{count}) | TIME: {round(time.time()-start)}s')
                           print(indent + f'Exception: {future.exception()}')

                   else:

                       res = future.result()
                       tempfiles.append(res[0])
                       results.append(res[1][colnames])
                       completed += 1

                       print(indent + f'SUCCESS | slice {tasks[future]["id"]} completed ({tasks[future]["count"]} attempt(s)) | TIME: {round(time.time()-start)}s')

                   tasks.pop(future)

        if len(results) != 0:
            wormsmatch = pd.concat(results,axis=0).reset_index(drop=True)
        else:
            wormsmatch = pd.DataFrame([],columns=colnames)

    else:
        wormsmatch = pd.DataFrame([],columns=colnames)

    # Previous matches

    if concat:
        if len(wormsmatch) != 0:
            wormsmatch = pd.concat([previous_wormsmatch[colnames],wormsmatch[colnames]],axis=0).reset_index(drop=True)
        else:
            wormsmatch = previous_wormsmatch[colnames].copy()

    # Store

    if store_parallel:
        writedataframe.to_txt(wormsmatch, outputfile, init=True, verbose=True, indent=indent)

    # Clean

    for file in tempfiles:
        os.remove(file)

    # Return

    return outputfile, wormsmatch


def parallel_match_WoRMSBySciname(raw_scinames, cpu, wormscall=WORMSCALL, identification_level='species', min_length=3, doublecheck=True, max_attempt=3, indent='', outputpath='./', outputfile='worms_matchfilter.txt', resume=True, resume_mode='soft', overwrite=False, store_parallel=True, overwrite_parallel=False, resume_parallel=True, **ignored):

    params_match_WoRMSBySciname = {
                                   'wormscall':wormscall,
                                   'identification_level':identification_level,
                                   'min_length':min_length,
                                   'doublecheck':doublecheck,
                                   'resume':resume,
                                   'resume_mode':resume_mode,
                                   'store':True,
                                   'overwrite':overwrite,
                                   'verbose':False,
                                   'parallel':True,
                                   'return_filename':True,
                                   'indent':indent
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

    if len(outputfile) == 0:
        outputfile = 'worms_matchfilter.txt'

    outputfile, wormsmatch = parallel_WoRMSmatch(match_WoRMSBySciname, raw_scinames, **params_parallel, **params_match_WoRMSBySciname)

    return outputfile, wormsmatch


def parallel_match_WoRMSByAcceptedSciname(valid_aphiaID, cpu, wormscall=WORMSCALL, species_only=True, max_attempt=3, indent='', outputpath='./', outputfile='worms_acceptedfilter.txt', resume=True, resume_mode='soft', overwrite=False, store_parallel=True, overwrite_parallel=False, resume_parallel=True, **ignored):

    params_match_WoRMSByAcceptedSciname = {
                                           'wormscall':wormscall,
                                           'species_only':species_only,
                                           'resume':resume,
                                           'resume_mode':resume_mode,
                                           'store':True,
                                           'overwrite':overwrite,
                                           'verbose':False,
                                           'parallel':True,
                                           'return_filename':True,
                                           'indent':indent
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

    if len(outputfile) == 0:
        outputfile = 'worms_acceptedfilter.txt'

    outputfile, wormsmatch = parallel_WoRMSmatch(match_WoRMSByAcceptedSciname, valid_aphiaID, **params_parallel, **params_match_WoRMSByAcceptedSciname)

    return outputfile, wormsmatch


### Retrieve classifications for taxa that partially failed to match WoRMS backbone ###


def process_partialmatch(wormsfilter, wormsfuncname, parallel, wormscall=WORMSCALL, indent='', **params_dict):

    if (wormsfuncname != 'recognized') and (wormsfuncname != 'accepted'):
        raise ValueError(f"`createwormsfilters.py` | `wormsfuncname` must be either 'recognized' or 'accepted', not '{wormsfuncname}'")

    params_parallel = {}
    params_func = {}
    if len(params_dict) != 0:
        if 'parallel_args' in params_dict.keys():
            params_parallel = params_dict['parallel_args'].copy()
        if 'func_args' in params_dict.keys():
            params_func = params_dict['func_args'].copy()

    if 'wormscall' in params_func.keys():
        wormscall = params_func['wormscall']
    else:
        params_func['wormscall'] = wormscall

    if 'indent' in params_func.keys():
        indent = params_func['indent']
    else:
        params_func['indent'] = indent

    wormsfunc = (match_WoRMSBySciname if (wormsfuncname == 'recognized') else match_WoRMSByAcceptedSciname)
    parallel_wormsfunc = (parallel_match_WoRMSBySciname if (wormsfuncname == 'recognized') else parallel_match_WoRMSByAcceptedSciname)

    # If some taxa match a non-quarantined, non-deleted WoRMS taxon
    # but have a missing value for 'kingdom' (and thus the entire classification)
    # or for 'rank' when 'kingdom' is not among the retrieved values,
    # attempt WoRMS matching again (WoRMS API bug)

    column = ('kingdom' if ('kingdom' in wormscall) else 'rank')
    doesmatch = (~pd.isnull(wormsfilter['status']))
    isquarantineddeleted = wormsfilter['status'].isin(['match_quarantine','match_deleted'])
    doeswormsmatchfailed = doesmatch & (~isquarantineddeleted) & pd.isnull(wormsfilter[column])
    doeswormsmatchfailed = doeswormsmatchfailed[doeswormsmatchfailed].index

    if len(doeswormsmatchfailed) != 0:

        params_func['store'] = False
        params_func['resume'] = False
        params_func['resume_mode'] = 'hard'
        params_parallel['store_parallel'] = False
        params_parallel['resume_parallel'] = False

        unique_rawscinames = wormsfilter.loc[doeswormsmatchfailed,'group'].tolist()
        wormsfilter.drop(index=doeswormsmatchfailed, inplace=True)

        print(indent + f'** WoRMS filter (partially recognized marine taxa) | {len(unique_rawscinames)} unique scientific names')

        if parallel and (len(unique_rawscinames) >= 1000):
            params_func['verbose'] = False
            _, retry_wormsfilter = parallel_wormsfunc(unique_rawscinames, **params_parallel, **params_func)
        else:
            params_func['verbose'] = True
            _, retry_wormsfilter = wormsfunc(unique_rawscinames, **params_func)

        wormsfilter = pd.concat([wormsfilter,retry_wormsfilter[wormsfilter.columns]], axis=0)

    return wormsfilter


### Retrieve classifications of accepted species counterparts for taxa below species rank ###


def process_subspecies(worms_acceptedfilter, parallel, wormscall=WORMSCALL, indent='', **params_dict):

    params_parallel = {}
    params_func = {}
    if len(params_dict) != 0:
        if 'parallel_args' in params_dict.keys():
            params_parallel = params_dict['parallel_args'].copy()
        if 'func_args' in params_dict.keys():
            params_func = params_dict['func_args'].copy()

    if 'wormscall' in params_func.keys():
        wormscall = params_func['wormscall']
    else:
        params_func['wormscall'] = wormscall

    if 'indent' in params_func.keys():
        indent = params_func['indent']
    else:
        params_func['indent'] = indent

    # Find taxa identified at a rank lower than species

    issubspecies = (worms_acceptedfilter['status'].isin(['subspecies','process'])) & (~pd.isnull(worms_acceptedfilter['valid_AphiaID']))

    if any(issubspecies):

        subspecies = worms_acceptedfilter.loc[issubspecies,['valid_AphiaID']].rename(columns={'valid_AphiaID':'group'})
        parent_aphiaID = subspecies['group'].unique().tolist()

        # Retrieve the classification of parent taxa
        # (which may still be identified below species rank, e.g. forma -> subspecies)

        print(indent + f'** WoRMS filter (subspecies) | {len(parent_aphiaID)} taxa either below species rank or unaccepted')

        if parallel and (len(parent_aphiaID) >= 1000):
            params_func['verbose'] = False
            params_parallel['store_parallel'] = False
            params_parallel['cpu'] = 2
            _, parent_classification = parallel_match_WoRMSByAcceptedSciname(parent_aphiaID, **params_func, **params_parallel)
        else:
            params_func['verbose'] = True
            params_func['store'] = False
            parent_classification = match_WoRMSByAcceptedSciname(parent_aphiaID, **params_func)

        subspecies = subspecies.reset_index().merge(parent_classification,how='inner',on='group')
        subspecies = subspecies.set_index('index').rename_axis(None, axis=0)

        # Ensure consistency of identifiers
        # In most cases, equality is expected,
        # however, circularity between identifiers may occur
        #   e.g. for “Parastenhelia spinosa”:
        #   aphiaID=116446 to valid_AphiaID=116896 (subspecies)
        #   to parentNameUsageID=116446 (alternative representation) to valid_AphiaID=116896 (subspecies) etc.
        # or the parent taxon to which WoRMS redirects may not be the accepted taxon
        #   e.g. for "Cystoseira montagnei var. tenuior":
        #   aphiaID=valid_aphiaID=1063030 (subspecies)
        #   to parentNameUsageID=145525 "Cystoseira montagnei" (superseded combination)
        #   to valid_aphiaID=1731896 "Gongolaria montagnei" (accepted, species)

        isaphiaID = (~pd.isnull(subspecies['valid_AphiaID']))
        isunaccepted = (subspecies['status'] != 'accepted') & (subspecies['valid_AphiaID'] != subspecies['group'])
        index = subspecies.index
        iscircularity = (subspecies['valid_AphiaID'] == worms_acceptedfilter.loc[index,'cyclic_valid_AphiaID'])

        cyclic_status = subspecies['status'].values
        cyclic_valid_AphiaID = subspecies['group'].values

        # Perform additional processing for unaccepted taxa

        condition = isaphiaID & isunaccepted & (~iscircularity)
        subspecies.loc[condition,'status'] = 'process'

        # Resolve circularity between identifiers

        condition = isaphiaID & isunaccepted & iscircularity
        islowerthanspecies = (subspecies['status'] == 'subspecies')

        donotchange = (condition & islowerthanspecies)
        index = subspecies[donotchange].index
        columns = list(set(subspecies.columns) - set(['group','valid_AphiaID']))
        subspecies.loc[index,columns] = worms_acceptedfilter.loc[index,columns].values
        subspecies.loc[index,'status'] = worms_acceptedfilter.loc[index,'cyclic_status']
        subspecies.loc[donotchange & (subspecies['status'] == 'subspecies'), 'status'] = 'cycle'

        finalchange = (condition & (~islowerthanspecies))
        subspecies.loc[finalchange,'valid_AphiaID'] = subspecies.loc[finalchange,'group'].values

        return subspecies, cyclic_status, cyclic_valid_AphiaID

    else:

        return None, None, None


### Create WoRMS filters ###


@export
def create_WoRMSrecognizedfilter(unique_rawscinames, wormscall=WORMSCALL, identification_level='species', min_length=3, doublecheck=True, store=True, outputpath='./', outputfile='worms_matchfilter.txt', overwrite=False, resume=True, resume_mode='soft', parallel=True, cpu=2, max_attempt=3, store_parallel=True, overwrite_parallel=False, resume_parallel=True, indent=''):

    if parallel:

        if (store != store_parallel):
            raise ValueError(f'`createwormsfilters.py` | parallel={parallel} and store={store} but store_parallel={store_parallel}')

        if (overwrite != overwrite_parallel):
            raise ValueError(f'`createwormsfilters.py` | parallel={parallel} and overwrite={overwrite} but overwrite_parallel={overwrite_parallel}')

    params_func = {
                   'wormscall': wormscall,
                   'identification_level': identification_level,
                   'min_length': min_length,
                   'doublecheck': doublecheck,
                   'return_filename': True,
                   'resume': resume,
                   'resume_mode': resume_mode,
                   'indent': indent
                  }

    params_store = {
                    'store': store,
                    'outputpath': outputpath,
                    'outputfile': outputfile,
                    'overwrite': overwrite
                  }

    params_parallel = {
                       'cpu': 2,
                       'max_attempt': max_attempt,
                       'resume_parallel': resume_parallel,
                       'store_parallel': store_parallel,
                       'overwrite_parallel': overwrite_parallel
                      }

    params_func.update(params_store)

    # Retrieve the classification for WoRMS-recognized taxa

    if parallel and (len(unique_rawscinames) >= 1000):
        print(indent + f'** WoRMS filter (recognized marine taxa) | {len(unique_rawscinames)} unique scientific names')
        params_func['verbose'] = False
        filename, worms_matchfilter = parallel_match_WoRMSBySciname(unique_rawscinames, **params_parallel, **params_func)
    else:
        params_func['verbose'] = True
        filename, worms_matchfilter = match_WoRMSBySciname(unique_rawscinames, **params_func)

    params_func['outputfile'] = filename
    worms_matchfilter = standardizenan.apply(worms_matchfilter)

    # Retrieve the classification for taxa that partially failed to match WoRMS backbone

    params_dict = {}
    params_dict['parallel_args'] = params_parallel
    params_dict['func_args'] = params_func

    worms_matchfilter = process_partialmatch(worms_matchfilter, 'recognized', parallel, **params_dict)

    # Standardize missing values

    worms_matchfilter = standardizenan.apply(worms_matchfilter)

    # Convert ID fields to integer type

    worms_matchfilter = astype_Int64(worms_matchfilter, wormscall, isrecognizedmatch=True)

    # Store WoRMS-accepted filter

    if store:
        writedataframe.to_txt(worms_matchfilter, params_func['outputfile'], init=True, verbose=True, indent=indent)

    return worms_matchfilter

@export
def create_WoRMSacceptedfilter(unaccepted_aphiaID, wormscall=WORMSCALL, species_only=True, store=True, outputpath='./', outputfile='worms_acceptedfilter.txt', overwrite=False, resume=True, resume_mode='soft', parallel=True, cpu=2, max_attempt=3, store_parallel=True, overwrite_parallel=False, resume_parallel=True, indent=''):

    if parallel:

        if (store != store_parallel):
            raise ValueError(f'`createwormsfilters.py` | parallel={parallel} and store={store} but store_parallel={store_parallel}')

        if (overwrite != overwrite_parallel):
            raise ValueError(f'`createwormsfilters.py` | parallel={parallel} and overwrite={overwrite} but overwrite_parallel={overwrite_parallel}')

    params_func = {
                   'wormscall':wormscall,
                   'species_only':species_only,
                   'return_filename':True,
                   'resume':resume,
                   'resume_mode':resume_mode,
                   'indent':indent
                  }

    params_store = {
                   'store':store,
                   'outputpath':outputpath,
                   'outputfile':outputfile,
                   'overwrite':overwrite
                  }

    params_parallel = {
                       'cpu':2,
                       'max_attempt':max_attempt,
                       'resume_parallel':resume_parallel,
                       'store_parallel':store_parallel,
                       'overwrite_parallel':overwrite_parallel
                      }

    params_func.update(params_store)

    # Retrieve the classification for the scientifically accepted counterpart of each unaccepted taxa

    if len(unaccepted_aphiaID) == 0:
        print(indent + f'** WoRMS filter (accepted marine taxa) | {len(unaccepted_aphiaID)} unaccepted taxa')
        return None

    if parallel and (len(unaccepted_aphiaID) >= 1000):
        print(indent + f'** WoRMS filter (accepted marine taxa) | {len(unaccepted_aphiaID)} unaccepted taxa')
        params_func['verbose'] = False
        filename, worms_acceptedfilter = parallel_match_WoRMSByAcceptedSciname(unaccepted_aphiaID, **params_parallel, **params_func)
    else:
        params_func['verbose'] = True
        filename, worms_acceptedfilter = match_WoRMSByAcceptedSciname(unaccepted_aphiaID, **params_func)

    params_func['outputfile'] = filename

    # Process taxa identified at a rank lower than species and any remaining unaccepted taxa

    params_func['store'] = False
    params_func['return_filename'] = False

    params_dict = {}
    params_dict['parallel_args'] = params_parallel
    params_dict['func_args'] = params_func

    ## Identify and replace any remaining unaccepted taxa with their accepted counterparts

    isunaccepted = (worms_acceptedfilter['status'] != 'accepted') & (~pd.isnull(worms_acceptedfilter['valid_AphiaID'])) & (worms_acceptedfilter['valid_AphiaID'] != worms_acceptedfilter['group'])
    worms_acceptedfilter.loc[isunaccepted,'status'] = 'process'

    ## Resolve cyclic dependencies between identifiers
    ## when retrieving species classification for taxa below species rank

    worms_acceptedfilter['cyclic_valid_AphiaID'] = worms_acceptedfilter['valid_AphiaID'].values
    worms_acceptedfilter['cyclic_status'] = worms_acceptedfilter['status'].values

    subspecies, cyclic_status, cyclic_valid_AphiaID = process_subspecies(worms_acceptedfilter, parallel, **params_dict)

    while subspecies is not None:

        ## Replace taxa identified below species rank,
        ## with their accepted parent classification in the WoRMS-accepted filter

        index, columns = subspecies.index.tolist(), list(set(subspecies.columns) - set(['group']))
        worms_acceptedfilter.loc[index, columns] = subspecies.loc[index, columns]
        worms_acceptedfilter.loc[index,'cyclic_status'], worms_acceptedfilter.loc[index,'cyclic_valid_AphiaID'] = cyclic_status, cyclic_valid_AphiaID

        subspecies, cyclic_status, cyclic_valid_AphiaID = process_subspecies(worms_acceptedfilter, parallel, **params_dict)

    worms_acceptedfilter = worms_acceptedfilter.drop(columns=['cyclic_status','cyclic_valid_AphiaID'])
    worms_acceptedfilter = standardizenan.apply(worms_acceptedfilter)

    # Retrieve the classification for taxa that partially failed to match WoRMS backbone

    worms_acceptedfilter = process_partialmatch(worms_acceptedfilter, 'accepted', parallel, **params_dict)

    # Standardize missing values

    worms_acceptedfilter = standardizenan.apply(worms_acceptedfilter)

    # Convert ID fields to integer type

    worms_acceptedfilter = astype_Int64(worms_acceptedfilter, wormscall, isrecognizedmatch=False)

    # Store WoRMS-accepted filter

    if store:
        writedataframe.to_txt(worms_acceptedfilter, params_func['outputfile'], init=True, verbose=True, indent=indent)

    return worms_acceptedfilter

@export
def create_WoRMSfilter(filepath, colname, wormscall=WORMSCALL, identification_level='species', min_length=3, doublecheck=True, store=True, outputpath='./', overwrite=False, resume=True, resume_mode='soft', parallel=True, max_attempt=3, store_parallel=True, overwrite_parallel=False, resume_parallel='soft', indent=''):

    # Parameters

    ## Global variables

    mandatory_wormskeys = ['scientificname','match_type','status','valid_AphiaID','rank']

    missing_keys = set(mandatory_wormskeys) - set(wormscall)
    if len(missing_keys) != 0:
        raise Exception(f'`createwormsfilters.py` | {missing_keys} WoRMS keys are missing in `wormscall`')

    ## Arguments

    cpu = 1
    if parallel:

        # To avoid compromising WoRMS performance to the detriment of other users, use a maximum of 2 CPUs
        # Inform WoRMS if necessary

        cpu = 2
        print(indent + f'INFO | {cpu} CPUs will be used')

        if (store != store_parallel):
            raise ValueError(f'`createwormsfilters.py` | parallel={parallel} and store={store} but store_parallel={store_parallel}')

        if (overwrite != overwrite_parallel):
            raise ValueError(f'`createwormsfilters.py` | parallel={parallel} and overwrite={overwrite} but overwrite_parallel={overwrite_parallel}')

    if (resume_mode != 'soft') and (resume_mode != 'hard'):
        raise ValueError(f"`createwormsfilters.py` | `resume_mode` must be 'soft' or 'hard'")

    params_store = {
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

    #unique_rawscinames = get_uniqueRawSciname(filepath, colname=colname, resume=resume, **params_store, indent=indent) #DEBUG
    unique_rawscinames = pd.read_csv('/data/smartbiodiv/eberhocoi/filters_20250323/unique_verbatimScientificName.txt',sep='\t')['raw_sciname'].tolist()

    if len(unique_rawscinames) == 0: #tester avec gbifID !!
        raise Exception(f"`createwormsfilters.py` | no scientific name found, {filepath} may be empty or '{colname}' column may not contain scientific names")

    # Get WoRMS-recognized classifications

    params_func = {
                   'wormscall':wormscall,
                   'identification_level':identification_level,
                   'min_length':min_length,
                   'doublecheck':doublecheck,
                   'resume':resume,
                   'resume_mode':resume_mode,
                   'indent':indent
                  }

    params_func.update(params_store)

    ## Match taxa with the WoRMS database and retrieve their classification if a match is found

    worms_matchfilter = create_WoRMSrecognizedfilter(unique_rawscinames, parallel=parallel, **params_parallel, **params_func)

    # Get WoRMS-accepted classifications

    params_func = {
                   'wormscall':wormscall,
                   'species_only':(identification_level == 'species'),
                   'resume':resume,
                   'resume_mode':resume_mode,
                   'indent':indent
                  }

    params_func.update(params_store)

    ## Identify unaccepted taxa classifications

    isunaccepted = (worms_matchfilter['status'] != 'accepted') & (~pd.isnull(worms_matchfilter['valid_AphiaID']))
    unaccepted_aphiaID = worms_matchfilter.loc[isunaccepted, 'valid_AphiaID'].unique().tolist()

    ## Retrieve the classification of their scientifically accepted species counterparts

    worms_acceptedfilter = create_WoRMSacceptedfilter(unaccepted_aphiaID, parallel=parallel, **params_func, **params_parallel)

    return worms_matchfilter, worms_acceptedfilter


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Create WoRMS filters')
    parser.add_argument('tabfilepath', type=str, help='path to the tab-separated file to be processed, either gzip-compressed or uncompressed')
    parser.add_argument('colname', type=str, help='column containing raw scientific names')
    parser.add_argument('--wormscall', nargs='*', type=str, help='list containing the WoRMS variables to keep', default=WORMSCALL)
    parser.add_argument('--identification_level', type=str, help="should be 'best', 'species' or 'first'", default='species')
    parser.add_argument('--min_length', type=int, help='minimum length of the words comprising the scientific name', default=3)
    parser.add_argument('--doublecheck', action=argparse.BooleanOptionalAction, help='double-check or not three-word scientific names by querying only the first two words', default=True)
    parser.add_argument('--store', action=argparse.BooleanOptionalAction, help='whether to store the filters', default=True)
    parser.add_argument('--outputpath', type=str, help='path to folder where files will be stored', default='./')
    parser.add_argument('--overwrite', action=argparse.BooleanOptionalAction, help='overwrite existing filters', default=False)
    parser.add_argument('--resume', action=argparse.BooleanOptionalAction, help='use stored filters and temporary files, if available', default=True)
    parser.add_argument('--resume_mode', type=str, help="whether to keep all previously retrieved data ('soft') or only the currently requested ones ('hard')", default='soft')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='parallelize requests (maximum 2 CPUs)', default=False)
    parser.add_argument('--max_attempt', type=int, help='maximum number of retries in case of errors when running in parallelized mode', default=3)
    parser.add_argument('--store_parallel', action=argparse.BooleanOptionalAction, help='whether to store the filters in parallelized mode', default=True)
    parser.add_argument('--overwrite_parallel', action=argparse.BooleanOptionalAction, help='overwrite existing filters in parallelized mode', default=False)
    parser.add_argument('--resume_parallel', action=argparse.BooleanOptionalAction, help='use stored filters, if available, in parallelized mode', default=True)

    args = parser.parse_args()
    params = {
              'wormscall': args.wormscall,
              'identification_level': args.identification_level,
              'min_length': args.min_length,
              'doublecheck': args.doublecheck,
              'resume' : args.resume,
              'resume_mode' : args.resume_mode,
              'store': args.store,
              'overwrite': args.overwrite,
              'outputpath': args.outputpath,
              'parallel': args.parallel,
              #'cpu': args.cpu,
              'max_attempt': args.max_attempt,
              'resume_parallel': args.resume_parallel,
              'store_parallel': args.store_parallel,
              'overwrite_parallel': args.overwrite_parallel
             }

    print()
    print('Parameters')
    print('----------')
    print(f'file: {args.tabfilepath}')
    print(f'colname: {args.colname}')
    for key, value in params.items():
        print(f'    {key}: {value}')
    print()

    print(f'* Creating the files needed for WoRMS filtering')

    start = time.time()

    _ = create_WoRMSfilter(args.tabfilepath, args.colname, **params)

    end = time.time()

    print(f'TIME : {round(end - start,0)}s')
