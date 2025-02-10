#!/usr/bin/env python3r

# External import

import argparse
import gzip
import pandas as pd
import numpy as np
import math
import yaml
import time
import os
from unidecode import unidecode
from operator import itemgetter
import itertools
import re
from datetime import datetime

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

WORMSCALL = {
             'scientificname': 'species',
             'genus': 'genus',
             'family': 'family',
             'order': 'order',
             'cls': 'class',
             'phylum': 'phylum',
             'kingdom': 'kingdom',
             'match_type':'worms_matchtype', #`match_type` must never be removed from `WORMSCALL`
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



def _update(myset,key):

    if isnan(key):
        return myset

    if not re.search(r'[a-zA-Z]',str(key)):
        return myset

    else:
        myset.add(key)
        return myset

def write_dataframe2txtfile(df, txt_filename, init=False, verbose=False):

    if verbose:
        print(f'            Storing in {txt_filename} | {len(df)} observations')

    if init:
        df.to_csv(txt_filename, mode='w', index=False, header=True, sep='\t')
    else:
        df.to_csv(txt_filename, mode='a', index=False, header=False, sep='\t')

    return True

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

            sciname = line.decode("utf8").strip('\n').split('\t')[sciname_index]
            sciname = _strip_rawSciname(sciname)

            unique_rawsciname = _update(unique_rawsciname,sciname)
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


def _format_scinamesForWoRMS_elementwise(raw_sciname, identification_level='best', min_length=3, min_words=1):

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

                else: #i.e (identification_level=='best') and (min_words==1):

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


def _format_scinamesForWoRMS(raw_scinames, identification_level='best', min_length=3, doublecheck=False): # 'best', 'species', 'first'

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

    # Delete duplicates

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


def _connect_matchAphiaRecordsByNames(wormsscinames, max_attempt=10, pause_duration=5):

    global cl

    attempt = 0
    while attempt < max_attempt:
        try:
            return cl.service.matchAphiaRecordsByNames(wormsscinames, marine_only="true")
        except (http.client.RemoteDisconnected, TimeoutError):
            attempt += 1
            if attempt < max_attempt:
                time.sleep(pause_duration)
                cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)
            else:
                raise


def _parse_matchAphiaRecordsByNames(sciname, results, keys):

    classification=[]

    if len(results)!=0:

        for taxon in results: #may be more than one candidate

            taxon = dict(items(taxon))
            classif = itemgetter(*keys)(taxon)
            classification.append([sciname] + list(classif))

    else:

        classification.append([sciname] + [pd.NA]*len(keys))

    return classification


def _match50_WoRMSBySciname(wormsscinames, wormscallK, verbose=False):

    if isinstance(wormsscinames,str):
        wormsscinames=[wormsscinames]

    scinames["scientificname"] = wormsscinames
    results=_connect_matchAphiaRecordsByNames(scinames)

    # Keep only the match information specified in `wormscallK`

    classification=[]

    for idx,res in enumerate(results):

        classification += _parse_matchAphiaRecordsByNames(wormsscinames[idx],res,wormscallK)

    return classification


def match_WoRMSBySciname(raw_scinames, wormscall=WORMSCALL, identification_level='best', min_length=3, doublecheck=False, store=False, outputpath='./', outputfile='worms_matchfilter.tsv', overwrite=False):

    wormscallK = list(wormscall.keys())
    wormscallV = list(itemgetter(*wormscallK)(wormscall))
    colnames = ['group'] + wormscallV
    outputfile = os.path.join(outputpath,outputfile)

    Nsciname = len(raw_scinames)
    init=True

    print(f'            ** WoRMS filter (recognized marine taxa) | {Nsciname} unique scientific names')

    if os.path.isfile(outputfile):

        if overwrite:

            print(f"            WARNING | {outputpath + outputfile} already exists and will be overwritten")

        else:

            print(f"            INFO | {outputpath + outputfile} already exists and will be used")

            previous_wormsmatch=pd.read_csv(outputfile, sep='\t')
            _, raw_scinames=_resume_matchWoRMS(previous_wormsmatch, raw_scinames)

            if len(raw_scinames)==0:
                return previous_wormsmatch
            else:
                print(f'            UPDATE | {len(raw_scinames)}/{Nsciname} ({np.round(len(raw_scinames)/Nsciname*100,2)}%) remaining scientific names to be processed')
                init=False

    # Pre-process scientific names for WoRMS queries

    print(f'            -- Scientific names pre-processing --')

    raw2worms_scinames=[]
    for idx,sci in enumerate(raw_scinames):

        preprocessing=_format_scinamesForWoRMS(sci, identification_level=identification_level, min_length=min_length, doublecheck=doublecheck)

        if len(preprocessing)==0:
            raw2worms_scinames+=[[sci,pd.NA]]
        else:
            raw2worms_scinames+=[[sci,proc] for proc in preprocessing]

    raw2worms_scinames=pd.DataFrame(raw2worms_scinames,columns=['rawsciname','wormssciname'])
    #print(raw2worms_scinames)
    print("Length after pre-processing:",len(raw2worms_scinames))
    unique=set(raw2worms_scinames.rawsciname.values)
    print("Check number of unique raw scinames:",len(unique))
    #print()
    unique_wormsscinames = raw2worms_scinames.loc[~pd.isnull(raw2worms_scinames['wormssciname']),'wormssciname'].unique().tolist()
    #print("length:",len(unique_wormsscinames))
    #print()
    Nprocessed=len(unique_wormsscinames)

    # Query WoRMS

    print(f'            -- WoRMS API call --')
    print(f'            {len(unique_wormsscinames)} WoRMS-formatted scientific names to process')

    Nwormsscinames = len(unique_wormsscinames)
    fullwormsmatch=[]
    #nbatch = math.ceil(Nwormsscinames/50)
    queryinit=True
    batch=[]

    tempfile=os.path.join(outputpath,'wormsmatch.temp')
    resume=False

    if os.path.isfile(tempfile):

        resume=True
        fullwormsmatch=pd.read_csv(tempfile,sep='\t')
        isdone=list(fullwormsmatch['wormssciname'].unique())
        fullwormsmatch=fullwormsmatch.values.tolist()

    #for batch in tqdm(range(nbatch)):

    #    start = batch*50
    #    if batch==(nbatch-1):
    #        end = Nwormsscinames
    #    else:
    #        end = start + 50
    #    fullwormsmatch+=_match50_WoRMSBySciname(unique_wormsscinames[start:end],wormscallK=wormscallK)

    for i,sciname in enumerate(tqdm(unique_wormsscinames)):

        if (not resume) or (resume and (sciname not in isdone)):
            batch.append(sciname)

        if (len(batch)==50) or ((i+1)==Nwormsscinames):
            fullwormsmatch+=_match50_WoRMSBySciname(batch,wormscallK=wormscallK)
            batch.clear()

        if (((i+1)%10000)==0) or ((i+1)==Nwormsscinames):
            store_fullwormsmatch=pd.DataFrame(fullwormsmatch,columns=['wormssciname']+wormscallV)
            write_dataframe2txtfile(store_fullwormsmatch, tempfile, init=queryinit)
            queryinit=False

    fullwormsmatch=pd.DataFrame(fullwormsmatch,columns=['wormssciname']+wormscallV)
    #print(fullwormsmatch)
    #print("length:",len(fullwormsmatch))
    #print()
    # Match WoRMS

    print(f'            -- WoRMS match filter construction --')

    fullwormsmatch=pd.merge(raw2worms_scinames,fullwormsmatch,how='left',on=['wormssciname'])
    print("Check length fullwormsmatch:",len(fullwormsmatch))

    isduplicated=fullwormsmatch.duplicated(subset=['rawsciname'],keep=False)
    wormsmatch=fullwormsmatch[~isduplicated]
    print("(not NaN & NaN) unique:",len(wormsmatch))

    duplicated_wormsmatch=fullwormsmatch[isduplicated]

    isduplicated_match=(~pd.isnull(duplicated_wormsmatch[WORMSCALL['match_type']]))
    isduplicated_NaN=duplicated_wormsmatch[(~isduplicated_match)].duplicated(subset=['rawsciname'],keep=False)

    if sum(isduplicated_NaN)>0:

        deduplicate_NaN=duplicated_wormsmatch[(~isduplicated_match) & isduplicated_NaN].drop_duplicates(subset=['rawsciname'],keep='last').index
        keep_idx=list(set(duplicated_wormsmatch.index)-set(deduplicate_NaN))
        duplicated_wormsmatch=duplicated_wormsmatch.loc[keep_idx,:]

        isduplicated=duplicated_wormsmatch.duplicated(subset=['rawsciname'],keep=False)
        if sum(~isduplicated)>0:
            wormsmatch=pd.concat([wormsmatch,duplicated_wormsmatch[~isduplicated]],axis=0)
            print("NaN duplicat:",len(duplicated_wormsmatch[~isduplicated]))

        duplicated_wormsmatch=duplicated_wormsmatch[isduplicated]
        bli=set(duplicated_wormsmatch.rawsciname.values)
        print("match duplicat:",len(bli))

        isduplicated_match=(~pd.isnull(duplicated_wormsmatch[WORMSCALL['match_type']]))

    if sum(isduplicated_match)>0:

        duplicated_wormsmatch=duplicated_wormsmatch[isduplicated_match]
        #print(duplicated_wormsmatch)
        #bli=set(duplicated_wormsmatch.rawsciname.values)
        #print("n sciname left:",len(bli))
        deduplicate_wormsmatch=duplicated_wormsmatch[['rawsciname','wormssciname']].set_index(['rawsciname','wormssciname']).index.unique().to_frame().drop_duplicates(subset=['rawsciname'],keep='first').values
        deduplicate_wormsmatch=pd.DataFrame(deduplicate_wormsmatch,columns=['rawsciname','wormssciname'])
        deduplicated_wormsmatch=pd.merge(duplicated_wormsmatch, deduplicate_wormsmatch, on=['rawsciname','wormssciname'])
        #bli=set(deduplicated_wormsmatch.rawsciname.values)
        #print(bli)
        #print("duplicat:",len(deduplicated_wormsmatch))

        wormsmatch=pd.concat([wormsmatch,deduplicated_wormsmatch],axis=0)

    wormsmatch=wormsmatch.rename(columns={'rawsciname':'group'})
    wormsmatch=wormsmatch[colnames]
    #print("final:",len(wormsmatch))

    # Store

    if store:

        wormsmatch.loc[pd.isnull(wormsmatch['worms_matchtype']),'worms_matchtype'] = 'nomatch'

        if 'valid_AphiaID' in wormscallK:
            wormsmatch[WORMSCALL['valid_AphiaID']] = wormsmatch[WORMSCALL['valid_AphiaID']].astype('Int64')

        write_dataframe2txtfile(wormsmatch, outputfile, init=init)

    # Clean

    os.remove(tempfile)

    if not init:
        wormsmatch=pd.concat([previous_wormsmatch,wormsmatch],axis=0)

    return wormsmatch, Nprocessed

def _resume_matchWoRMS(filter, values):

    valuesprocessed = set(filter['group'].tolist())
    values2process = set(values) - valuesprocessed

    return len(valuesprocessed), list(values2process)


def _match50_WoRMSBySciname_v1(preprocessed_species, wormscallK, verbose=False):

    species=list(preprocessed_species.keys())

    preprocessing=list(itemgetter(*species)(preprocessed_species))
    preprocessing=list(itertools.chain(*preprocessing)) #flatten the list
    duplicate=len(preprocessing)-len(set(preprocessing))

    if verbose:
        print(f'            -- WoRMS API call --')

    # Query WoRMS with the pre-processed strings of the 50 species

    results=[]
    nbatch = math.ceil(len(preprocessing)/50)
    for batch in range(nbatch):

        start_idx = batch*50
        if batch==(nbatch-1):
            end_idx = len(preprocessing)
        else:
            end_idx = start_idx + 50

        scinames["scientificname"] = preprocessing[start_idx:end_idx]
        results += _connect_matchAphiaRecordsByNames(scinames)

    if verbose:
        print(f'            -- WoRMS match formatting --')

    # Keep only the match information specified in `wormscallK`

    classification=[]
    cursor=0
    for idx,spe in enumerate(species):

        Npreprocessing=len(preprocessed_species[spe])
        process=False
        i=0

        while not process and i<Npreprocessing:

            res=results[cursor+i]

            if len(res)!=0:

                # Match in WoRMS

                classification += _parse_matchAphiaRecordsByNames(spe,res,wormscallK)
                process=True

            else:

                # No match in WoRMS
                # Try again with the next pre-processed string of the species, if any

                i+=1

        if not process:

            # No match

            classification += [[spe] + [pd.NA]*len(wormscallK)]

        cursor+=Npreprocessing #move on to the next species

    return classification


def match_WoRMSBySciname_v1(species, wormscall=WORMSCALL, identification_level='best', min_length=3, doublecheck=False, store=False, outputpath='./', outputfile='worms_matchfilter.tsv', overwrite=False):

    wormscallK = list(wormscall.keys())
    wormscallV = list(itemgetter(*wormscallK)(wormscall))
    colnames = ['group'] + wormscallV
    outputfile = os.path.join(outputpath,outputfile)

    Nspecies = len(species)
    wormsmatch_temp = []

    print(f'            ** WoRMS filter (recognized marine taxa) | {Nspecies} unique species')

    if os.path.isfile(outputfile):

        if overwrite:

            print(f"            WARNING | {outputpath + outputfile} already exists and will be overwritten")

        else:

            print(f"            INFO | {outputpath + outputfile} already exists and will be used")

            wormsmatch=pd.read_csv(outputfile, sep='\t')
            cumNspecies, species=_resume_matchWoRMS(wormsmatch, species)
            Nspecies+=cumNspecies

            if len(species)==0:
                return wormsmatch
            else:
                print(f'            UPDATE | {len(species)}/{Nspecies} ({np.round(len(species)/Nspecies*100,2)}%) remaining species to be processed')
                wormsmatch_temp=wormsmatch.values.tolist()

    cumNprocessed=0
    cumNnomatch=0
    #Nmatch=0 #SUPRESS APRES DEBUG
    batch={}
    init=True
    for idx,spe in enumerate(species):

        preprocessing = _format_scinamesForWoRMS(spe, identification_level=identification_level, min_length=min_length, doublecheck=doublecheck)

        if isnan(spe) or (len(preprocessing)==0):
            wormsmatch_temp += [[spe] + [pd.NA]*len(wormscallK)]

        else:
            batch[spe]=preprocessing

        if (len(batch)==50) or (idx==(len(species)-1)):
            wormsmatch_temp += _match50_WoRMSBySciname_v1(batch, wormscallK=wormscallK)
            batch={}

        # Display progress

        if ((idx+1)%100==0) or (idx==(len(species)-1)):

            wormsmatch=pd.DataFrame(wormsmatch_temp,columns=colnames)

            #classification_print = wormsmatch.drop_duplicates(subset=['group'],keep='first') #SUPRESS APRES DEBUG
            #Nnomatch = len(classification_print[pd.isnull(classification_print["worms_matchtype"])]) #SUPRESS APRES DEBUG
            #Nmatch = len(classification_print[~pd.isnull(classification_print["worms_matchtype"])]) #SUPRESS APRES DEBUG
            Nprocessed = cumNprocessed + len(wormsmatch['group'].unique())
            Nnomatch = cumNnomatch + len(wormsmatch.loc[pd.isnull(wormsmatch['valid_aphiaID']),'group'].unique()) #UNCOMMENT APRES DEBUG
            #if store:
            #    Nnomatch += cumNnomatch
            #    Nprocessed = len(wormsmatch) + cumNprocessed
            #else:
            #    Nprocessed=len(wormsmatch)
            Nmatch = (Nprocessed - Nnomatch) #UNCOMMENT APRES DEBUG
            #Nprocessed=len(classification_print)
            percentage_done = np.round(Nprocessed/Nspecies*100,2)

            print(f'            Processing | {Nprocessed}/{Nspecies} species done ({percentage_done}%): no_match={Nnomatch}, match={Nmatch}')

        # Save progress

        if store and (((idx+1)%10000==0) or (idx==len(species)-1)):

            wormsmatch=pd.DataFrame(wormsmatch_temp,columns=colnames)
            wormsmatch.loc[pd.isnull(wormsmatch['worms_matchtype']),'worms_matchtype'] = 'nomatch'

            if 'valid_aphiaID' in wormscall.keys():
                wormsmatch['valid_aphiaID'] = wormsmatch['valid_aphiaID'].astype('Int64')

            write_dataframe2txtfile(wormsmatch, outputfile, init=init)

            init=False
            cumNnomatch+=len(wormsmatch.loc[pd.isnull(wormsmatch['worms_matchtype']),'group'].unique())
            cumNprocessed+=len(wormsmatch['group'].unique())
            wormsmatch_temp.clear()

    if store:
        wormsmatch=pd.read_csv(outputfile, sep='\t')
    else:
        wormsmatch=pd.DataFrame(wormsmatch_temp,columns=colnames)

    return wormsmatch


def old_match_WoRMS(species, wormscall=WORMSCALL, doublecheck=False, store=False, outputpath='./', outputfile='worms_matchfilter.tsv', overwrite=False):

    nspecies_print = len(species)
    resume=False
    print(f'            ** WoRMS filter (recognized marine taxa) | {nspecies_print} unique species')

    if os.path.isfile(outputpath + outputfile):

        if overwrite:
            print(f"            WARNING | {outputpath + outputfile} already exists and will be overwritten")
        else:
            print(f"            INFO | {outputpath + outputfile} already exists and will be used")
            matched_worms = pd.read_csv((outputpath + outputfile), sep='\t')

            species = resume_match_WoRMSBySciname(matched_worms, species)

            if len(species)==0:
                return matched_worms
            else:
                print(f'            UPDATE | {len(species)}/{nspecies_print} ({np.round(len(species)/nspecies_print*100,2)}%) remaining species to be processed')
                resume=True

    nspecies = len(species)
    nbatch = int(np.ceil(nspecies/50))
    done = nspecies_print - nspecies
    for batch in range(tqdm(nbatch)):

        start_idx = batch*50
        if batch==(nbatch-1):
            end_idx = nspecies
        else:
            end_idx = start_idx + 50

        species_subset = species[start_idx:end_idx]
        classification = match50_WoRMSBySciname(species_subset, wormscall=wormscall, doublecheck=doublecheck)

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
            write_dataframe2txtfile(matched_worms, file, init=True)

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

            valid_aphiaID = resume_match_WoRMSBySciname(accepted_worms, valid_aphiaID)

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
                write_dataframe2txtfile(accepted_worms, outputfile, init=True)

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

    worms_matchfilter = match_WoRMSBySciname(unique_rawsciname, **params)

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

from tqdm import tqdm

def test_preprocess(identification_level,doublecheck=True):

    species = pd.read_csv('/data/smartbiodiv/eberhocoi/source/unique_verbatimScientificName_v2.txt',sep='\t')
    species = species.raw_sciname.tolist()

    outputfile=f'/data/smartbiodiv/eberhocoi/source/verbatimScientificName_processed_{identification_level}_{doublecheck}.txt'

    preprocessed_sciname=[]
    init=True
    for idx,spe in enumerate(tqdm(species)):
        results=_format_scinamesForWoRMS(spe, identification_level=identification_level,doublecheck=doublecheck)
        for res in results:
            preprocessed_sciname.append([spe,res])

        if (idx+1)%10000==0:
            store=pd.DataFrame(preprocessed_sciname,columns=['verbatim','processed'])
            write_dataframe2txtfile(store,outputfile,init=init,verbose=False)
            init=False
            preprocessed_sciname.clear()

    store=pd.DataFrame(preprocessed_sciname,columns=['verbatim','processed'])
    write_dataframe2txtfile(store,outputfile,init=init,verbose=False)

import random

def test_50(species_dict):

    #df = pd.read_csv('/data/smartbiodiv/eberhocoi/source/verbatimScientificName_processed_species_v3.txt', sep='\t')
    #print(f"{len(df)} lines to process")
    #species_dict=df[['verbatim','processed']].groupby(['verbatim'])['processed'].apply(list).to_dict()

    speciesK=list(species_dict.keys())
    wormscall_keys=list(WORMSCALL.keys())
    samples=random.sample(range(len(speciesK)),30)

    time_all=[]
    classif_all=[]
    count_all=[]
    match_all=[]
    duplicate_all=[]

    start=time.time()
    for i in samples:
        processed_species=dict(zip(speciesK[i:i+50],list(itemgetter(*speciesK[i:i+50])(species_dict))))
        classification,count,store_time,match,duplicate=_match50_WoRMSBySciname(processed_species, wormscall_keys)
        time_all+=store_time
        count_all+=count
        classif_all+=classification
        match_all.append(match)
        duplicate_all.append(duplicate)
    end=time.time()
    print(f'TIME : {np.round(end - start,0)}s')

    return classif_all,count_all,time_all,match_all,duplicate_all

def test_v1():

    species = pd.read_csv('/data/smartbiodiv/eberhocoi/source/unique_verbatimScientificName_v2.txt',sep='\t')

    size=[100,10000]

    time_storage=[]

    for s in size:
        print("SIZE:",s)
        for i in range(10):

            index=random.randint(0,len(species))
            scinames = species.raw_sciname.tolist()[index:index+s]

            start=time.time()
            wormsmatch=match_WoRMSBySciname_v1(scinames, wormscall=WORMSCALL, identification_level='species', doublecheck=True, store=True, outputpath='/data/smartbiodiv/eberhocoi/source',outputfile='worms_matchfilter_v1.txt')
            end=time.time()

            time_storage.append([s,round(end - start),s])
            print(f'TIME : {round(end - start)}s')

            storage=pd.DataFrame(time_storage,columns=['size','time','Nprocessed'])
            write_dataframe2txtfile(storage, '/data/smartbiodiv/eberhocoi/source/time_v1.txt', init=True, verbose=True)

            print()
            print()

    return wormsmatch

def test():

    species = pd.read_csv('/data/smartbiodiv/eberhocoi/source/unique_verbatimScientificName_v2.txt',sep='\t')
    size=[10000]

    time_storage=[]

    for s in size:
        print("SIZE:",s)
        for i in range(6):

            index=random.randint(0,len(species))
            scinames = species.raw_sciname.tolist()[index:index+s]

            start=time.time()
            wormsmatch,Nprocessed=match_WoRMSBySciname(scinames, wormscall=WORMSCALL, identification_level='species', doublecheck=True, store=True, outputpath='/data/smartbiodiv/eberhocoi/source', outputfile='worms_matchfilter_v2.txt')
            end=time.time()

            time_storage.append([s,round(end - start),Nprocessed])
            print(f'TIME : {round(end - start)}s')

            storage=pd.DataFrame(time_storage,columns=['size','time','Nprocessed'])
            write_dataframe2txtfile(storage, '/data/smartbiodiv/eberhocoi/source/time_v2_B.txt', init=True, verbose=True)

            print()
            print()



if __name__ == '__main__':

     #parser = argparse.ArgumentParser()
     #parser.add_argument('--identification_level', type=str, help='identification level', default='best')
     #args = parser.parse_args()
     #test_preprocess(args.identification_level)

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
