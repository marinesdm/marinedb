#!/usr/bin/python

# External imports

import pandas as pd
import numpy as np
import argparse
from operator import itemgetter
from functools import wraps
from unidecode import unidecode
import re
from difflib import get_close_matches
import Levenshtein
import json
import time

# Local imports

from marinedb.filters import createwormsfilters as cwf
from marinedb.filters import dropvalues
from marinedb.filters import subsetranks
from marinedb.utils import regexstrip
from marinedb.utils import getdefaultargs
from marinedb.utils import standardizenan

# Global variables

## Rank names in the file to be processed

# schema: RANK = {rank_name: rank_name_in_the_file}

 #################################################################################
 # Leave `rank_name` unchanged, modify only `rank_name_in_the_file` if necessary #
 #################################################################################

#RANK = {
#        'species':'verbatimScientificName',
#        'genus':'genus',
#        'family':'family',
#        'order':'order',
#        'class':'class',
#        'phylum':'phylum',
#        'kingdom':'kingdom'
#       }

#WORMS_MAPPING FAIT
#RANK fait

RANK_MAPPING = {
                'scientificname':'verbatimScientificName',
                'genus':'genus',
                'family':'family',
                'order':'order',
                'cls':'class',
                'phylum':'phylum',
                'kingdom':'kingdom'
               }

## Map custom vocabulary to WoRMS vocabulary

# schema: WORMS_MAPPING = {custom_vocabulary: worms_vocabulary}

 ####################################################################
 # Custom vocabulary must match that used in createwormsfilters.py, #
 # if filters were created upstream                                 #
 ####################################################################

 ###########################################
 # Do not remove starred dictionary values #
 ###########################################

#WORMS_MAPPING = {
#                  RANK['species']:'scientificname', #* (cwf, isinworms)
#                  RANK['genus']:'genus', #* (isinworms)
#                  RANK['family']:'family', #* (isinwors)
#                  RANK['order']:'order', #* (isinworms)
#                  RANK['class']:'cls', #* (isinworms)
#                  RANK['phylum']:'phylum', #* (isinworms)
#                  RANK['kingdom']:'kingdom', #* (isinworms)
#                  'worms_matchtype':'match_type', #* (cwf, isinworms)
#                  'worms_status':'status', #* (cwf, isinworms)
#                  'valid_aphiaID':'valid_AphiaID', #* (cwf, isinworms)
#                  'isextinct':'isExtinct',
#                  'ismarine':'isMarine',
#                  'rank':'rank', #* (cwf)
#                  'authority':'authority'
#                 }

#WORMSCALL = {v:k for k,v in WORMS_MAPPING.items()}

WORMSCALL = [
             'scientificname', #* (cwf, isinworms)
             'genus', #* (isinworms)
             'family', #* (isinwors)
             'order', #* (isinworms)
             'cls', #* (isinworms)
             'phylum', #* (isinworms)
             'kingdom', #* (isinworms)
             'match_type', #* (cwf, isinworms)
             'status', #* (cwf, isinworms)
             'valid_AphiaID', #* (cwf, isinworms)
             'isExtinct',
             'isMarine',
             'rank', #* (cwf)
             'authority'
            ]

COLNAMES = list(set(list(set(WORMSCALL) - set(RANK_MAPPING.keys())) + list(RANK_MAPPING.values())))

## WORMS-specific column dtypes

#WORMS_DTYPES = {
#                WORMSCALL['match_type']:'string',
#                WORMSCALL['status']:'string',
#                WORMSCALL['valid_AphiaID']:'Int64',
#                WORMSCALL['isExtinct']:'Int64',
#                WORMSCALL['isMarine']:'Int64',
#                WORMSCALL['rank']:'string',
#                WORMSCALL['authority']:'string'
#               }

WORMS_DTYPES = {
                'match_type':'string',
                'status':'string',
                'valid_AphiaID':'Int64',
                'isExtinct':'Int64',
                'isMarine':'Int64',
                'rank':'string',
                'authority':'string'
               }

## Number of mismatches allowed according to the number of missing values

NaN2AllowedMismatch = {0:2,
                       1:2,
                       2:1,
                       3:0,
                       4:0,
                       5:0,
                       6:-1}


class NotImplemented(Exception): #À SUPPRIMER APRES DEBUG
    pass

def _resume(filter, values, issciname):

    if not issciname:
        filter['group'].astype('Float64').astype('Int64')

    valuesprocessed = set(filter['group'].tolist())
    values2process = set(values) - valuesprocessed

    return list(values2process)

def handlenan(func):

    @wraps(func)
    def nanfunc(df, keys, **options):

        if isinstance(keys, str):
            keys = [keys]

        # Handle cases with only missing values separately (return pd.NA)
        res = pd.Series([pd.NA]*len(df), dtype='object', index=df.index.to_list())
        isallnan = df[keys].isna().all(axis=1)
        res[~isallnan] = func(df[~isallnan], keys, **options)

        return res

    return nanfunc

@handlenan
def pdmin(df, keys, **options):
    return df[keys].min(**options)

@handlenan
def pdmax(df, keys, **options):
    return df[keys].max(**options)

@handlenan
def idxmin(df, keys, **options):
    return df[keys].idxmin(**options)

@handlenan
def idxmax(df, keys, **options):
    return df[keys].idxmax(**options)

@handlenan
def pdmean(df, keys, **options):
    return df[keys].mean(**options)

def naneqsingle(series1, series2):

    if (len(series1)!=len(series2)):
        raise Exception

    if (len(series1.shape)!=1) or (len(series2.shape)!=1):
        raise Exception

    if series1.index.to_list()!=series2.index.to_list():
        raise Exception

    temp = pd.concat([series1,series2], axis='columns')
    isallnan = temp.isna().all(axis='columns')

    # Process cases with only missing values separately (return pd.NA)
    res = pd.Series([pd.NA]*len(series1), dtype='boolean', index=series1.index.to_list())
    res[~isallnan] = series1[~isallnan].eq(series2[~isallnan])

    return res

def clean_string(string):

    # remove the accents
    string=unidecode(string)

    # replace special characters by " "
    pattern=r'[^a-zA-Z\s]+'
    string=re.sub(pattern, ' ', string)

    # standardize whitespace
    string=re.sub('\s+', ' ', string)

    # strip
    string=string.strip()

    # convert into lowercase characters
    string=string.lower()

    return string

def clean_split_strings(strings, authorship=False):

    # Example: '(Claparède & Lachmann) Diesing' TO ['claparede', 'lachmann', 'diesing']

    strings_print=strings

    if authorship:
        # replace "and" in different languages by " "
        # remark: do no delete all words of less than 1 or 2 letters,
        # as sometimes only the first letter of the author is specified
        # e.g. "L." for Linné/Linnaeus
        pattern='\s((and)|(et)|(und)|[yie])\s'
        strings=re.sub(pattern, ' ', strings)

    # Split `strings` into words

    strings=np.array(re.split(r'\s+',strings))

    # Clean words

    keep=[]
    for i, string in enumerate(strings):
        strings[i]=clean_string(string)
        if len(strings[i])!=0:
            keep.append(i)

    # Keep only non-empty strings

    return list(strings[keep])

def elementwise_LevensteinRatio(strings, refstrings, difflib_cutoff=0.5): #!one-way

    if pd.isnull(refstrings) or (len(refstrings)==0) or pd.isnull(strings) or (len(strings)==0):
        return pd.NA, pd.NA

    # Preparing strings
    refstrings = clean_split_strings(refstrings)
    strings = clean_split_strings(strings)

    ratio=0
    Nmatch=0
    for string in strings: #the result depends on the order of the `string` list

        ## Find the component closest to `string` in `refstrings`
        stringbestmatch = get_close_matches(string, refstrings, n=1, cutoff=difflib_cutoff) #difflib: cutoff=0.6 by default

        ## Compute the Levenstein ratio between `string` and `stringbestmatch`
        if len(stringbestmatch)!=0:
            Nmatch+=1
            stringbestmatch=stringbestmatch[0]
            ratio+=Levenshtein.ratio(string, stringbestmatch)
            del refstrings[refstrings.index(stringbestmatch)]

    return np.round(ratio/len(strings),2), Nmatch

def _match_WormsToVerbatimSpecies(wormsspecies, verbatimspecies, phonetic=False, cutoff_phonetic=0.7):

    wormsspecies = clean_split_strings(wormsspecies, authorship=True)
    verbatimspecies = clean_split_strings(verbatimspecies, authorship=True)

    if phonetic:
        cutoff=cutoff_phonetic
    else:
        cutoff=0.5

    levenshtein_distance=0
    mapping=[]
    for wormsstring in wormsspecies:

        # Find the component closest to `wormsstring` in `verbatimspecies`
        verbatimbestmatch=get_close_matches(wormsstring, verbatimspecies, n=1, cutoff=cutoff)

        if len(verbatimbestmatch)!=0:
            # Calculate the Levenshtein distance
            levenshtein_distance+=Levenshtein.distance(wormsstring,verbatimbestmatch[0])
        else:
            levenshtein_distance=4

        # Store worms-to-verbatim mapping
        mapping+=verbatimbestmatch

    if not phonetic:
        if levenshtein_distance<=3:
            # "near_3" (i.e 3-character mismatch) is the worst matching level in WoRMS, excluding "phonetic"
            return ' '.join(mapping)
        else:
            return ''

    else:
        # using a threshold with Levenshtein distance may not be relevant for "phonetic" matching level in WoRMS
        if len(mapping)==len(wormsspecies):
            return ' '.join(mapping)
        else:
            return ''


def split_authorship(authorship):

    if pd.isnull(authorship) or (len(authorship)==0): # i.e pd.NA or authorship==''
        return pd.NA, pd.NA, pd.NA

    # Find the date(s), if present

    pattern=r'[0-9]{4}'
    res=re.finditer(pattern,authorship)
    match = [m for m in res]

    # Find the author(s)

    if len(match)>1:

        # More than one date

        raise Exception(f'Multiple dates found in the taxon authorship {authorship}')

    elif (len(match)==0):

        # No date
        # assumption : the string corresponds to the authors' names

        date=pd.NA
        author=regexstrip.apply(authorship,r'[^a-zA-Z0-9]+')
        more=''

    else:

        # One date

        match=match[0]
        date=int(match.group())
        start, stop = match.span()

        if (start==0):

            # Date at the beginning of the string
            # assumption : the end of the string corresponds to the authors' names

            author=regexstrip.apply(authorship[stop:],r'[^a-zA-Z0-9]+')
            more=''
            processed=True

        elif (stop==len(authorship)):

            # Date at the end of the string
            # assumption : the beginning of the string corresponds to the authors' names

            author=regexstrip.apply(authorship[:start],r'[^a-zA-Z0-9]+')
            more=''
            processed=True

        elif (authorship[start-1]=='(') and (authorship[stop]!=')'):

            # Date preceded by a parenthesis
            # Find the closing parenthesis

            res=re.fullmatch(fr'(?P<more1>.*?)\({authorship[start:stop]}(?P<author>.+)\)(?P<more2>.*)', authorship)

            if res:

                # assumption : the text up to the last closing parenthesis corresponds to the authors' names
                # i.e more (date author) more
                author = regexstrip.apply(res['author'],r'[^a-zA-Z0-9]+')
                more = regexstrip.apply(res['more1'],r'[^a-zA-Z0-9]+') + regexstrip.apply(res['more2'],r'[^a-zA-Z0-9]+')
                processed=True

            else:
                processed=False

        elif (authorship[stop]==')') and (authorship[start-1]!='('):

            # Date followed by a parenthesis
            # Find the opening parenthesis

            res=re.fullmatch(fr'(?P<more1>.*?)\((?P<author>.+?){authorship[start:stop]}\)(?P<more2>.*)', authorship)

            if res:

                # assumption : the text up to the first opening parenthesis (read backwards) corresponds to the authors' names
                # i.e more (author date) more
                author = regexstrip.apply(res['author'],r'[^a-zA-Z0-9]+')
                more = regexstrip.apply(res['more1'],r'[^a-zA-Z0-9]+') + regexstrip.apply(res['more2'],r'[^a-zA-Z0-9]+')
                processed=True

            else:
                processed=False

        else:
            processed=False

        if not processed:

            start_string=authorship[:start]
            stop_string=authorship[stop:]

            start_string=regexstrip.apply(start_string, r'[^a-zA-Z0-9]+')
            stop_string=regexstrip.apply(stop_string, r'[^a-zA-Z0-9]+')

            # assumption : the non-empty string corresponds to the authors' names
            if len(start_string)==0:
                author=stop_string
                more=''
            elif len(stop_string)==0:
                author=start_string
                more=''
            else:
                # assumption: the string preceding the date corresponds to the authors' names, following established conventions
                author=start_string
                more=stop_string

    # set aside text that probably does not correspond to the authors' names
    match=re.search(r'[A-Z]', author)
    if match:
        start = match.start()
        if start!=0:
            try:
                more += author[:start]
            except TypeError:
                # may or may not correspond to the authors' name
                more = author[:start]
            author = author[start:]
    else:
        try:
            more += author
        except TypeError:
            more = author

    # drop all special characters
    more=re.sub(r'[^a-zA-Z0-9]+','',more)

    return date, author, more


def _match_AuthorshipByAuthors(refauthors, authors,  difflib_cutoff=0.5, levenshtein_tolerance=0.7, author_tolerance=0.7):

    if pd.isnull(refauthors) or (len(refauthors)==0) or pd.isnull(authors) or (len(authors)==0):
        return pd.NA, pd.NA

    # Preparing authors' names
    refauthors = clean_split_strings(refauthors, authorship=True)
    authors = clean_split_strings(authors, authorship=True)

    # Do `authors` and `refauthors` match?

    Nmatch=0
    for author in authors:

        ## Find the component closest to `author` in `refauthors`
        authorbestmatch = get_close_matches(author, refauthors, n=1, cutoff=difflib_cutoff) #difflib: cutoff=0.6 by default

        ## Do `author` and `authorbestmatch` match?

        # delete parts of the string containing 3 or fewer letters to avoid false mismatches
        # e.g. "J.Lachm." => `author`='j lachm'
        # vs.  "Lachmann" => `authorbestmatch`='lachmann'
        temp = author.split()
        temp = ' '.join([string for string in temp if len(string)>3])
        if len(temp)>0:
            author = temp

        if len(authorbestmatch)!=0:
            # should always be the case when `difflib_cutoff`=0
            authorbestmatch=authorbestmatch[0]

            # delete parts of the string containing 3 or fewer letters
            temp = authorbestmatch.split()
            temp = ' '.join([string for string in temp if len(string)>3])
            if len(temp)>0:
                authorbestmatch = temp

            if (author in authorbestmatch) or (authorbestmatch in author):
                # one contains the other
                Nmatch+=1

            elif Levenshtein.ratio(authorbestmatch, author)>=levenshtein_tolerance:
                # the levenshtein ratio between `authorbestmatch` and `author` is higher than `levenstein_tolerance`
                # `author` and `authorbestmatch` match sufficiently
                Nmatch+=1

            # else: no match

    ## Full match

    score = np.round(Nmatch/len(authors),1)
    if score>=author_tolerance:
        return True, score
    else:
        return False, score


def _match_AuthorshipsByDatesAuthors(refauthorships, authorship, date_tolerance=2, difflib_cutoff=0.5, levenshtein_tolerance=0.7, author_tolerance=0.7): #author, date dataframe

    authorship['date']=authorship['date'].astype('Int64')
    refauthorships['date']=refauthorships['date'].astype('Int64')

    refauthorships['datematch_diff']=pd.NA
    refauthorships['datematch']=pd.NA
    refauthorships['authormatch_ratio']=pd.NA
    refauthorships['authormatch']=pd.NA

    # Date match

    if any(~pd.isnull(authorship['date'])):

        refauthorships['datematch_diff'] = np.abs(refauthorships['date'] - authorship.loc[0,'date'])
        refauthorships['datematch'] = (refauthorships['datematch_diff'] <= date_tolerance)
        refauthorships.loc[(pd.isnull(refauthorships['date'])),'datematch'] = pd.NA

        index = refauthorships[(pd.isnull(refauthorships['date'])) | (refauthorships['datematch'])].index
        index = list(index)

    else:
        # no date
        index = list(refauthorships.index)

    # Author match

    params = {'difflib_cutoff':difflib_cutoff,
              'levenshtein_tolerance':levenshtein_tolerance,
              'author_tolerance':author_tolerance}

    for i, refauthors in enumerate(refauthorships.loc[index,'author']):
        refauthorships.loc[index[i],['authormatch','authormatch_ratio']] = _match_AuthorshipByAuthors(refauthors, authorship.loc[0,'author'], **params)

    # Final match
    # date and author must both match when known,
    # otherwise date or author, whichever is known, must match

    refauthorships['match'] = pdmin(refauthorships, ['datematch','authormatch'], axis=1, skipna=True).astype('boolean')
    refauthorships['datematch_diff'] = refauthorships['datematch_diff'].astype('Int64')
    refauthorships['authormatch_ratio'] = refauthorships['authormatch_ratio'].astype('Float64')

    return refauthorships


def _match_TaxaByAuthorship(verbatim, candidates, date_tolerance=2, difflib_cutoff=0.5, levenshtein_tolerance=0.7, author_tolerance=0.7): #species, authorship, worms status dataframe #same species

    params = {'date_tolerance':date_tolerance,
              'difflib_cutoff':difflib_cutoff,
              'levenshtein_tolerance':levenshtein_tolerance,
              'author_tolerance':author_tolerance}

    candidates[['sensu_conflict','match','datematch','datematch_diff','authormatch','authormatch_ratio']]=pd.NA
    candidates[['sensu_conflict','match','datematch','authormatch']]=candidates[['sensu_conflict','match','datematch','authormatch']].astype('boolean')
    candidates['datematch_diff']=candidates['datematch_diff'].astype('Int64')
    candidates['authormatch_ratio']=candidates['authormatch_ratio'].astype('Float64')
    ismore = False

    if pd.isnull(verbatim) or (len(verbatim)==0):
        return candidate, ismore

    try:
        verbatim = verbatim.encode('latin-1').decode('utf-8')
    except UnicodeDecodeError:
        pass
    verbatim = unidecode(verbatim.strip())

    speidx = candidates.columns.to_list().index(RANK_MAPPING['scientificname'])
    wormsspecies = unidecode(candidates.iloc[0,speidx].strip())
    # note: Only the species name in the first line is considered.
    # In most cases, WoRMS candidates share the same species name.
    # However, if they do not, the best species name match
    # has been placed on the first line by the _match_TaxaByFullClassification() function.

    # Find the species name in `verbatim`

    ## Determine the spelling of the species name components in `verbatim` using `wormsspecies`
    # i.e take misspelling into account e.g. "Clatria rubens" for "Clathria rubens"

    if 'status' in candidates.columns:
        status = candidates['status'].tolist()
        if 'phonetic' in status:
            phonetic=True
        else:
            phonetic=False
    else:
        phonetic=False

    wormsspecies = _match_WormsToVerbatimSpecies(wormsspecies, verbatim, phonetic=phonetic)

    if len(wormsspecies)==0:

        # no match between `wormsspecies` components and `verbatim` components
        # assumption : `verbatim` only contains information on the authorship
        #candidates["match"]=False
        #candidates[["sensu_conflict","datematch_diff","datematch","authormatch_ratio","authormatch"]]=pd.NA
        ismore=True
        verbatim_authorship = verbatim

    else:

        ## Search for the species name in `verbatim`, taking into account mid-string variations
        # e.g. Atrina pectinata & Atrina (Servatrina) pectinata

        wormsspecies_split = wormsspecies.split()
        wormsspecies_pattern = ''.join(fr'{string}(?P<more{i}>.*?)' for i,string in enumerate(wormsspecies_split[:-1])) + wormsspecies_split[-1]
        speciesmatch = re.search(fr'(?<![a-zA-Z]){wormsspecies_pattern}', verbatim, flags=re.IGNORECASE)

        if speciesmatch: # species name found

            # Put aside the species name to find the authorship information

            start, end = speciesmatch.span()
            verbatim_species = verbatim[start:end]
            verbatim_authorship = verbatim[:start] + verbatim[end:]

            more = ''.join(speciesmatch.groups())
            more=re.sub(r'[^a-zA-Z0-9]+','',more)
            if len(more)>1:
                ismore=True
            else:
                ismore=False

        else: # species name not found

            # assumption : `verbatim` only contains information on the authorship

            #candidates["match"]=False
            #candidates[["sensu_conflict","datematch_diff","datematch","authormatch_ratio","authormatch"]]=pd.NA
            ismore=True
            verbatim_authorship = verbatim

    if len(verbatim_authorship)==0:

        # no authorship information to separate candidates

        candidates['match'] = True
        #candidates[["sensu_conflict","datematch_diff","datematch","authormatch_ratio","authormatch"]]=pd.NA

    else:

        # Authorship match

        ## Does verbatim authorship contain "sensu"?

        doescontainsensu_verbatim = ('sensu' in verbatim_authorship)

        ## Do the authorship candidates contain "sensu"?

        doescontainsensu_candidates = candidates['authorship'].str.contains('sensu')

        ## Are there "sensu" conflicts between verbatim and authorship candidates?
        # `verbatim_authorship` does not contain "sensu" & one or more candidates contain "sensu"
        #  OR
        # `verbatim_authorship` contain "sensu" & one or more candidates does not contain "sensu"

        candidates['sensu_conflict'] = False
        candidates.loc[doescontainsensu_candidates!=doescontainsensu_verbatim, 'sensu_conflict'] = True

        if doescontainsensu_verbatim:

            # `verbatim_authorship` contains "sensu"

            verbatim_authorship = verbatim_authorship.split('sensu')

            if len(verbatim_authorship)>2:

                # more than one "sensu": unexpected

                raise NotImplemented(f'More than one "sensu" in the authorship ({verbatim}).') #pour le débug, à supprimer ensuite
                #print(f"WARNING | More than one 'sensu' in {verbatim}. Exit `_match_TaxaByAuthorship`.")
                #return None

            # for candidates not containing "sensu", no match is possible

            candidates.loc[~doescontainsensu_candidates, 'match'] = False
            candidates_authorships = candidates.loc[doescontainsensu_candidates,['authorship']].copy()

        else:

            # `verbatim_authorship` does not contain "sensu"
            # but one or more candidates may contain "sensu"
            # and `verbatim_authorship` could match one of the authors of these candidates

            candidates_authorships = candidates[['authorship']].copy()


        if len(candidates_authorships)==0:

            # i.e `verbatimauthorship` contains "sensu"
            # but no candidate contains "sensu"
            # no match

            _ , _ , more = split_authorship(verbatim_authorship[0])
            if len(verbatim_authorship)!=1:
                _ , _ , moretemp = split_authorship(verbatim_authorship[1])
                more += moretemp
            if len(more)>0:
                ismore=True

        else:

            candidates_sensusplit = candidates_authorships['authorship'].str.split('sensu')

            if any(doescontainsensu_candidates):

                exitcondition = (candidates_sensusplit.str.len()>2)

                if any(exitcondition):

                    # more than one "sensu": unexpected

                    raise NotImplemented(f'More than one "sensu" in the authorship ({candidates["authorship"].tolist()}).')
                    #print(f"WARNING | More than one 'sensu' in {candidates["authorship"].tolist()}. Exit `_match_TaxaByAuthorship`.")
                    #return None

            ## Split authorships into date, author, more

            # `verbatim_authorship`

            if doescontainsensu_verbatim:
                verbatim_authorship = list(split_authorship(verbatim_authorship[0])) + list(split_authorship(verbatim_authorship[1]))
            else:
                verbatim_authorship = list(split_authorship(verbatim_authorship))
                verbatim_authorship += verbatim_authorship
            verbatim_authorship=pd.DataFrame([verbatim_authorship], columns=['date1','author1','more1', 'date2', 'author2', 'more2'])

            if any(verbatim_authorship['more1'].str.len()>0) or any(verbatim_authorship['more2'].str.len()>0):
                ismore=True

            # `candidates_authorships`

            candidates_authorships['authorship1'] = candidates_sensusplit.str[0]
            candidates_authorships['authorship2'] = candidates_sensusplit.str[1] #pd.NA if len<2
            index = candidates_authorships.index.to_list()

            for i, authorship in enumerate(candidates_authorships[['authorship1','authorship2']].values):
                candidates_authorships.loc[index[i],['date1','author1','more1']] = split_authorship(authorship[0])
                candidates_authorships.loc[index[i],['date2','author2','more2']] = split_authorship(authorship[1])

            ## Match authorships, both before and after "sensu", by date and author

            colmap1, colmap2 = {'date1':'date','author1':'author'}, {'date2':'date','author2':'author'}
            res1 =_match_AuthorshipsByDatesAuthors(candidates_authorships[list(colmap1.keys())].rename(columns=colmap1), verbatim_authorship[list(colmap1.keys())].rename(columns=colmap1), **params)
            res2 =_match_AuthorshipsByDatesAuthors(candidates_authorships[list(colmap2.keys())].rename(columns=colmap2), verbatim_authorship[list(colmap2.keys())].rename(columns=colmap2), **params)

            columns = ['match','datematch','datematch_diff','authormatch','authormatch_ratio']

            res1, res2 = res1[columns], res2[columns]
            colmap1 = dict(zip(res1.columns, (res1.columns + '1')))
            colmap2 = dict(zip(res2.columns, (res2.columns + '2')))
            res1 = res1.rename(columns=colmap1)
            res2 = res2.rename(columns=colmap2)
            candidates_authorships = pd.concat([candidates_authorships,res1[list(colmap1.values())],res2[list(colmap2.values())]],axis=1)

            ## Final match

            # if `verbatim_authorship` does not contain "sensu":
            #   for candidates containing "sensu" (i.e sensu_conflict=True), `verbatim_authorship` must match one of the candidates' authors
            #     if `verbatim_authorhip` matches a candidate's two authors, store the best match information, if any
            #       if the best match is not obvious, keep the information of the candidate whose author is the best match

            doescandidatecontain = (candidates.index.isin(index)) & (candidates['sensu_conflict'])

            if any(doescandidatecontain):

                doescandidatecontain = doescandidatecontain[doescandidatecontain].index.to_list()

                temp = candidates_authorships.loc[doescandidatecontain,:].copy()
                temp_match = temp[['match1','match2']].sum(axis=1)

                # No match

                index_nomatch = temp_match[temp_match==0].index.to_list()
                if len(index_nomatch)!=0:
                    candidates.loc[index_nomatch,'match']=False

                idx1 = []
                idx2 = []

                # Only one match

                index_singlematch = temp_match[temp_match==1].index.to_list()
                if len(index_singlematch)!=0:
                    singlematch = idxmax(temp.loc[index_singlematch,:], ['match1','match2'], axis=1, skipna=True)
                    idx1 = idx1 + singlematch[singlematch=='match1'].index.to_list()
                    idx2 = idx2 + singlematch[singlematch=='match2'].index.to_list()

                # More than one match

                index_morematch = temp_match[temp_match>1].index.to_list()
                if len(index_morematch)!=0:

                    #(~morematch_eqauthors) & (~morematch_eqdates) & (morematch_eqbest) : best author (equivalent to best date)
                    #(~morematch_eqauthors) & (~morematch_eqdates) & (~morematch_eqbest) : if conflict between best author and best date, best author by default
                    #(~morematch_eqauthors) & (morematch_eqdates) : best author
                    #(morematch_eqauthors) & (~morematch_eqdates) : best date
                    #(morematch_eqauthors) & (morematch_eqdates) : best author (equivalent to best date)

                    morematch = temp.loc[index_morematch,:]

                    morematch_eqauthors = ((morematch['authormatch_ratio1']-morematch['authormatch_ratio2']).abs() <= 1e-2)
                    isnull = morematch[['authormatch_ratio1','authormatch_ratio2']].isna().sum(axis=1)
                    morematch_eqauthors[isnull==1] = False # if only one is null, there is no equality in author match
                    morematch_eqauthors[isnull==2] = True # if both are null, the author match is considered equal

                    morematch_eqdates = naneqsingle(morematch['datematch_diff1'], morematch['datematch_diff2'])
                    morematch_eqdates[pd.isnull(morematch_eqdates)] = True  # if both are null, the date match is considered equal

                    morematch_bestauthor = idxmax(morematch, ['authormatch_ratio1','authormatch_ratio2'], axis=1, skipna=True).str[-1]
                    morematch_bestdate = idxmin(morematch, ['datematch_diff1','datematch_diff2'], axis=1, skipna=True).str[-1]

                    conditions11 = (morematch_eqauthors) & (~morematch_eqdates) & (morematch_bestdate=='1')
                    conditions12 = ((~morematch_eqauthors) | (morematch_eqdates)) & (morematch_bestauthor=='1')
                    idx1 = idx1 + morematch[conditions11 | conditions12].index.to_list()

                    conditions21 = (morematch_eqauthors) & (~morematch_eqdates) & (morematch_bestdate=='2')
                    conditions22 = ((~morematch_eqauthors) | (morematch_eqdates)) & (morematch_bestauthor=='2')
                    idx2 = idx2 + morematch[conditions21 | conditions22].index.to_list()


                if len(idx1)!=0:
                    candidates.loc[idx1, columns] = candidates_authorships.loc[idx1,list(itemgetter(*columns)(colmap1))].values
                if len(idx2)!=0:
                    candidates.loc[idx2, columns] = candidates_authorships.loc[idx2,list(itemgetter(*columns)(colmap2))].values

            # else:
            #   both authorships must match when known
            #   otherwise, whichever is known, must match

            doescandidateequal = (candidates.index.isin(index)) & (~candidates['sensu_conflict'])
            doescandidateequal = doescandidateequal[doescandidateequal].index.to_list()

            candidates.loc[doescandidateequal,'match'] = pdmin(candidates_authorships.loc[doescandidateequal,:],['match1','match2'], axis=1, skipna=True).astype('boolean')
            candidates.loc[doescandidateequal,'datematch'] = pdmin(candidates_authorships.loc[doescandidateequal,:],['datematch1','datematch2'], axis=1, skipna=True).astype('boolean')
            candidates.loc[doescandidateequal,'authormatch'] = pdmin(candidates_authorships.loc[doescandidateequal,:],['authormatch1','authormatch2'], axis=1, skipna=True).astype('boolean')
            candidates.loc[doescandidateequal,'datematch_diff'] = candidates_authorships.loc[doescandidateequal,['datematch_diff1','datematch_diff2']].sum(axis=1, skipna=True, min_count=1).astype('Int64')
            candidates.loc[doescandidateequal,'authormatch_ratio'] = pdmean(candidates_authorships.loc[doescandidateequal,:],['authormatch_ratio1','authormatch_ratio2'], axis=1, skipna=True).astype('Float64')

    return candidates, ismore  #if ismore & all(~candidates["match"]), new WoRMS request with verbatim


def _match_TaxaByVerbatim(verbatim, candidates, wormscolumns, verbatimauthorshiponly=False): #verbatimcolumn=None

    processed = False
    classif = None

    if pd.isnull(verbatim) or (len(verbatim)==0):
        return candidates, processed, classif

    # Match taxa by verbatim authorship

    candidates, ismore = _match_TaxaByAuthorship(verbatim, candidates)
    candidates = candidates[candidates['match']]

    if len(candidates)==0:

        # No match

        if ismore and (not verbatimauthorshiponly):

            # other information available but not used

            match_idx = None
            classif = ['ismore'] + [pd.NA]*len(wormscolumns)

        else:

            match_idx = None
            classif = ['nomatch'] + [pd.NA]*len(wormscolumns)

        processed = True

    elif len(candidates)==1:

        # Only one match

        match_idx = candidates.index[0]
        classif = ['singleVerbatimMatch'] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
        processed = True

    else:

        # More than one match

        if not all(candidates['authormatch_ratio'].isna()):

            # Keep the candidate that best matches the verbatim author names

            candidates = candidates[~pd.isnull(candidates['authormatch_ratio'])]
            max_authormatch_ratio = candidates['authormatch_ratio'].max()
            candidates = candidates[(max_authormatch_ratio - candidates['authormatch_ratio'])<=1e-2]

            if len(candidates)==1:

                # Only one match

                match_idx = candidates.index[0]
                classif = ['bestAuthorMatch'] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
                processed = True

        if (not processed) and (not all(candidates['datematch_diff'].isna())):

            # Keep the candidate that best matches:
            # - the verbatim author names, if any
            # - and the verbatim authorship date

            candidates = candidates[~pd.isnull(candidates['datematch_diff'])]
            min_datematch_diff = candidates['datematch_diff'].min()
            candidates = candidates[candidates['datematch_diff']==min_datematch_diff]

            if len(candidates)==1:

                # Only one match

                match_idx = candidates.index[0]
                classif = ['bestDateMatch'] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
                processed = True

        if (not processed) and (not all(candidates['sensu_conflict'].isna())):

            # Keep the candidate that best matches:
            # - the verbatim author names, if any
            # - the verbatim authorship date, if any
            # and with no "sensu" conflict
            # e.g. `verbatim`="(Slabber, 1769)"
            #      `candidate1`="(Slabber, 1769)"
            #      `candidate2`="(Slabber, 1769) sensu Holmes, 1905"
            #       the result should be `candidate1`

            candidates = candidates[~candidates['sensu_conflict']]

            if len(candidates)==1:

                # Only one match

                match_idx = candidates.index[0]
                classif = ['authorshipNoSensuConflict'] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
                processed = True

        return {"candidates": candidates, "processed": processed, "match_idx": match_idx, "classif": classif}


def _fuzzymatch_HigherRanks(ranks1, ranks2, levenshtein_tolerance=0.7):

    diffnan = (ranks1.isna()!=ranks2.isna()) # if both are null, it is considered a match
                                             # if only one is null, it is considered a mismatch

    match = []

    for c in range(ranks1.shape[0]): # candidate classification

        isnan=False
        Nnan=0
        Nmismatch=0
        match.append([])

        for r in range(ranks1.shape[1]): # rank

            r1=ranks1.loc[c,r]
            r2=ranks2.loc[c,r]

            if diffnan.loc[c,r]:
                isnan=True
                Nnan+=1

            elif (not pd.isnull(r1)) and (not pd.isnull(r2)):

                if (len(r1.split())!=1) or (len(r2.split())!=1): #À SUPPRIMER APRES DEBUG
                    raise Exception

                if Levenshtein.ratio(r1, r2)<levenshtein_tolerance:
                    Nmismatch+=1

        match[c].append(Nmismatch)
        match[c].append(Nnan)
        match[c].append(isnan)

    match = pd.DataFrame(match, columns=['Nmismatch','Nnan','isnan'])

    return match

def _exactmatch_HigherRanks(ranks1, ranks2):

    diff = (ranks1.fillna('')!=ranks2.fillna('')) # compute differences
    #isnan = (ranks1.isna() + ranks2.isna())
    isnan = (ranks1.isna()!=ranks2.isna()) # if both are null, it is considered a match
                                           # if only one is null, it is considered a mismatch

    match = pd.DataFrame(diff[~isnan].sum(axis=1).astype(int), columns=['Nmismatch'])

    match['Nnan'] = isnan.sum(axis=1) # number of NaNs
    match['isnan'] = isnan.any(axis=1)

    return match

def _match_TaxaByHigherRanks(ranks1, ranks2, fuzzy=True, fixed_allowedMismatch=False, auto_allowedMismatch=NaN2AllowedMismatch, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2):

    #print(ranks1)
    #print(ranks2)
    #print()

    ranks1 = ranks1.astype('string')
    ranks2 = ranks2.astype('string')

    # Difference between the two classifications

    if fuzzy:
        # Partial fuzzy matching
        match=_fuzzymatch_HigherRanks(ranks1, ranks2)

    else:
        # Partial exact matching
        match=_exactmatch_HigherRanks(ranks1, ranks2)

    # Number of mismatches allowed according to the number of NaNs

    allowedMismatchByNaN = pd.DataFrame.from_dict(auto_allowedMismatch, orient='index', columns=['max_mismatch'])
    if fixed_allowedMismatch:
        allowedMismatchByNaN.iloc[0,0]=fixed_allowedMismatch_withoutNaN
        allowedMismatchByNaN.iloc[1:-1,0]=fixed_allowedMismatch_withNaN
        allowedMismatchByNaN.iloc[-1,0]=-1

    # Full naive matching
    # naive, as it does not account for the level of non-matching ranks

    match.loc[:,'match'] = (match.loc[:,'Nmismatch'].values <= allowedMismatchByNaN.loc[match.loc[:,'Nnan'],'max_mismatch'].values)

    return match


def _match_TaxaByFullClassification(data_classif, worms_classif, check_ambiguity=True, verbatimcolumn=None, verbatimauthorshiponly=False, fuzzy=True, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False):

    #higherranks = list(data_classif.columns)
    higherranks = list(set(RANK_MAPPING.values()) - set([RANK_MAPPING['scientificname']]))
    wormscolumns = list(worms_classif.columns)
    colnames = ['classif_matchtype'] + wormscolumns
    add_ambiguitycol=check_ambiguity

    isambiguity=False
    isverbatim=(verbatimcolumn is not None)

    #print()
    #print('data_classif')
    #print(data_classif)
    if worms_classif['match_type'].isin(['nomatch']).any():

        # No match in WoRMS

        if len(worms_classif)>1: # something wrong
            raise NotImplementedError("More than one candidate, but one is a 'nomatch'")

        else:
            match_idx = None
            classif = pd.DataFrame([['nomatch'] + [pd.NA]*len(wormscolumns)], columns=colnames)
            processed = True
            check_ambiguity = False

    elif worms_classif['match_type'].isin(['match_quarantine','match_deleted']).all():

        # No match in WoRMS

        match_idx = None
        classif = pd.DataFrame([['nomatch'] + [pd.NA]*len(wormscolumns)], columns=colnames)
        processed = True
        check_ambiguity = False

    else:

        # WoRMS match

        params = {'fuzzy':fuzzy,
                  'fixed_allowedMismatch':fixed_allowedMismatch,
                  'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
                  'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN}

        processed = False

        # STEP N°1: Do the higher ranks match?

        match = _match_TaxaByHigherRanks(worms_classif.loc[:,higherranks], data_classif.loc[:,higherranks], **params)

        # Worst-case strategy (risk aversion):
        # N certain non-matches are preferred to (N+1) potential non-matches, and therefore also to (N+1) potential matches
        # i.e to (N+1) missing values
        # Best classification:
        # classification with the lowest `mismatch_level` and the lowest number of mismatches within that level (`Nmismatch`)

        match['mismatch_level'] = match['Nmismatch'] + match['Nnan']

        if any(match['match']):

            # Higher ranks match

            if match['match'].sum()==1:

                # Only one full match

                match_idx = np.where(match['match'])[0][0]
                classif = pd.DataFrame([['singleMatch'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                processed = True
                check_ambiguity = False

            else:

                # More than one full match

                match = match[match['match']]

                match_index = match.index.tolist()
                candidates = worms_classif.loc[match_index,:]


                # STEP N°2: Do all candidates refer to the same accepted species?


                unique_aphiaID = candidates['valid_AphiaID'].unique()
                if len(unique_aphiaID)==1:

                    # By default, keep the first one
                    # all candidates refer to the same accepted species

                    match_idx = match_index[0]
                    classif = pd.DataFrame([['singleAphiaID'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                    processed = True
                    check_ambiguity = False


                # INTERMEDIATE STEP: Reorder lines based on species name match for subsequent processing steps
                # see STEP N°3 _match_TaxaByAuthorship() and STEP N°5 below


                unique_wormsspecies = candidates[RANK_MAPPING['scientificname']].unique()

                if (not processed) and len(unique_wormsspecies)>1:

                    # More than one species name among WoRMS candidates

                    match[['speciesratio','Nspeciesmatch']]=pd.NA
                    match['speciesratio']=match['speciesratio'].astype('Float64')
                    match['Nspeciesmatch']=match['Nspeciesmatch'].astype('Int64')

                    ## Compute the Levenstein ratio between each unique WoRMS species name and the name of the species being processed

                    indexBywormsspecies = candidates[RANK_MAPPING['scientificname']].groupby([RANK_MAPPING['scientificname']]).indices
                    dataspecies = data_classif.loc[0,RANK_MAPPING['scientificname']]
                    for wormsspecies in unique_wormsspecies:
                        match.loc[indexBywormsspecies[wormsspecies],['speciesratio','Nspeciesmatch']] = elementwise_LevensteinRatio(wormsspecies, dataspecies)

                    ## Best species name
                    # i.e  species name with the highest number of components and the best Levenstein ratio
                    # e.g. species: "Haliclona (Rhizoniera) viscosa" (may be misspelled)
                    #      worms: "Haliclona (Rhizoniera) viscosa" & "Haliclona viscosa"
                    #      the result should be "Haliclona (Rhizoniera) viscosa",
                    #      even if the Levenstein ratio is lower due to spelling mistakes

                    bestspecies = match[(match['speciesratio']>=0.8)] # threshold of 0.8 to minimize false matches
                    bestspecies = bestspecies.sort_values(by=['Nspeciesmatch','speciesratio'], ascending=False)

                    match = pd.concat([bestspecies, match[(match['speciesratio']<0.8)]], axis=0)

                match_index = match.index.tolist()
                candidates = worms_classif.loc[match_index,:]


                # STEP N°3: Is it possible to decide among candidates based on the information in the raw data?


                if (not processed) and isverbatim:

                    verbatim = data_classif.loc[0,verbatimcolumn]

                    if not pd.isnull(verbatim):

                        results = _match_TaxaByVerbatim(verbatim, candidates, wormscolumns, verbatimauthorshiponly=verbatimauthorshiponly)

                        candidates = results['candidates']
                        match_idx = results['match_idx']
                        classif = results['classif']
                        processed = results['processed']

                    if processed:

                        # Keep the candidate whose authorship best matches the verbatim authorship, if any

                        classif = pd.DataFrame([classif], columns=colnames)

                        if check_ambiguity:

                            if match_idx is None:
                                check_ambiguity=False
                            else:
                                candidates = worms_classif.loc[match_index,:]


                # STEP N°4: Is one of the candidates the best match for higher taxonomic ranks?


                if (not processed) or (check_ambiguity and (not isambiguity)):

                    match_temp = match.loc[candidates.index,:]
                    match_temp = match_temp[(match_temp['mismatch_level']==match_temp['mismatch_level'].min())]
                    match_temp = match_temp[(match_temp['Nmismatch']==match_temp['Nmismatch'].min())]
                    candidates = candidates.loc[match_temp.index,:]

                    if check_ambiguity and (not isambiguity):

                         # Are the best candidates based on raw data also
                         # the best candidates based on higher rank matches?

                        if processed:

                            # i.e processed in the previous step

                            isambiguity=(match_idx not in candidates.index)

                        if (not processed) and isverbatim:

                            # i.e not processed in the previous step

                            match_bestclassif = match.copy()
                            match_bestclassif = match_bestclassif[(match_bestclassif['mismatch_level']==match_bestclassif['mismatch_level'].min())]
                            match_bestclassif = match_bestclassif[(match_bestclassif['Nmismatch']==match_bestclassif['Nmismatch'].min())]

                            index_intersection = set(match_bestclassif.index).intersection(candidates.index)
                            isambiguity=(len(index_intersection)!=len(candidates))

                            if len(index_intersection)<len(candidates): #SUPPRIMER DEBUG
                                print('species:',unique_wormsspecies)
                                print('match_bestclassif')
                                print(match_bestclassif)
                                print('candidate')
                                print(candidat)
                                raise Exception('STEP N°4')

                    if (not processed) and (len(candidates)==1):

                        # Only one match

                        match_idx = candidates.index[0]
                        classif = pd.DataFrame([['bestClassification'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                        processed = True


                # STEP N°5: Does one of the candidates best match the species name?


                if (not processed) or (check_ambiguity and (not isambiguity)):

                    if processed:

                        isambiguity=(match_idx!=match_index[0])

                    else:

                        match_temp = match.loc[candidates.index,:]
                        match_temp = match_temp[(match_temp['Nspeciesmatch']==match_temp['Nspeciesmatch'].max())]
                        if len(match_temp)>1:
                            max_speciesratio = match_temp['speciesratio'].max() # no NaN
                            match_temp = match_temp[(max_speciesratio - match_temp['speciesratio'])<1e-2]
                        candidates = candidates.loc[match_temp.index,:]

                        if check_ambiguity and (not isambiguity):
                            isambiguity=(match_index[0] not in candidates.index)

                        if (len(candidates)==1):

                            # Only one match

                            match_idx = candidates.index[0]
                            classif = pd.DataFrame([['bestSpeciesName'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                            processed = True


                # STEP N°6: Do all candidates have the same classification and "accepted" status?


                if (not processed):

                    isidentical_exclauthspe = candidates[higherranks + ['status']].fillna('MISSING').drop_duplicates(inplace=False)
                    condition1 = (len(isidentical_exclauthspe)==1)
                    condition2 = (isidentical_exclauthspe.loc[0,'status']=='accepted')

                    if condition1 and condition2:

                        if len(candidates['valid_AphiaID'].unique())!=1: #À SUPPRIMER APRES DEBUG
                            raise Exception

                        # By default, keep the first one
                        # all candidates share the same classification and “accepted” status but differ only in authority,
                        # suggesting they likely refer to the same species

                        match_idx = candidates.index[0]
                        classif = pd.DataFrame([['allAccepted'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                        processed = True


                # STEP N°7: Uncertain


                if (not processed):

                    # Decision not possible, review manually or delete

                    match_idx = None
                    classif = pd.DataFrame([['undecided'] + [pd.NA]*len(wormscolumns)], columns=colnames)
                    processed = True

        else:

            check_ambiguity = False

            # No match for higher ranks

            candidates = worms_classif[worms_classif['match_type'].isin(['exact','exact_subgenus','phonetic','near_1','near_2','near_3'])]

            data_kingdom = data_classif.loc[0,RANK_MAPPING['kingdom']]
            if fuzzy:
                match = [(Levenshtein.ratio(kingdom, data_kingdom)>=0.7) for _,kingdom in enumerate(candidates[RANK_MAPPING['kingdom']])]
            else:
                match = (candidates[RANK_MAPPING['kingdom']]==data_kingdom)
            candidates = candidates[match]

            if len(candidates)!=0:

                if (verbatimcolumn is not None):

                    # If species match is high, use verbatim authorship
                    # because classification may have changed

                    verbatim = data_classif.loc[0,verbatimcolumn]

                    if not pd.isnull(verbatim):

                        results = _match_TaxaByVerbatim(verbatim, candidates, wormscolumns, verbatimauthorshiponly=verbatimauthorshiponly)

                        candidates = results['candidates']
                        match_idx = results['match_idx']
                        classif = results['classif']
                        processed = results['processed']

                    if processed:

                        # Keep the candidate whose authorship best matches the verbatim authorship, if any

                        classif = pd.DataFrame([classif], columns=colnames)
                        classif['classif_matchtype'] = classif['classif_matchtype'] + '_nomatch'

                if (not processed):

                    # Check by hand or delete

                    match_idx = None
                    classif = pd.DataFrame([['suspicious'] + [pd.NA]*len(wormscolumns)], columns=colnames)
                    processed = True

            else:

                match_idx = None
                classif = pd.DataFrame([['nomatch'] + [pd.NA]*len(wormscolumns)], columns=colnames)
                processed = True


    # Remove fossils

    if not keep_fossil:

        worms_classif['isExtinct']=worms_classif['isExtinct'].astype('Int64')
        indexes = worms_classif[worms_classif['isExtinct']==1].index

        if match_idx in indexes:

             classif = pd.DataFrame([['nomatch'] + [pd.NA]*len(wormscolumns)], columns=colnames)
             print(data_classif)
             print(worms_classif)

    if add_ambiguitycol:

        if check_ambiguity:
            classif['isambiguity']=isambiguity
        else:
            classif['isambiguity']=pd.NA

    return classif

def _display_progress(classification, idx):

    classif = classification.iloc[:idx,:]

    nclassification = len(classification)
    Nnomatch = len(classif[classif['classif_matchtype']=='nomatch'])
    Nmatch = len(classif) - Nnomatch
    percentage = np.round((idx+1)/nclassification*100,2)

    print(f'            Processing | {idx+1}/{nclassification} classifications done ({percentage}%): no_match={Nnomatch}, match={Nmatch}')

    return True

def _call_create_WoRMSrecognizedfilter(species, identification_level='species', min_length=3, doublecheck=True, resume=True, store=True, outputpath='./', outputfile='worms_matchfilter.txt', outputfile_suffix='isinworms', overwrite=False, parallel=False, max_attempt=3, resume_parallel=True, store_parallel=True, overwrite_parallel=False):

    params_func = {
                   'wormscall':WORMSCALL,
                   'identification_level':identification_level,
                   'min_length':min_length,
                   'doublecheck':doublecheck,
                   'resume':resume
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

    if store:

        outputfile_split = outputfile.split('.')

        if ('isinworms' not in outputfile_suffix):
            outputfile_suffix = 'isinworms_' + outputfile_suffix

        params_store['outputfile'] = outputfile_split[0] + '_' + outputfile_suffix + '.' + outputfile_split[1]

    matchfilter = cwf.create_WoRMSrecognizedfilter(species, **params_func, **params_store, **params_parallel)

    return matchfilter

def _apply_matchfilter(classification, matchfilter=None, check_ambiguity=True, fuzzy=True, verbatimcolumn=None, verbatimauthorshiponly=False, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False, store=True, outputpath='./', overwrite=False, parallel=False, **params_dict):

    # Parameters

    params_store = {
                   'outputpath':outputpath,
                   'store':store,
                   'store_parallel':store,
                   'overwrite':overwrite,
                   'overwrite_parallel':overwrite
                   }

    if 'store_parallel' in params_dict.keys():
        if parallel and (store!=params_dict['store_parallel']):
            raise ValueError(f'parallel={parallel} and store={store} but store_parallel={params_dict["store_parallel"]}')
        params_store['store_parallel'] = params_dict.pop('store_parallel')

    if 'overwrite_parallel' in params_dict.keys():
        if parallel and (overwrite!=params_dict['overwrite_parallel']):
            raise ValueError(f'parallel={parallel} and overwrite={overwrite} but overwrite_parallel={params_dict["overwrite_parallel"]}')
        params_store['overwrite_parallel'] = params_dict.pop('overwrite_parallel')


#    if keep_fossil and ('isExtinct' in WORMSCALL.keys()):
#        # do not delete fossil occurrences
#        del WORMS_MAPPING[WORMSCALL['isExtinct']]

    # Match taxa to a WoRMS classification, based on:
    # - the taxon name
    # - higher ranks
    # - and, if available, authorship

    nclassification = len(classification)
    print(f'            * WoRMS filtering (recognized marine taxa) | {nclassification} unique classifications')

#    wormscolumns = list(WORMS_MAPPING.keys())
#    wormscolumns = WORMSCALL

    ## Match species name

    unique_species = classification[RANK_MAPPING['scientificname']].unique().tolist()

    if matchfilter is None:

        # Create WoRMS match filter

        print(f'            ** isinworms | createwormsfilter')

        matchfilter = _call_create_WoRMSrecognizedfilter(unique_species, wormscall=WORMSCALL, parallel=parallel, **params_store, **params_dict)

    else:

        # Ensure all columns required for filtering are included in the WoRMS match filter

        check_columns = ['group'] + WORMSCALL
        print(matchfilter.columns) #DEBUG
        print(check_columns)
        if (len(check_columns)>len(matchfilter.columns)) or any(col not in matchfilter.columns for col in check_columns):
           raise KeyError(f'Filter column names must be: {check_columns}')

        # Complete the WoRMS match filter if necessary

        species2process = _resume(matchfilter, unique_species, issciname=True)
        if len(species2process)!=0:

            print(f'            ** isinworms | createwormsfilter')
            print(f'            UPDATE | {len(species2process)}/{len(unique_species)} ({np.round(len(species2process)/len(unique_species)*100,2)}%) taxa remaining to be processed')

            params_dict['outputfile_suffix']='additional'
            params_store['overwrite']=False
            params_store['overwrite_parallel']=False

            addmatchfilter = _call_create_WoRMSrecognizedfilter(species2process, wormscall=WORMSCALL, parallel=parallel, **params_store, **params_dict)

            matchfilter = pd.concat([matchfilter,addmatchfilter], axis=0)

    ## Match higher ranks & authorship

    matchfilter = matchfilter.rename(columns=RANK_MAPPING)
    filter = matchfilter.groupby(['group'])

    params = {
              'check_ambiguity':check_ambiguity,
              'fuzzy':fuzzy,
              'fixed_allowedMismatch':fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN,
              'verbatimauthorshiponly':verbatimauthorshiponly,
              'verbatimcolumn':verbatimcolumn,
              'keep_fossil':keep_fossil
             }

    if verbatimcolumn is None:
        # no authorship
        datacolumns = list(RANK_MAPPING.values())
    else:
        # use authorship, if any
        datacolumns = list(RANK_MAPPING.values()) + [verbatimcolumn]
    print("check datacolumn:")
    print(datacolumn)
    print(classification.columns)
    colnames = COLNAMES + ['classif_matchtype']
    if check_ambiguity:
        colnames+=['isambiguity']

    coldiff = list(set(colnames) - set(RANK_MAPPING.values())) #set(classification.columns))
    print("coldiff:", coldiff)
    print("check coldiff:", set(WORMSCALL) - set(RANK_MAPPING.keys()))
    classification[coldiff]=pd.NA

    for idx in range(nclassification):

        spe = tuple([classification.loc[idx,RANK_MAPPING['scientificname']]])

        worms_classif = filter.get_group(spe).reset_index(drop=True)
        data_classif = pd.DataFrame([classification.loc[idx,datacolumns].tolist()]*len(worms_classif),columns=datacolumns).reset_index(drop=True)
        #print(worms_classif)
        #print(data_classif)

        classif = _match_TaxaByFullClassification(data_classif, worms_classif, **params)

        if len(classif)!=1: #DEBUG
            raise Exception

        if classif.loc[0,'classif_matchtype'] in ['nomatch', 'undecided', 'suspicious', 'ismore', 'ismore_nomatch']:

            # Keep original values

            classification.loc[idx,'classif_matchtype'] = classif.loc[0,'classif_matchtype']
            #classification.loc[idx,new_columns] = pd.NA #[WORMSCALL['match_type'],WORMSCALL['status'],WORMSCALL['valid_AphiaID']]

        else:

            # Keep WoRMS values

            classification.loc[idx,colnames] = classif.loc[0,colnames] #.values.flatten() #DEBUG : après, mettre .loc[0,...].tolist()


        if (((idx+1)%1000)==0) or (idx==(nclassification-1)):

            # Display code progress

            _display_progress(classification, idx)

    # Delete taxa that do not match any WoRMS classification

    classification = classification[classification['classif_matchtype']!='nomatch']

    print(f'            Done | before: {nclassification}, after: {len(classification)} classifications')

    return classification


def _call_create_WoRMSacceptedfilter(valid_aphiaID, species_only=True, store=True, outputpath='./', outputfile='worms_acceptedfilter.txt', outputfile_suffix='isinworms', overwrite=False, resume=True, parallel=False, max_attempt=3, resume_parallel=True, store_parallel=True, overwrite_parallel=False):

    # Parameters

    params_func = {
                   'wormscall':WORMSCALL,
                   'species_only':species_only,
                   'resume':resume
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

    if store:

        outputfile_split = outputfile.split('.')

        if ('isinworms' not in outputfile_suffix):
            outputfile_suffix = 'isinworms_' + outputfile_suffix

        params_store['outputfile'] = outputfile_split[0] + '_' + outputfile_suffix + '.' + outputfile_split[1]

    matchfilter = cwf.create_WoRMSacceptedfilter(valid_aphiaID, **params_func, **params_store, **params_parallel)

    return matchfilter

def _apply_acceptedfilter(classification, acceptedfilter=None, store=True, outputpath='./', overwrite=False, parallel=False, **params_dict):

    if len(classification)==0:
        return classification

    # Parameters

    params_store = {
                    'outputpath':outputpath,
                    'store':store,
                    'store_parallel':store,
                    'overwrite':overwrite,
                    'overwrite_parallel':overwrite
                   }

    if 'store_parallel' in params_dict.keys():
        if parallel and (store!=params_dict['store_parallel']):
            raise ValueError(f'parallel={parallel} and store={store} but store_parallel={params_dict["store_parallel"]}')
        params_store['store_parallel'] = params_dict.pop('store_parallel')

    if 'overwrite_parallel' in params_dict.keys():
        if parallel and (overwrite!=params_dict['overwrite_parallel']):
            raise ValueError(f'parallel={parallel} and overwrite={overwrite} but overwrite_parallel={params_dict["overwrite_parallel"]}')
        params_store['overwrite_parallel'] = params_dict.pop('overwrite_parallel')

    classification['valid_AphiaID']=classification['valid_AphiaID'].astype('Float64').astype('Int64')
    if acceptedfilter is not None:
        acceptedfilter['group']=acceptedfilter['group'].astype('Float64').astype('Int64')

    # Identify unaccepted taxa

    unaccepted_idx = classification[(~classification['status'].isin(['accepted','deleted'])) & (~pd.isnull(classification['valid_AphiaID']))].index
    nunaccepted = len(unaccepted_idx)

    # Map unaccepted taxa to their accepted classification

    if len(unaccepted_idx)!=0:

        print(f'            * WoRMS filtering (accepted taxa) | {nunaccepted} occurrences of unaccepted taxa')

        unique_aphiaID = classification.loc[unaccepted_idx,'valid_AphiaID'].unique().tolist()

        if acceptedfilter is None:

            # Create WoRMS accepted match filter

            print(f'            ** isinworms | createwormsfilter')

            acceptedfilter = _call_create_WoRMSacceptedfilter(unique_aphiaID, wormscall=WORMSCALL, parallel=parallel, **params_store, **params_dict)

        else:

            # Ensure all columns required for matching are present in the WoRMS accepted match filter

#            check_columns = ['group'] + list(WORMS_MAPPING.keys())
            check_columns = ['group'] + WORMSCALL
            if (len(check_columns)>len(acceptedfilter.columns)) or any(col not in acceptedfilter.columns for col in check_columns):
                raise KeyError(f'Filter column names must be: {check_columns}')

            # Complete the WoRMS accepted match filter if necessary

            aphiaID2process = _resume(acceptedfilter, unique_aphiaID, issciname=False)
            if len(aphiaID2process)!=0:

                print(f'            ** isinworms | createwormsfilter')
                print(f'            UPDATE | {len(aphiaID2process)}/{len(unique_aphiaID)} ({np.round(len(aphiaID2process)/len(unique_aphiaID)*100,2)}%) unaccepted taxa remaining to be processed')

                params_dict['outputfile_suffix']='additional'
                params_store['overwrite']=False
                params_store['overwrite_parallel']=False

                addacceptedfilter = _call_create_WoRMSacceptedfilter(aphiaID2process, wormscall=WORMSCALL, parallel=parallel, **params_store, **params_dict)

                acceptedfilter = pd.concat([acceptedfilter,addacceptedfilter], axis=0)

        if len(acceptedfilter['group'].unique()) != len(acceptedfilter): #DEBUG
            raise Exception(f'The filter of accepted classifications must not contain duplicates for the `valid_aphiaID` column.')

        # Match `valid_aphiaID`

        acceptedfilter = acceptedfilter.rename(columns=RANK_MAPPING)
        filter = acceptedfilter.set_index(['group'])
        filter = filter.loc[classification.loc[unaccepted_idx,'valid_AphiaID'].values,:].reset_index()

        classification.loc[unaccepted_idx, COLNAMES] = filter[COLNAMES].values

    return classification


def clean_taxonomy(classification, matchfilter=None, acceptedfilter=None, check_ambiguity=True, fuzzy=True, verbatimcolumn=None, verbatimauthorshiponly=False, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False, identification_level='species', min_length=3, doublecheck=True, store=True, outputpath='./', resume=True, overwrite=False, parallel=False, max_attempt=3, store_parallel=True, overwrite_parallel=False, resume_parallel=True):

    # Parameters

    params_store = {
                    'outputpath':outputpath,
                    'store':store,
                    'overwrite':overwrite,
                   }

    params_parallel = {
                       'parallel':parallel,
                       'max_attempt':max_attempt,
                       'resume_parallel':resume_parallel,
                       'store_parallel':store_parallel,
                       'overwrite_parallel':overwrite_parallel
                      }

    params_recognized = {
                         'identification_level':identification_level,
                         'min_length':min_length,
                         'doublecheck':doublecheck,
                         'resume':resume
                        }

    params_accepted = {
                       'species_only':(identification_level=='species'),
                       'resume':resume
                      }

    # Match WoRMS

    params = {
              'matchfilter':matchfilter,
              'check_ambiguity':check_ambiguity,
              'fuzzy':fuzzy,
              'fixed_allowedMismatch':fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN,
              'verbatimauthorshiponly':verbatimauthorshiponly,
              'verbatimcolumn':verbatimcolumn,
              'keep_fossil':keep_fossil,
             }

    classification = _apply_matchfilter(classification, **params, **params_store, **params_parallel, **params_recognized)

    # Relaunch WoRMS matching for classifications tagged "ismore"

    ismore_index = classification[classification['classif_matchtype'].str.contains('ismore')].index.tolist()
    if (len(ismore_index)!=0) and (verbatimcolumn is not None):

        if verbatimauthorshiponly: #À SUPPRIMER APRES DEBUG
            raise Exception

        params['matchfilter']=None
        params['outputfile_suffix']='ismore'

#        speciesrank = RANK['species']
        speciesrank = RANK_MAPPING['scientificname']
#        WORMS_MAPPING[verbatimcolumn]=WORMS_MAPPING.pop(RANK['species']) # ='scientificname'
        RANK_MAPPING['scientificname'] = verbatimcolumn
#        WORMSCALL['scientificname']=verbatimcolumn
#        RANK['species'] = verbatimcolumn
        COLNAME[COLNAME.index(speciesrank)] = verbatimcolumn

        temp = _apply_matchfilter(classification.loc[ismore_index,:], **params, **params_store, **params_parallel, **params_recognized)
        temp = temp.rename(columns={verbatimcolumn:speciesrank})
        classification.loc[ismore_index,classification.columns] = temp.loc[ismore_index,classification.columns] # specify indexes and columns to verify that the code performed as intended

        #WORMS_MAPPING[speciesrank]=WORMS_MAPPING.pop(verbatimcolumn)
        #WORMSCALL['scientificname']=speciesrank
        #RANK['species'] = speciesrank
        RANK_MAPPING['scientificname'] = speciesrank
        COLNAME[COLNAME.index(verbatim)] = speciesrank

    debug = classification[classification['classif_matchtype'].str.contains('ismore')] #À SUPPRIMER APRES DEBUG
    if len(debug)!=0:
       print(len(debug))
       print(debug[RANK_MAPPING['scientificname']].tolist())
       raise Exception

    # Match accepted WoRMS

    params = {
              'acceptedfilter':acceptedfilter,
             }

    classification = _apply_acceptedfilter(classification, **params, **params_store, **params_parallel, **params_accepted)

    return classification


def drop(df, drop_conditions):

    if len(drop_conditions)!=0:

        print(f'            * Final filtering | Drop conditions')

        if 'identification_level' in drop_conditions.keys():
            dropranks=subsetranks.apply(drop_conditions['identification_level'], lower=False, strict=True)
            drop_conditions['rank']=dropranks
            del drop_conditions['identification_level']

        df = dropvalues.apply(df, **drop_conditions)

    else:
        print(f'            * Final filtering | No drop conditions')

    return df

def apply(df, *ignored_args, wormscall=None, rank_mapping=None, worms_dtypes=None, matchfilter=None, acceptedfilter=None, check_ambiguity=True, fuzzy=True, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, verbatimcolumn=None, verbatimauthorshiponly=False, keep_fossil=False, identification_level='species', min_length=3, doublecheck=True, resume=True, store=True, overwrite=True, outputpath='./', outputfile='', parallel=True, max_attempt=3, store_parallel=True, overwrite_parallel=False, resume_parallel=True, drop_conditions=None):

    Nobs = len(df)

    # Parameters

    ## Global variables

    global WORMSCALL, WORMS_DTYPES

    if wormscall is not None:
        WORMSCALL=wormscall

    if rank_mapping is not None:
        RANK_MAPPING=rank_mapping

    if len(set(RANK_MAPPING.values) - set(df.columns))!=0:
        raise Exception(f'`RANK_MAPPING` values must be `df` columns')

#        WORMS_MAPPING = {v:k for k,v in wormscall.items()}

#    if set(WORMS_MAPPING.values())!=set(WORMSCALL.keys()):
#        raise Exception(f'`WORMSCALL` differs from `WORMS_MAPPING`')

    wormsranks = ['scientificname','genus','family','order','cls','phylum','kingdom']

#    rankkeys = ['species','genus','family','order','class','phylum','kingdom']
#    if len(set(RANK.keys()).symmetric_difference(rankkeys))!=0:
#        raise Exception(f'`RANK` keys should be {rankkeys}')
    if len(set(RANK_MAPPING.keys()).symmetric_difference(wormsranks))!=0:
        raise Exception(f'`RANK_MAPPING` keys should be {wormsranks}')

#    missing_keys = set(wormsranks + ['match_type','status','valid_AphiaID', 'rank']) - set(WORMSCALL.keys())
    missing_keys = set(wormsranks + ['match_type','status','valid_AphiaID', 'rank']) - set(WORMSCALL)
    if len(missing_keys)!=0:
        raise Exception(f'{missing_keys} WoRMS keys are missing in `WORMSCALL`')

    if (wormscall is not None) or (rank_mapping is not None):
        COLNAMES = list(set(list(set(WORMSCALL) - set(RANK_MAPPING.keys())) + list(RANK_MAPPING.values())))

#    if set(RANK.values())!=set(itemgetter(*wormsranks)(WORMSCALL)):
#        for i in range(len(wormsranks)):
#            RANK[rankkeys[i]] = WORMSCALL[wormsranks[i]]
        #RANK = {RANK[rankkeys[i]]:WORMSCALL[wormsranks[i]] for i in range(len(wormsranks))}
#        print(f'            INFO | `RANK` values : {RANK}')

#    wormscolumns = list(set(WORMS_MAPPING.keys()) - set(rankcolumns))

    if worms_dtypes is not None:
        WORMS_DTYPES=worms_dtypes

#    delkeys = list(set(WORMS_DTYPES.keys()) - set(WORMS_MAPPING.keys()))
    delkeys = list(set(WORMS_DTYPES.keys()) - set(WORMSCALL))
    for key in delkeys:
        del WORMS_DTYPES[key]

    missing_dtypes = set(WORMSCALL) - set(WORMS_DTYPES.keys())
    if len(missing_dtypes)!=0:
        print(f'            INFO | No dtype specified for: {list(missing_dtypes)}')

    ## Arguments

    if parallel and (store!=store_parallel):
        raise ValueError(f'parallel={parallel} and store={store} but store_parallel={store_parallel}')

    if parallel and (overwrite!=overwrite_parallel):
        raise ValueError(f'parallel={parallel} and overwrite={overwrite} but overwrite_parallel={overwrite_parallel}')

#    if (not keep_fossil) and ('isExtinct' not in WORMSCALL.keys()):
    if (not keep_fossil) and ('isExtinct' not in WORMSCALL):
       raise Exception(f"`keep_fossil`={keep_fossil} but 'isExtinct' not in `WORMSCALL`")

    if keep_fossil and ('isExtinct' in WORMSCALL):
        # do not delete fossil occurrences
        del WORMSCALL[WORMSCALL.index('isExtinct')]

    params = {
              'matchfilter':matchfilter,
              'acceptedfilter':acceptedfilter,
              'check_ambiguity':check_ambiguity,
              'fuzzy':fuzzy,
              'fixed_allowedMismatch':fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN,
              'verbatimauthorshiponly':verbatimauthorshiponly,
              'verbatimcolumn':verbatimcolumn,
              'keep_fossil':keep_fossil,
              'identification_level':identification_level,
              'min_length':min_length,
              'doublecheck':doublecheck,
              'resume':resume
             }


    params_store = {
                    'outputpath':outputpath,
                    'store':store,
                    'overwrite':overwrite,
                   }


    params_parallel = {
                       'parallel':parallel,
                       'max_attempt':max_attempt,
                       'resume_parallel':resume_parallel,
                       'store_parallel':store_parallel,
                       'overwrite_parallel':overwrite_parallel
                      }

    rankcolumns = list(RANK_MAPPING.values())
    print('rankcolumns:',rankcolumns) #DEBUG
    wormscolumns = list(set(WORMSCALL) - set(RANK_MAPPING.keys()))
    print('wormscolumns',wormscolumns) #DEBUG

    if overwrite:
        print(f'            WARNING | {rankcolumns} columns already exists and will be overwritten')
        rankcolumns_mapping = {rank : rank for rank in rankcolumns}
    else:
        rankcolumns_mapping = {rank : rank + '_processedby_isinworms' for rank in rankcolumns}
    print('rankmap:',rankcolumns_mapping) #DEBUG

    if verbatimcolumn is not None:

        # use authorship, if any

#        if verbatimauthorshiponly & ('authority' not in WORMSCALL.keys()):
        if verbatimauthorshiponly & ('authority' not in WORMSCALL):
            raise Exception(f"`verbatimauthorshiponly`={verbatimauthorshiponly} but 'authority' not in `WORMSCALL`")

        columns = rankcolumns + [verbatimcolumn]

    else:

        # no authorship

        columns = rankcolumns
    print('columns:',columns) #DEBUG

    if Nobs==0:

        # no observations

        colnames = list(set(df.columns.tolist() + list(rankcolumns_mapping.values()) + ['classif_matchtype'] + wormscolumns))
        # METTRE worms DEVANT WORMS COLUMNS!!
        if check_ambiguity:
            colnames+=['isambiguity']
        df = df.reindex(colnames, axis='columns')

        return df

    # Convert all missing values in `columns` columns to pd.NA

    df = standardizenan.apply(df, key=columns)

    # Pre-process the raw scientific names
    # to avoid quotation mark problems with pandas

    tempspecies = rankcolumns_mapping[RANK_MAPPING['scientificname']]
    print('unique spe:', len(df[RANK_MAPPING['scientificname']].unique())) #DEBUG
    df[tempspecies] = cwf.preprocess_quotationMarks(df[RANK_MAPPING['scientificname']].tolist(), unique_values=False)
    speidx = columns.index(RANK_MAPPING['scientificname'])
    columns[speidx] = tempspecies
    print('columns:',columns) # DEBUG
    print('unique spe:', len(df[tempspecies].unique())) #DEBUG
    # Get unique classifications

    dfByClassification = df.loc[~pd.isnull(df[tempspecies]), columns].fillna('_MISSING_').groupby(columns, dropna=False) #get_group() doesn't work with NaN
    columns[speidx]=RANK_MAPPING['scientificname']
    print('columns:',columns)
    taxonomy = pd.DataFrame(list(dfByClassification.groups.keys()), columns=columns)
    print(taxonomy)
    # Get WoRMS-accepted classifications associated with these classifications, if any

    classification = clean_taxonomy(taxonomy.replace('_MISSING_',pd.NA), **params, **params_store, **params_parallel)

    print('classification len:', len(classification)) #À SUPPRIMER APRES DEBUG (il peut y en avaoir moins dans classification car suppression des nomatch
    print('taxonomy len:', len(taxonomy))
    idx_test=classification.index[10]
    print('check:', taxonomy.loc[idx_test,:])
    print('check:', classification.loc[idx_test,:])

    # Standardize taxonomy

    ## Prepare the dataframe

    df['classif_matchtype'] = 'nomatch'

    if check_ambiguity:
        df['isambiguity'] = pd.NA
        df['isambiguity'] = df['isambiguity'].astype('boolean')

    df[wormscolumns] = pd.NA
    df[wormscolumns] = df[wormscolumns].astype(WORMS_DTYPES)

    rankcolumns = list(rankcolumns_mapping.values())
    if not overwrite:
        df[rankcolumns]=pd.NA
    df[rankcolumns] = df[rankcolumns].astype('string')

    ## Apply the standardized taxonomy

    print(f'            * Standardization via WoRMS | Full dataset')

    classification_indexes = classification.index.tolist()
    classification_columns = classification.columns.tolist()

    target_columns = []
    for column in classification_columns:
        try:
            target_columns.append(rankcolumns_mapping[column])
        except KeyError:
            target_columns.append(column)

    print('target_columns',target_columns) #À SUPPRIMER APRES DEBUG

    for idx in classification_indexes:

        group = tuple(taxonomy.loc[idx,:].values)
        indexes = dfByClassification.get_group(group).index #ATTENTION PRE-PROCESSING !
        df.loc[indexes, target_columns] = classification.loc[idx, classification_columns].values

    df['rank']=df['rank'].str.lower()

    # Delete matches deemed insufficient

    if drop_conditions is not None:
        df=drop(df, drop_conditions)

    df.rename(columns={'valid_AphiaID':'worms_aphiaID'}, inplace=True)
    # AJOUTER WROMS DEVANT TOUTES LES CLÉS WORMS
    print(f'            Done | before : {Nobs}, after : {len(df)} observations')

    # Store

    if store:

        if len(args.outputfile)==0:
            outputfile = os.path.join(outputpath,'data_processedby_isinworms.txt')

        if overwrite and os.path.isfile(outputfile):
            print(f'            WARNING | {outputfile} already exists and will be overwritten')

        cwf.write_dataframe2txtfile(df, outputfile, init=overwrite, verbose=True)

    return df


#À SUPPRIMER APRES DEBUG

def test():

    df = pd.read_csv('/data/smartbiodiv/eberhocoi/useverbatim.csv',sep='\t')
    dfgb = df.groupby(['verbatim'])
    for key in dfgb.groups.keys():
        verbatim = key
        candidates = dfgb.get_group((key,))[['species','authorship','status']]

        print('verbatim :', verbatim)
        print('candidates')
        print(candidates)
        print(_match_TaxaByAuthorship(verbatim, candidates))
        print()
        print()

if __name__ == "__main__":

    #test()

    parser = argparse.ArgumentParser(description='Create WoRMS filters')
    parser.add_argument('data_txtfile', type=str, help='path to the tab-separated file to be processed')
#    parser.add_argument('--wormscall', type=json.loads, help='dictionary containing the WoRMS variables to keep and the names under which to store them', default=json.dumps(WORMSCALL))
    parser.add_argument('--wormscall', nargs='*', type=str, help='list containing the WoRMS variables to keep', default=WORMSCALL)
    parser.add_argument('--worms_dtypes', type=json.loads, help='dictionary of the dtypes of WoRMS-specific columns', default=json.dumps(WORMS_DTYPES))
    parser.add_argument('--matchfilter_txtfile', type=str, help='path to the WoRMS match filter', default=None)
    parser.add_argument('--acceptedfilter_txtfile', type=str, help='path to the WoRMS accepted filter', default=None)
    parser.add_argument('--check_ambiguity', action=argparse.BooleanOptionalAction, help='check if a different order of the matching criteria would have led to a different result', default=True)
    parser.add_argument('--fuzzy', action=argparse.BooleanOptionalAction, help='fuzzy or exact matching on higher ranks', default=True)
    parser.add_argument('--fixed_allowedMismatch', action=argparse.BooleanOptionalAction, help='set a fixed number of allowed mismatches for higher ranks, regardless of missing values', default=False)
    parser.add_argument('--fixed_allowedMismatch_withNaN', type=int, help='number of allowed mismatches for higher ranks with missing values', default=1)
    parser.add_argument('--fixed_allowedMismatch_withoutNaN', type=int, help='number of allowed mismatches for higher ranks without missing values', default=2)
    parser.add_argument('--verbatimcolumn', type=str, help='column containing authorship information', default=None)
    parser.add_argument('--verbatimauthorshiponly', action=argparse.BooleanOptionalAction, help='`verbatimcolumn` contains only authorship information', default=False)
    parser.add_argument('--keep_fossil', action=argparse.BooleanOptionalAction, help='keep fossil taxa', default=False)
    parser.add_argument('--identification_level', type=str, help="should be 'best', 'species' or 'first'", default='species')
    parser.add_argument('--min_length', type=int, help='minimum length of the words comprising the scientific name', default=3)
    parser.add_argument('--doublecheck', action=argparse.BooleanOptionalAction, help='double-check or not three-word scientific names by querying only the first two words', default=True)
    parser.add_argument('--store', action=argparse.BooleanOptionalAction, help='whether to store the filters', default=True)
    parser.add_argument('--outputpath', type=str, help='path to folder where files will be stored', default='./')
    parser.add_argument('--outputfile', type=str, help='name of the output file', default='')
    parser.add_argument('--overwrite', action=argparse.BooleanOptionalAction, help='overwrite existing filters', default=False)
    parser.add_argument('--resume', action=argparse.BooleanOptionalAction, help='reuse existing filters and temporary files', default=True)
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='parallelize requests (maximum 2 CPUs)', default=False)
    parser.add_argument('--max_attempt', type=int, help='maximum number of retries in case of errors when running in parallelized mode', default=3)
    parser.add_argument('--store_parallel', action=argparse.BooleanOptionalAction, help='whether to store the filters in parallelized mode', default=True)
    parser.add_argument('--overwrite_parallel', action=argparse.BooleanOptionalAction, help='overwrite existing filters in parallelized mode', default=False)
    parser.add_argument('--resume_parallel', action=argparse.BooleanOptionalAction, help='reuse existing filters in parallelized mode', default=True)

    args = parser.parse_args()

    if len(args.outputfile)==0:
        outputfile = args.data_txtfile.split('.')[0].split('/')[-1]
        outputfile = outputfile + '_processedby_isinworms.txt'

    df = pd.read_csv(args.data_txtfile, sep='\t', low_memory=False)
    matchfilter = pd.read_csv(args.matchfilter_txtfile, sep='\t', low_memory=False)
    acceptedfilter = pd.read_csv(args.acceptedfilter_txtfile, sep='\t', low_memory=False)

    print_params = {
                    'data': args.data_txtfile,
                    'matchfilter': args.matchfilter_txtfile,
                    'acceptedfilter': args.acceptedfilter_txtfile
                   }

    params = {
              'wormscall': args.wormscall,
              'worms_dtypes': args.worms_dtypes,
              'check_ambiguity': args.check_ambiguity,
              'fuzzy': args.fuzzy,
              'fixed_allowedMismatch': args.fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN': args.fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN': args.fixed_allowedMismatch_withoutNaN,
              'verbatimcolumn': args.verbatimcolumn,
              'verbatimauthorshiponly': args.verbatimauthorshiponly,
              'keep_fossil': args.keep_fossil,
              'identification_level': args.identification_level,
              'min_length': args.min_length,
              'doublecheck': args.doublecheck,
              'resume' : args.resume,
              'store': args.store,
              'overwrite': args.overwrite,
              'outputpath': args.outputpath,
              'outputfile': outputfile,
              'parallel': args.parallel,
              'max_attempt': args.max_attempt,
              'resume_parallel': args.resume_parallel,
              'store_parallel': args.store_parallel,
              'overwrite_parallel': args.overwrite_parallel
             }


    print_params.update(params)

    params['matchfilter']=matchfilter
    params['acceptedfilter']=acceptedfilter

    print()
    print("    Parameters")
    print("    ----------")
    for key, value in print_params.items():
        print(f'    {key}: {value}')
    print()

    start=time.time()

    _ = apply(df, **params)

    end=time.time()

    print(f'    TIME : {round(end - start,0)}s')
