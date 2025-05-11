#!/usr/bin/python
# coding: utf-8

# External imports

import re
import os
import json
import copy
import gzip #DEBUG
import yaml
import time
import argparse
import numpy as np
import Levenshtein
import pandas as pd
from tqdm import tqdm
from functools import wraps
from operator import itemgetter
from unidecode import unidecode
from difflib import get_close_matches
from importlib.resources import files

# Local imports

from marinedb.utils import regexstrip
from marinedb.utils import standardizenan
from marinedb.utils import writedataframe
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv
from marinedb.utils import preprocessquotationmark

from marinedb.tools import isin
from marinedb.tools import dropvalues
from marinedb.tools import getcolumnname
from marinedb.tools.taxonomic import createwormsfilters as cwf

# Global variables

__all__ = [] # populated using the @export decorator

IGNOREWORDS_PATH = files('marinedb.tools.data').joinpath('ignoreWords.yaml')
with open(IGNOREWORDS_PATH,'r') as f:
    file = yaml.safe_load(f)
    IGNOREWORDS = file['SCN_IGNORE'] + file['AUTHORSHIP_IGNORE']
IGNOREWORDS = sorted(IGNOREWORDS, key=len, reverse=True)
IGNOREWORDS = [word for word in IGNOREWORDS if len(word)>1]
IGNOREWORDS = '|'.join([fr'{word}' for word in IGNOREWORDS])

## Rank names in the file to be processed

# schema: RANK_MAPPING = {WoRMS_rank_name: rank_name_in_the_file}

 #######################################################################################
 # Leave `WoRMS_rank_name` unchanged, modify only `rank_name_in_the_file` if necessary #
 #######################################################################################

RANK_MAPPING = {
                'scientificname':'verbatimScientificName',
                'genus':'genus',
                'family':'family',
                'order':'order',
                'cls':'class',
                'phylum':'phylum',
                'kingdom':'kingdom'
               }

RANK_MAPPING_RENAMED = RANK_MAPPING

## WoRMS fields

 #########################################################
 # Must match `WORMSCALL` used in createwormsfilters.py, #
 # if filters were created upstream                      #
 #########################################################

 ################################
 # Do not remove starred values #
 ################################

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

COLNAMES = list(set(WORMSCALL) - set(RANK_MAPPING.keys())) + list(RANK_MAPPING.values())

## WORMS-specific column dtypes

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

def resume(filter, values, issciname):

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

    if (len(series1) != len(series2)):
        raise Exception

    if (len(series1.shape) != 1) or (len(series2.shape) != 1):
        raise Exception

    if series1.index.to_list() != series2.index.to_list():
        raise Exception

    temp = pd.concat([series1,series2], axis='columns')
    isallnan = temp.isna().all(axis='columns')

    # Process cases with only missing values separately (return pd.NA)
    res = pd.Series([pd.NA]*len(series1), dtype='boolean', index=series1.index.to_list())
    res[~isallnan] = series1[~isallnan].eq(series2[~isallnan])

    return res


def clean_string(string):

    # remove the accents
    string = unidecode(string)

    # replace special characters by " "
    pattern = r'[^a-zA-Z\s]+'
    string = re.sub(pattern, ' ', string)

    # standardize whitespace
    string = re.sub('\s+', ' ', string)

    # strip
    string = string.strip()

    # convert into lowercase characters
    string = string.lower()

    return string

def clean_split_strings(strings, authorship=False):

    # Example: '(Claparède & Lachmann) Diesing' TO ['claparede', 'lachmann', 'diesing']

    strings = unidecode(strings) # e.g. "Strøm"

    if authorship:

        # Replace all words in AUTHORSHIP_IGNORE section of ignoreWords.yaml with " "
        # remark: do no delete all words of less than 1 or 2 letters,
        # as sometimes only the first letter of the author is specified
        # e.g. "L." for Linné/Linnaeus

        pattern = fr'((?<=[\s\.,\-])|(?<=^))({IGNOREWORDS})([^a-zA-Z]|$)' # e.g. "ex" and "De" in "(Pers.) Rabenh. ex Ces. & De Not."
        strings = re.sub(fr'{pattern}', ' ', strings, flags=re.IGNORECASE) # re.IGNORECASE e.g. "Van" in "Dreissena Van Beneden, 1835"

    # Clean `strings`

    strings = clean_string(strings)

    # Split `strings` into words

    strings = strings.split(' ')

    # Remove single-letter words to avoid false mismatches
    # e.g. "J.Lachm." => `author`='j lachm'
    # vs.  "Lachmann" => `authorbestmatch`='lachmann'

    temp = [string for string in strings if len(string)>1]
    if len(temp)>0:
        strings = temp

    return strings


def elementwise_LevensteinRatio(strings, refstrings, difflib_cutoff=0.51): #!one-way, not commutative

    if pd.isnull(refstrings) or (len(refstrings) == 0) or pd.isnull(strings) or (len(strings) == 0):
        return pd.NA, pd.NA

    # Preparing strings

    refstrings = clean_split_strings(refstrings)
    strings = clean_split_strings(strings)
    ratio = 0
    Nmatch = 0

    for string in strings: #the result depends on the order of the `string` list

        ## Find the component closest to `string` in `refstrings`
        stringbestmatch = get_close_matches(string, refstrings, n=1, cutoff=difflib_cutoff) #difflib: cutoff=0.6 by default

        ## Compute the Levenstein ratio between `string` and `stringbestmatch`
        if len(stringbestmatch) != 0:
            Nmatch += 1
            stringbestmatch = stringbestmatch[0]
            ratio += Levenshtein.ratio(string, stringbestmatch)
            del refstrings[refstrings.index(stringbestmatch)]

    return np.round(ratio/len(strings),2), Nmatch


def match_WormsToVerbatimSpecies(wormsspecies, verbatimspecies, cutoff=0.65):

    wormsspecies = clean_split_strings(wormsspecies, authorship=True)
    verbatimspecies = clean_split_strings(verbatimspecies, authorship=True)

    mapping = []
    for wormsstring in wormsspecies:

        # Find the component closest to `wormsstring` in `verbatimspecies`
        verbatimbestmatch = get_close_matches(wormsstring, verbatimspecies, n=1, cutoff=cutoff)

        if len(verbatimbestmatch)!=0:
            # Store worms-to-verbatim mapping
            mapping += verbatimbestmatch
            del verbatimspecies[verbatimspecies.index(verbatimbestmatch[0])]

    return ' '.join(mapping)


def split_authorship(authorship):

    if pd.isnull(authorship) or (len(authorship) == 0): # i.e pd.NA or authorship==''
        return pd.NA, pd.NA, pd.NA

    # Find the date(s), if present

    pattern = r'[0-9]{4}'
    res = re.finditer(pattern,authorship)
    match = [m for m in res]

    # Find the author(s)

    if len(match) > 1:

        # More than one date
        # This case is not handled

        return pd.NA, pd.NA, pd.NA

    elif (len(match) == 0):

        # No date
        # assumption : the string corresponds to the authors' names

        date = pd.NA
        author = regexstrip.apply(authorship,r'[^a-zA-Z0-9]+')
        more = ''

    else:

        # One date

        match = match[0]
        date = int(match.group())
        start, stop = match.span()

        if (start == 0):

            # Date at the beginning of the string
            # assumption : the end of the string corresponds to the authors' names

            author = regexstrip.apply(authorship[stop:],r'[^a-zA-Z0-9]+')
            more = ''
            processed = True

        elif (stop == len(authorship)):

            # Date at the end of the string
            # assumption : the beginning of the string corresponds to the authors' names

            author = regexstrip.apply(authorship[:start],r'[^a-zA-Z0-9]+')
            more = ''
            processed = True

        elif (authorship[start-1] == '(') and (authorship[stop] != ')'):

            # Date preceded by a parenthesis
            # Find the closing parenthesis

            res = re.fullmatch(fr'(?P<more1>.*?)\({authorship[start:stop]}(?P<author>.+)\)(?P<more2>.*)', authorship)

            if res:

                # assumption : the text up to the last closing parenthesis corresponds to the authors' names
                # i.e more (date author) more
                author = regexstrip.apply(res['author'],r'[^a-zA-Z0-9]+')
                more = regexstrip.apply(res['more1'],r'[^a-zA-Z0-9]+') + regexstrip.apply(res['more2'],r'[^a-zA-Z0-9]+')
                processed = True

            else:
                processed = False

        elif (authorship[stop] == ')') and (authorship[start-1] != '('):

            # Date followed by a parenthesis
            # Find the opening parenthesis

            res = re.fullmatch(fr'(?P<more1>.*?)\((?P<author>.+?){authorship[start:stop]}\)(?P<more2>.*)', authorship)

            if res:

                # assumption : the text up to the first opening parenthesis (read backwards) corresponds to the authors' names
                # i.e more (author date) more
                author = regexstrip.apply(res['author'],r'[^a-zA-Z0-9]+')
                more = regexstrip.apply(res['more1'],r'[^a-zA-Z0-9]+') + regexstrip.apply(res['more2'],r'[^a-zA-Z0-9]+')
                processed = True

            else:
                processed = False

        else:
            processed = False

        if not processed:

            start_string = authorship[:start]
            stop_string = authorship[stop:]

            start_string = regexstrip.apply(start_string, r'[^a-zA-Z0-9]+')
            stop_string = regexstrip.apply(stop_string, r'[^a-zA-Z0-9]+')

            # assumption : the non-empty string corresponds to the authors' names
            if len(start_string) == 0:
                author = stop_string
                more = ''
            elif len(stop_string) == 0:
                author = start_string
                more = ''
            else:
                # assumption: the string preceding the date corresponds to the authors' names, following established conventions
                author = start_string
                more = stop_string

    # set aside text that probably does not correspond to the authors' names
    match = re.search(r'[A-Z]', author)
    if match:
        start = match.start()
        if start != 0:
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
    more = re.sub(r'[^a-zA-Z0-9]+','',more)

    return date, author, more


def match_AuthorshipByAuthors(refauthors, authors, difflib_cutoff=0.51, levenshtein_tolerance=0.7, author_tolerance=0.7):

    if pd.isnull(refauthors) or (len(refauthors) == 0) or pd.isnull(authors) or (len(authors) == 0):
        return pd.NA, pd.NA

    # Preparing authors' names
    refauthors = clean_split_strings(refauthors, authorship=True)
    authors = clean_split_strings(authors, authorship=True)

    # Do `authors` and `refauthors` match?

    Nmatch = 0
    for author in authors:
        if len(author) <= 3:
            cutoff = 0.1
        else:
            cutoff = difflib_cutoff

        ## Find the component closest to `author` in `refauthors`

        authorbestmatch = get_close_matches(author, refauthors, n=1, cutoff=cutoff) #difflib: cutoff=0.6 by default

        ## Do `author` and `authorbestmatch` match?

        if len(authorbestmatch) != 0:

            # should always be the case when `difflib_cutoff`=0
            authorbestmatch = authorbestmatch[0]

            if (author in authorbestmatch) or (authorbestmatch in author):
                # one contains the other
                Nmatch += 1

            elif Levenshtein.ratio(authorbestmatch, author) >= levenshtein_tolerance:
                # the levenshtein ratio between `authorbestmatch` and `author` is higher than `levenstein_tolerance`
                # `author` and `authorbestmatch` match sufficiently
                Nmatch += 1

            del refauthors[refauthors.index(authorbestmatch)]

            # else: no match

    ## Full match

    score = np.round(Nmatch/len(authors),1)
    if score >= author_tolerance:
        return True, score
    else:
        return False, score


def match_AuthorshipsByDatesAuthors(refauthorships, authorship, date_tolerance=2, difflib_cutoff=0.51, levenshtein_tolerance=0.7, author_tolerance=0.7): #author, date dataframe

    authorship['date'] = authorship['date'].astype('Int64')
    refauthorships['date'] = refauthorships['date'].astype('Int64')

    refauthorships['datematch_diff'] = pd.NA
    refauthorships['datematch'] = pd.NA
    refauthorships['authormatch_ratio'] = pd.NA
    refauthorships['authormatch'] = pd.NA

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

    params = {'difflib_cutoff': difflib_cutoff,
              'levenshtein_tolerance': levenshtein_tolerance,
              'author_tolerance': author_tolerance}

    for i, refauthors in enumerate(refauthorships.loc[index,'author']):
        refauthorships.loc[index[i],['authormatch','authormatch_ratio']] = match_AuthorshipByAuthors(refauthors, authorship.loc[0,'author'], **params)

    # Final match
    # date and author must both match when known,
    # otherwise date or author, whichever is known, must match

    refauthorships['match'] = pdmin(refauthorships, ['datematch','authormatch'], axis=1, skipna=True).astype('boolean')
    refauthorships['datematch_diff'] = refauthorships['datematch_diff'].astype('Int64')
    refauthorships['authormatch_ratio'] = refauthorships['authormatch_ratio'].astype('Float64')

    return refauthorships


def match_TaxaByAuthorship(verbatim, candidates, verbatimauthorshiponly=False, date_tolerance=2, difflib_cutoff=0.51, levenshtein_tolerance=0.7, author_tolerance=0.7, verbose=True, indent=''):

    params = {'date_tolerance': date_tolerance,
              'difflib_cutoff': difflib_cutoff,
              'levenshtein_tolerance': levenshtein_tolerance,
              'author_tolerance': author_tolerance}

    candidates[['sensu_conflict','match','datematch','datematch_diff','authormatch','authormatch_ratio']] = pd.NA
    candidates[['sensu_conflict','match','datematch','authormatch']] = candidates[['sensu_conflict','match','datematch','authormatch']].astype('boolean')
    candidates['datematch_diff'] = candidates['datematch_diff'].astype('Int64')
    candidates['authormatch_ratio'] = candidates['authormatch_ratio'].astype('Float64')
#    candidates['taxamatch'] = 'uncertain'
    ismore = False

    if pd.isnull(verbatim) or (len(verbatim) == 0):
        return candidates, ismore

    try:
        verbatim = verbatim.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError,UnicodeEncodeError):
        pass
    verbatim = unidecode(verbatim.strip())

    speidx = candidates.columns.to_list().index(RANK_MAPPING_RENAMED['scientificname'])
    wormsspecies = unidecode(candidates.iloc[0,speidx].strip())
    # note: Only the species name in the first line is considered.
    # In most cases, WoRMS candidates share the same species name.
    # However, if they do not, the best species name match
    # has been placed on the first line by the match_TaxaByFullClassification() function.

    # Find the species name in `verbatim`

    ## Determine the spelling of the species name components in `verbatim` using `wormsspecies`
    # i.e take misspelling into account e.g. "Clatria rubens" for "Clathria rubens"

    if verbatimauthorshiponly:
        wormsspecies = ''
    else:
        wormsspecies = match_WormsToVerbatimSpecies(wormsspecies, verbatim)

    if len(wormsspecies) == 0:
        # no match between `wormsspecies` components and `verbatim` components
        # assumption : `verbatim` only contains information on the authorship
        ismore = True
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
            more = re.sub(r'[^a-zA-Z0-9]+','',more)
            if len(more) > 1:
                ismore = True
            else:
                ismore = False

        else: # species name not found
            # assumption : `verbatim` only contains information on the authorship
            ismore = True
            verbatim_authorship = verbatim

    if len(verbatim_authorship) == 0:

        # no authorship information to separate candidates

        candidates['match'] = True

    else:

        # Authorship match

        ## Does verbatim authorship contain "sensu"?

        doescontainsensu_verbatim = ('sensu' in verbatim_authorship)

        ## Do the authorship candidates contain "sensu"?

        doescontainsensu_candidates = candidates['authority'].str.contains('sensu')

        ## Are there "sensu" conflicts between verbatim and authorship candidates?
        # `verbatim_authorship` does not contain "sensu" & one or more candidates contain "sensu"
        #  OR
        # `verbatim_authorship` contain "sensu" & one or more candidates does not contain "sensu"

        candidates['sensu_conflict'] = False
        candidates.loc[doescontainsensu_candidates != doescontainsensu_verbatim, 'sensu_conflict'] = True

        if doescontainsensu_verbatim:

            # `verbatim_authorship` contains "sensu"

            verbatim_authorship = verbatim_authorship.split('sensu')

            if len(verbatim_authorship) > 2:

                # more than one "sensu": unexpected

                printv(f"WARNING | More than one 'sensu' in {verbatim}. Exiting `match_TaxaByAuthorship`.", verbose=verbose, indent=indent)

                return candidates, ismore

            # for candidates not containing "sensu", no match is possible

            candidates.loc[~doescontainsensu_candidates, 'match'] = False
            candidates_authorships = candidates.loc[doescontainsensu_candidates,['authority']].copy()

        else:

            # `verbatim_authorship` does not contain "sensu"
            # but one or more candidates may contain "sensu"
            # and `verbatim_authorship` could match one of the authors of these candidates

            candidates_authorships = candidates[['authority']].copy()

        if len(candidates_authorships) == 0:

            # i.e `verbatimauthorship` contains "sensu"
            # but no candidate contains "sensu"
            # no match

            _ , _ , more1 = split_authorship(verbatim_authorship[0])
            if len(verbatim_authorship) != 1:
                _ , _ , more2 = split_authorship(verbatim_authorship[1])
            condition1 = (not pd.isnull(more1)) and (len(more1) > 0)
            condition2 = (not pd.isnull(more2)) and (len(more2) > 0)
            if condition1 or condition2:
                ismore = True

        else:

            candidates_sensusplit = candidates_authorships['authority'].str.split('sensu')

            if any(doescontainsensu_candidates):

                exitcondition = (candidates_sensusplit.str.len()>2)

                if any(exitcondition):

                    # more than one "sensu": unexpected

                    printv(f"WARNING | More than one 'sensu' in {candidates['authorship'].tolist()}. Exiting `match_TaxaByAuthorship`", verbose=verbose, indent=indent)

#                    isnomatch = (~pd.isnull(candidates['match'])) & (~candidates['match'])
#                    ismatch = (~pd.isnull(candidates['match'])) & (candidates['match'])
#                    candidates.loc[isnomatch,'taxamatch'] = 'nomatch'
#                    candidates.loc[ismatch,'taxamatch'] = 'match'

                    return candidates, ismore

            ## Split authorships into date, author, more

            # `verbatim_authorship`

            if doescontainsensu_verbatim:
                verbatim_authorship = list(split_authorship(verbatim_authorship[0])) + list(split_authorship(verbatim_authorship[1]))
            else:
                verbatim_authorship = list(split_authorship(verbatim_authorship))
                verbatim_authorship += verbatim_authorship
            verbatim_authorship = pd.DataFrame([verbatim_authorship], columns=['date1','author1','more1', 'date2', 'author2', 'more2'])

            if verbatim_authorship[['date1','author1']].isnull().all(None) or verbatim_authorship[['date2','author2']].isnull().all(None):

                printv(f"WARNING | Failed to parse the authorship of {verbatim}. Exiting `match_TaxaByAuthorship`", verbose=verbose, indent=indent)

                return candidates, ismore

            if any(verbatim_authorship['more1'].str.len() > 0) or any(verbatim_authorship['more2'].str.len() > 0):
                ismore = True

            # `candidates_authorships`

            candidates_authorships['authorship1'] = candidates_sensusplit.str[0]
            candidates_authorships['authorship2'] = candidates_sensusplit.str[1] #pd.NA if len<2
            index = candidates_authorships.index.to_list()

            for i, authorship in enumerate(candidates_authorships[['authorship1','authorship2']].values):
                candidates_authorships.loc[index[i],['date1','author1','more1']] = split_authorship(authorship[0])
                candidates_authorships.loc[index[i],['date2','author2','more2']] = split_authorship(authorship[1])

            ## Match authorships, both before and after "sensu", by date and author

            colmap1, colmap2 = {'date1':'date','author1':'author'}, {'date2':'date','author2':'author'}
            res1 = match_AuthorshipsByDatesAuthors(candidates_authorships[list(colmap1.keys())].rename(columns=colmap1), verbatim_authorship[list(colmap1.keys())].rename(columns=colmap1), **params)
            res2 = match_AuthorshipsByDatesAuthors(candidates_authorships[list(colmap2.keys())].rename(columns=colmap2), verbatim_authorship[list(colmap2.keys())].rename(columns=colmap2), **params)

            columns = ['match','datematch','datematch_diff','authormatch','authormatch_ratio']

            res1, res2 = res1[columns], res2[columns]
            colmap1 = dict(zip(columns, (pd.Series(columns) + '1')))
            colmap2 = dict(zip(columns, (pd.Series(columns) + '2')))
            res1 = res1.rename(columns=colmap1)
            res2 = res2.rename(columns=colmap2)
            column1 = list(itemgetter(*columns)(colmap1))
            column2 = list(itemgetter(*columns)(colmap2))
            candidates_authorships = pd.concat([candidates_authorships,res1[column1],res2[column2]],axis=1)

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
                if len(index_nomatch) != 0:
                    candidates.loc[index_nomatch,'match'] = False

                idx1 = []
                idx2 = []

                # Only one match

                index_singlematch = temp_match[temp_match==1].index.to_list()
                if len(index_singlematch) != 0:
                    singlematch = idxmax(temp.loc[index_singlematch,:], ['match1','match2'], axis=1, skipna=True)
                    idx1 = idx1 + singlematch[singlematch=='match1'].index.to_list()
                    idx2 = idx2 + singlematch[singlematch=='match2'].index.to_list()

                # More than one match

                index_morematch = temp_match[temp_match>1].index.to_list()
                if len(index_morematch) != 0:

                    #(~morematch_eqauthors) & (~morematch_eqdates) & (morematch_eqbest) : best author (equivalent to best date)
                    #(~morematch_eqauthors) & (~morematch_eqdates) & (~morematch_eqbest) : if conflict between best author and best date, best author by default
                    #(~morematch_eqauthors) & (morematch_eqdates) : best author
                    #(morematch_eqauthors) & (~morematch_eqdates) : best date
                    #(morematch_eqauthors) & (morematch_eqdates) : best author (equivalent to best date)

                    morematch = temp.loc[index_morematch,:]

                    morematch_eqauthors = ((morematch['authormatch_ratio1'] - morematch['authormatch_ratio2']).abs() <= 1e-2)
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

#            isnomatch = (~pd.isnull(candidates['match'])) & (~candidates['match'])
#            ismatch = (~pd.isnull(candidates['match'])) & (candidates['match'])
#            candidates.loc[isnomatch,'taxamatch'] = 'nomatch'
#            candidates.loc[ismatch,'taxamatch'] = 'match'

    return candidates, ismore


def match_TaxaByVerbatim(verbatim, candidates, wormscolumns, verbatimauthorshiponly=False, date_tolerance=2, difflib_cutoff=0.51, levenshtein_tolerance=0.7, author_tolerance=0.7, verbose=True, indent=''):

    params = {
              'date_tolerance': date_tolerance,
              'difflib_cutoff': difflib_cutoff,
              'levenshtein_tolerance': levenshtein_tolerance,
              'author_tolerance': author_tolerance,
              'indent': indent,
              'verbose': verbose
             }

    processed = False
    classif = None
    match_idx = None

    if pd.isnull(verbatim) or (len(verbatim) == 0):
        return {'candidates': candidates, 'processed': processed, 'match_idx': match_idx, 'classif': classif}

    # Match taxa by verbatim authorship

    candidates, ismore = match_TaxaByAuthorship(verbatim, candidates, **params)

    if pd.isnull(candidates['match']).all():
        return {'candidates': candidates, 'processed': processed, 'match_idx': match_idx, 'classif': classif}

    candidates = candidates[candidates['match']]

    if len(candidates) == 0:

        # No match

        doesmatch = 'nomatch'

        if ismore and (not verbatimauthorshiponly):

            # other information available but not used

            classif = [doesmatch,'verbatim_noMatchIsMore'] + [pd.NA]*len(wormscolumns)

        else:

            classif = [doesmatch,'verbatim_noMatch'] + [pd.NA]*len(wormscolumns)

        processed = True

    elif len(candidates) == 1:

        # Only one match

        match_idx = candidates.index[0]

        if pd.isnull(candidates.loc[match_idx,'authormatch_ratio']) and pd.isnull(candidates.loc[match_idx,'datematch_diff']):

            # Insufficient information to draw a conclusion

            match_idx = None

        else:

            doesmatch = 'match'
            classif = [doesmatch,'verbatim_singleMatch'] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
            processed = True

    else:

        # More than one match

        if not candidates['authormatch_ratio'].isna().all():

            # Keep the candidate that best matches the verbatim author names

            candidates = candidates[~pd.isnull(candidates['authormatch_ratio'])]
            max_authormatch_ratio = candidates['authormatch_ratio'].max()
            candidates = candidates[(max_authormatch_ratio - candidates['authormatch_ratio'])<=1e-2]

            if len(candidates)==1:

                # Only one match

                doesmatch = 'match'
                match_idx = candidates.index[0]
                classif = [doesmatch,'verbatim_bestAuthorMatch'] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
                processed = True

        if (not processed) and (not all(candidates['datematch_diff'].isna())):

            # Keep the candidate that best matches:
            # - the verbatim author names, if any
            # - and the verbatim authorship date

            candidates = candidates[~pd.isnull(candidates['datematch_diff'])]
            min_datematch_diff = candidates['datematch_diff'].min()
            candidates = candidates[candidates['datematch_diff']==min_datematch_diff]

            if len(candidates) == 1:

                # Only one match

                doesmatch = 'match'
                match_idx = candidates.index[0]
                classif = [doesmatch,'verbatim_bestDateMatch'] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
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

            if len(candidates) == 1:

                # Only one match

                doesmatch = 'match'
                match_idx = candidates.index[0]
                classif = [doesmatch,'verbatim_noSensuConflict'] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
                processed = True

    return {'candidates': candidates, 'processed': processed, 'match_idx': match_idx, 'classif': classif}


def fuzzymatch_HigherRanks(ranks1, ranks2, levenshtein_tolerance=0.7):

    diffnan = (ranks1.isna() != ranks2.isna()) # if both are null, it is considered a match

    match = []

    for c in range(ranks1.shape[0]): # candidate classification

        isnan = False
        Nnan = 0
        Nmismatch = 0
        match.append([])

        for r in range(ranks1.shape[1]): # rank

            r1 = ranks1.iloc[c,r]
            r2 = ranks2.iloc[c,r]

            if diffnan.iloc[c,r]:
                isnan = True
                Nnan += 1

            elif (not pd.isnull(r1)) and (not pd.isnull(r2)):

                r1 = re.sub('incertae sedis','',r1).strip()
                r2 = re.sub('incertae sedis','',r2).strip()

                if Levenshtein.ratio(r1, r2) < levenshtein_tolerance:
                    Nmismatch += 1

        match[c].append(Nmismatch)
        match[c].append(Nnan)
        match[c].append(isnan)

    match = pd.DataFrame(match, columns=['Nmismatch','Nnan','isnan'])

    return match

def exactmatch_HigherRanks(ranks1, ranks2):

    diff = (ranks1.fillna('') != ranks2.fillna('')) # compute differences

    isnan = (ranks1.isna()!=ranks2.isna()) # if both are null, it is considered a match
                                           # if only one is null, it is considered a mismatch

    match = pd.DataFrame(diff[~isnan].sum(axis=1).astype(int), columns=['Nmismatch'])

    match['Nnan'] = isnan.sum(axis=1) # number of NaNs
    match['isnan'] = isnan.any(axis=1)

    return match

def match_TaxaByHigherRanks(ranks1, ranks2, fuzzy=True, fixed_allowedMismatch=False, auto_allowedMismatch=NaN2AllowedMismatch, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2):

    ranks1 = ranks1.astype('string')
    ranks2 = ranks2.astype('string')

    if pd.isnull(ranks1).all(axis=None) or pd.isnull(ranks2).all(axis=None):
        match = pd.DataFrame([[0,6,True,False]], columns=['Nmismatch','Nnan','isnan','match'])
        return match

    # Difference between the two classifications

    if fuzzy:
        # Partial fuzzy matching
        match = fuzzymatch_HigherRanks(ranks1, ranks2)

    else:
        # Partial exact matching
        match = exactmatch_HigherRanks(ranks1, ranks2)

    # Number of mismatches allowed according to the number of NaNs

    allowedMismatchByNaN = pd.DataFrame.from_dict(auto_allowedMismatch, orient='index', columns=['max_mismatch'])
    if fixed_allowedMismatch:
        allowedMismatchByNaN.iloc[0,0] = fixed_allowedMismatch_withoutNaN
        allowedMismatchByNaN.iloc[1:-1,0] = fixed_allowedMismatch_withNaN
        allowedMismatchByNaN.iloc[-1,0] = -1

    # Full naive matching
    # naive, as it does not account for the level of non-matching ranks

    match.loc[:,'match'] = (match.loc[:,'Nmismatch'].values <= allowedMismatchByNaN.loc[match.loc[:,'Nnan'],'max_mismatch'].values)

    return match


def match_TaxaByFullClassification(data_classif, worms_classif, check_ambiguity=True, verbatimcolumn=None, verbatimauthorshiponly=None, fuzzy=True, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False):

    higherranks = list(set(RANK_MAPPING_RENAMED.values()) - set([RANK_MAPPING_RENAMED['scientificname']]))
    wormscolumns = list(worms_classif.columns)
    colnames = ['taxamatch_generatedby_isinworms','classif_matchtype_generatedby_isinworms'] + wormscolumns

    add_ambiguitycol = check_ambiguity

    isambiguity = False
    ambiguitymsg = []
    isverbatim = (verbatimcolumn is not None)

    isnomatch = worms_classif['match_type'].str.contains(r'nomatch|above',regex=True)
    if isnomatch.any():

        # No match in WoRMS

        if (not isnomatch.all()) or (len(worms_classif['match_type'].unique())!=1): # something wrong
            print('-----------------------------')
            print('            ERROR            ')
            print('-----------------------------')
            print(worms_classif)
            raise NotImplementedError('`isinworms.py` | some candidates match while others do not, or none match but have different `match_type` values')

        else:
            doesmatch = 'nomatch'
            match_idx = None
            match_type = worms_classif.loc[0,'match_type']
            if match_type == 'match_abovespecies':
                classif_matchtype = 'worms_taxonNoSpecies'
            else:
                classif_matchtype = 'worms_taxonNoMatch'
            classif = pd.DataFrame([[doesmatch,classif_matchtype] + [pd.NA]*len(wormscolumns)], columns=colnames)
            processed = True
            check_ambiguity = False

    elif worms_classif['match_type'].isin(['match_quarantine','match_deleted']).all():

        # No match in WoRMS

        doesmatch = 'nomatch'
        match_idx = None
        classif = pd.DataFrame([[doesmatch,'worms_taxonQuarantineDeleted'] + [pd.NA]*len(wormscolumns)], columns=colnames)
        processed = True
        check_ambiguity = False

    else:

        # WoRMS match

        params = {
                  'fuzzy':fuzzy,
                  'fixed_allowedMismatch':fixed_allowedMismatch,
                  'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
                  'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN
                 }

        processed = False


        # STEP N°1: Do the higher ranks match?

        match = match_TaxaByHigherRanks(worms_classif.loc[:,higherranks], data_classif.loc[:,higherranks], **params)

        # Worst-case strategy (risk aversion):
        # N certain non-matches are preferred to (N+1) potential non-matches, and therefore also to (N+1) potential matches
        # i.e to (N+1) missing values
        # Best classification:
        # classification with the lowest `mismatch_level` and the lowest number of mismatches within that level (`Nmismatch`)

        match['mismatch_level'] = match['Nmismatch'] + match['Nnan']


        # Reorder lines based on species name match for subsequent processing steps
        # see match_TaxaByAuthorship() and STEP N°5 below


        match_index = match.index.tolist()
        candidates = worms_classif.loc[match_index,:]

        unique_wormsspecies = candidates[RANK_MAPPING_RENAMED['scientificname']].unique()

        if (match['match'].sum() != 1) and (len(unique_wormsspecies) > 1): #DEBUG !=1

            # More than one species name among WoRMS candidates

            match[['speciesratio','Nspeciesmatch']] = pd.NA
            match['speciesratio'] = match['speciesratio'].astype('Float64')
            match['Nspeciesmatch'] = match['Nspeciesmatch'].astype('Int64')

            ## Compute the Levenstein ratio between each unique WoRMS species name and the name of the species being processed

            indexBywormsspecies = candidates[[RANK_MAPPING_RENAMED['scientificname']]].groupby([RANK_MAPPING_RENAMED['scientificname']]).indices
            dataspecies = data_classif.loc[0,RANK_MAPPING_RENAMED['scientificname']]
            for wormsspecies in unique_wormsspecies:
                match.loc[indexBywormsspecies[wormsspecies],['speciesratio','Nspeciesmatch']] = elementwise_LevensteinRatio(wormsspecies, dataspecies)

            ## Best species name
            # i.e  species name with the highest number of components and the best Levenstein ratio
            # e.g. species: "Haliclona (Rhizoniera) viscosa" (may be misspelled)
            #      worms: "Haliclona (Rhizoniera) viscosa" & "Haliclona viscosa"
            #      the result should be "Haliclona (Rhizoniera) viscosa",
            #      even if the Levenstein ratio is lower due to spelling mistakes

            bestspecies = match[(match['speciesratio'] >= 0.8)] # threshold of 0.8 to minimize false matches
            bestspecies = bestspecies.sort_values(by=['Nspeciesmatch','speciesratio'], ascending=False)

            match = pd.concat([bestspecies, match.loc[(match['speciesratio'] < 0.8),bestspecies.columns]], axis=0)

            match_index = match.index.tolist()
            candidates = candidates.loc[match_index,:]

        else:

            match['speciesratio'] = 1
            match['Nspeciesmatch'] = 1

        candidates = candidates.astype('string')
        candidates = candidates.fillna('_MISSING_')
        candidates = candidates.drop_duplicates(subset = higherranks + ['authority','valid_AphiaID'], keep='first', inplace=False)
        candidates = candidates.replace('_MISSING_',pd.NA)

        match_index = candidates.index.tolist()
        match = match.loc[match_index,:]


        # CASE N°1: Only one higher ranks match


        if match['match'].sum()==1:

            doesmatch = 'match'
            match_idx = np.where(match['match'])[0][0]
            classif = pd.DataFrame([[doesmatch,'classification_singleMatch'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
            processed = True
            check_ambiguity = False


        # CASE N°2: More than one higher ranks match


        if match['match'].sum() > 1:

            match = match[match['match']]

            match_index = match.index.tolist()
            candidates = worms_classif.loc[match_index,:]


            # STEP N°2: Do all candidates refer to the same accepted species?


            unique_aphiaID = candidates['valid_AphiaID'].unique()
            if len(unique_aphiaID) == 1:

                # By default, keep the first one
                # all candidates refer to the same accepted species

                doesmatch = 'match'
                match_idx = match_index[0]
                classif = pd.DataFrame([[doesmatch,'classification_singleAphiaID'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                processed = True
                check_ambiguity = False


            # STEP N°3: Is it possible to decide among candidates based on the information in the raw data?


            if (not processed) and isverbatim and (not pd.isnull(candidates['authority']).any()):

                index = 0
                while (not processed) and (index != len(verbatimcolumn)):

                    verbatim = data_classif.loc[0,verbatimcolumn[index]]

                    if not pd.isnull(verbatim):

                        results = match_TaxaByVerbatim(verbatim, candidates, wormscolumns, verbatimauthorshiponly=verbatimauthorshiponly[index])

                        candidates = results['candidates']
                        match_idx = results['match_idx']
                        classif = results['classif']
                        processed = results['processed']

                    if processed:

                        # Keep the candidate whose authorship best matches the verbatim authorship, if any

                        classif = pd.DataFrame([classif], columns=colnames)
                        classif['classif_matchtype_generatedby_isinworms'] = 'classification_' + classif['classif_matchtype_generatedby_isinworms']

                        if check_ambiguity:

                            if match_idx is None:
                                check_ambiguity = False
                            else:
                                candidates = worms_classif.loc[match_index,:]
                                ambiguitymsg.append('VERBATIM')

                    else:
                        index += 1

            # STEP N°4: Is one of the candidates the best match for higher taxonomic ranks?


            if (not processed) or (isverbatim and check_ambiguity):

                match_temp = match.loc[candidates.index,:]
                match_temp = match_temp[(match_temp['mismatch_level'] == match_temp['mismatch_level'].min())]
                match_temp = match_temp[(match_temp['Nmismatch'] == match_temp['Nmismatch'].min())]
                candidates = candidates.loc[match_temp.index,:]

                if isverbatim and check_ambiguity:

                    # Are the best candidates based on raw data also
                    # the best candidates based on higher rank matches?

                    if processed:

                        # i.e processed in the previous step

                        isambiguity = (match_idx not in candidates.index)

                    if (not processed):

                        # i.e not processed in the previous step

                        match_bestclassif = match.copy()
                        match_bestclassif = match_bestclassif[(match_bestclassif['mismatch_level'] == match_bestclassif['mismatch_level'].min())]
                        match_bestclassif = match_bestclassif[(match_bestclassif['Nmismatch'] == match_bestclassif['Nmismatch'].min())]

                        index_intersection = set(match_bestclassif.index).intersection(candidates.index)
                        isambiguity = (len(index_intersection) != len(candidates))

                    if isambiguity:
                        ambiguitymsg.append('HIGHERRANKS')

                if (not isverbatim) and check_ambiguity:
                    ambiguitymsg.append('HIGHERRANKS')

                if (not processed) and (len(candidates) == 1):

                    # Only one match

                    doesmatch = 'match'
                    match_idx = candidates.index[0]
                    classif = pd.DataFrame([[doesmatch,'classification_bestMatch'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                    processed = True


            # STEP N°5: Does one of the candidates best match the species name?


            if (not processed) or (check_ambiguity and (not isambiguity)):

                if processed:

                    condition1 = (match.loc[match_idx,'Nspeciesmatch'] != match.loc[match_index[0],'Nspeciesmatch'])
                    condition2 = ((match.loc[match_index[0],'speciesratio'] - match.loc[match_idx,'speciesratio']) >= 1e-2)
                    isambiguity = (condition1 | condition2)

                else:

                    match_temp = match.loc[candidates.index,:].copy()
                    match_temp = match_temp[(match_temp['Nspeciesmatch'] == match_temp['Nspeciesmatch'].max())]
                    max_speciesratio = match_temp['speciesratio'].max() # no NaN
                    match_temp = match_temp[(max_speciesratio - match_temp['speciesratio'])<1e-2]
                    candidates = candidates.loc[match_temp.index,:]

                    if check_ambiguity and (not isambiguity):
                        idx = candidates.index[0]
                        condition1 = (match.loc[idx,'Nspeciesmatch'] != match.loc[match_index[0],'Nspeciesmatch'])
                        condition2 = ((match.loc[match_index[0],'speciesratio'] - match.loc[idx,'speciesratio'])>=1e-2)
                        isambiguity = (condition1 | condition2)

                    if (len(candidates)==1):

                        # Only one match

                        doesmatch = 'match'
                        match_idx = candidates.index[0]
                        classif = pd.DataFrame([[doesmatch,'classification_bestSpeciesName'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                        processed = True

                if check_ambiguity and isambiguity:
                    ambiguitymsg.append('SPECIESNAME')

            # STEP N°6: Do all candidates have the same classification and "accepted" status?


            if (not processed):

                isidentical_exclauthspe = candidates[higherranks + ['status']].fillna('_MISSING_').drop_duplicates(inplace=False)
                condition1 = (len(isidentical_exclauthspe) == 1)
                condition2 = (isidentical_exclauthspe.loc[candidates.index[0],'status'] == 'accepted')

                if condition1 and condition2:

                    # By default, keep the first one
                    # all candidates share the same classification and “accepted” status but differ only in authority,
                    # suggesting they likely refer to the same species

                    doesmatch = 'match'
                    match_idx = candidates.index[0]
                    classif = pd.DataFrame([[doesmatch,'classification_allAccepted'] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                    processed = True


            # STEP N°7: Uncertain


            if (not processed):

                # Decision not possible, review manually or delete

                doesmatch = 'uncertain'
                match_idx = None
                classif = pd.DataFrame([[doesmatch,'classification_undecided'] + [pd.NA]*len(wormscolumns)], columns=colnames)
                processed = True

        # CASE N°3: no higher ranks match

        if match['match'].sum() == 0:

            check_ambiguity = False

            # No match for higher ranks,
            # either due to unmet criteria
            # or the complete absence of information for higher ranks

            candidates = candidates[candidates['match_type'].isin(['exact','exact_subgenus','phonetic','near_1','near_2','near_3'])]

            noranks = pd.isnull(candidates[RANK_MAPPING_RENAMED['kingdom']])
            datakingdom = data_classif.loc[0,RANK_MAPPING_RENAMED['kingdom']]
            if any(~noranks) and (datakingdom != 'incertae sedis'):

                candidates_withranks = candidates[~noranks]
                if fuzzy:
                    isequalkingdom = [(Levenshtein.ratio(kingdom, datakingdom) >= 0.7) for _,kingdom in enumerate(candidates_withranks[RANK_MAPPING_RENAMED['kingdom']])]
                else:
                    isequalkingdom = (candidates_withranks[RANK_MAPPING_RENAMED['kingdom']] == datakingdom)
                candidates_withranks = candidates_withranks[isequalkingdom]

                candidates = pd.concat([candidates_withranks,candidates.loc[noranks,candidates_withranks.columns]],axis=0)

            if len(candidates) != 0:

                if (verbatimcolumn is not None) and all(~pd.isnull(candidates['authority'])):

                    # If species match is high, use verbatim authorship,
                    # classification may have changed

                    index = 0
                    while (not processed) and (index != len(verbatimcolumn)):

                        verbatim = data_classif.loc[0,verbatimcolumn[index]]

                        if not pd.isnull(verbatim):

                            results = match_TaxaByVerbatim(verbatim, candidates, wormscolumns, verbatimauthorshiponly=verbatimauthorshiponly[index])

                            candidates = results['candidates']
                            match_idx = results['match_idx']
                            classif = results['classif']
                            processed = results['processed']

                        if processed:

                            # Keep the candidate whose authorship best matches the verbatim authorship, if any

                            classif = pd.DataFrame([classif], columns=colnames)
                            classif['classif_matchtype_generatedby_isinworms'] = 'noclassification_' + classif['classif_matchtype_generatedby_isinworms']

                        else:
                            index+=1

                if (not processed):

                    # Check by hand or delete

                    doesmatch = 'uncertain'
                    match_idx = None
                    classif = pd.DataFrame([[doesmatch,'noclassification_suspicious'] + [pd.NA]*len(wormscolumns)], columns=colnames)
                    processed = True

            else:

                doesmatch = 'nomatch'
                match_idx = None
                classif = pd.DataFrame([[doesmatch,'noclassification_kingdomNoMatch'] + [pd.NA]*len(wormscolumns)], columns=colnames)
                processed = True

    # Remove fossils

    if not keep_fossil:

        worms_classif['isExtinct'] = worms_classif['isExtinct'].astype('Int64')
        indexes = worms_classif[worms_classif['isExtinct'] == 1].index

        if match_idx in indexes:

             doesmatch = 'nomatch'
             classif_matchtype = classif.loc[0,'classif_matchtype_generatedby_isinworms'] + '_fossil'
             classif = pd.DataFrame([[doesmatch,classif_matchtype] + [pd.NA]*len(wormscolumns)], columns=colnames)

    if add_ambiguitycol:
        classif['issue_isinworms'] = ('AMBIGUOUS_TAXAMATCH_' + '_'.join(ambiguitymsg) if isambiguity else pd.NA)

    return classif

def display_progress(classification, idx, verbose=True, indent=''):

    classif = classification.loc[:idx,:]

    nclassification = len(classification)
    Nnomatch = len(classif[classif['taxamatch_generatedby_isinworms'] == 'nomatch'])
    Nmatch = len(classif[classif['taxamatch_generatedby_isinworms'] == 'match'])
    Nunk = len(classif[classif['taxamatch_generatedby_isinworms'] == 'uncertain'])
    assert (Nnomatch + Nmatch + Nunk) == (idx+1) #DEBUG
    percentage = np.round((idx+1)/nclassification*100,2)

    printv(f'Processing | {idx+1}/{nclassification} classifications done ({percentage}%): no_match={Nnomatch}, match={Nmatch}, uncertain={Nunk}', verbose=verbose, indent=indent)

    return True

def call_create_WoRMSrecognizedfilter(species, min_length=3, doublecheck=True, resume=True, resume_mode='soft', store=True, outputdir='./', outputfile='worms_matchfilter.txt', outputfile_suffix='generatedby_isinworms', overwrite=False, parallel=False, max_attempt=3, resume_parallel=True, store_parallel=True, overwrite_parallel=False, verbose=True, indent=''):

    params_func = {
                   'wormscall': WORMSCALL,
                   'min_length': min_length,
                   'doublecheck': doublecheck,
                   'identification_level': 'species',
                   'resume': resume,
                   'resume_mode': resume_mode,
                   'indent': indent,
                   'verbose': verbose
                  }

    params_store = {
                    'store': store,
                    'outputdir': outputdir,
                    'outputfile': outputfile,
                    'overwrite': overwrite
                  }

    params_parallel = {
                       'parallel': parallel,
                       'max_attempt': max_attempt,
                       'resume_parallel': resume_parallel,
                       'store_parallel': store_parallel,
                       'overwrite_parallel': overwrite_parallel
                      }

    if store:

        outputfile_split = outputfile.split('.')

        if len(outputfile_suffix) == 0:
            outputfile_suffix = 'generatedby_isinworms'

        if ('isinworms' not in outputfile_suffix):
            outputfile_suffix = outputfile_suffix + '_generatedby_isinworms'

        params_store['outputfile'] = outputfile_split[0] + '_' + outputfile_suffix + '.' + outputfile_split[1]

    matchfilter = cwf.create_WoRMSrecognizedfilter(species, **params_func, **params_store, **params_parallel)

    return matchfilter

def apply_matchfilter(classification, matchfilter=None, check_ambiguity=True, fuzzy=True, verbatimcolumn=None, verbatimauthorshiponly=None, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False, store=True, outputdir='./', overwrite=False, parallel=False, verbose=True, indent='', **params_dict):

    # Parameters

    params_store = {
                   'outputdir':outputdir,
                   'store':store,
                   'store_parallel':store,
                   'overwrite':overwrite,
                   'overwrite_parallel':overwrite
                   }

    if 'store_parallel' in params_dict.keys():
        if parallel and (store != params_dict['store_parallel']):
            raise ValueError(f'`isinworms.py` | parallel={parallel} and store={store} but store_parallel={params_dict["store_parallel"]}')
        params_store['store_parallel'] = params_dict.pop('store_parallel')

    if 'overwrite_parallel' in params_dict.keys():
        if parallel and (overwrite != params_dict['overwrite_parallel']):
            raise ValueError(f'`isinworms.py` | parallel={parallel} and overwrite={overwrite} but overwrite_parallel={params_dict["overwrite_parallel"]}')
        params_store['overwrite_parallel'] = params_dict.pop('overwrite_parallel')

    # Match taxa to a WoRMS classification, based on:
    # - the taxon name
    # - higher ranks
    # - and, if available, authorship

    nclassification = len(classification)
    printv(f'* WoRMS filtering (recognized marine taxa) | {nclassification} unique classifications', verbose=verbose, indent=indent)

    ## Match species name

    unique_species = classification[RANK_MAPPING_RENAMED['scientificname']].unique().tolist()

    if matchfilter is None:

        # Create WoRMS match filter

        printv(f'** isinworms | createwormsfilter', verbose=verbose, indent=indent)

        matchfilter = call_create_WoRMSrecognizedfilter(unique_species, parallel=parallel, verbose=verbose, indent=indent, **params_store, **params_dict)

    else:

        # Ensure all columns required for filtering are included in the WoRMS match filter

        check_columns = ['group'] + WORMSCALL
        if (len(check_columns) > len(matchfilter.columns)) or any(col not in matchfilter.columns for col in check_columns):
           raise KeyError(f'`isinworms.py` | filter column names must be: {check_columns}')

        # Complete the WoRMS match filter if necessary

        species2process = resume(matchfilter, unique_species, issciname=True)
        if len(species2process) != 0:

            printv(f'** isinworms | createwormsfilter', verbose=verbose, indent=indent)
            printv(f'UPDATE | {len(species2process)}/{len(unique_species)} ({np.round(len(species2process)/len(unique_species)*100,2)}%) taxa remaining to be processed', verbose=verbose, indent=indent)

            params_dict['outputfile_suffix'] = 'additional'
            params_dict['resume_mode'] = 'hard'
            params_store['overwrite'] = False
            params_store['overwrite_parallel'] = False

            addmatchfilter = call_create_WoRMSrecognizedfilter(species2process, parallel=parallel, verbose=verbose, indent=indent, **params_store, **params_dict)
            matchfilter = pd.concat([matchfilter,addmatchfilter.loc[:,matchfilter.columns]], axis=0)

    ## Match higher ranks & authorship

    matchfilter = matchfilter.rename(columns=RANK_MAPPING_RENAMED)
    filter = matchfilter.groupby(['group'])

    params = {
              'check_ambiguity': check_ambiguity,
              'fuzzy': fuzzy,
              'fixed_allowedMismatch': fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN': fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN': fixed_allowedMismatch_withoutNaN,
              'verbatimauthorshiponly': verbatimauthorshiponly,
              'verbatimcolumn': verbatimcolumn,
              'keep_fossil': keep_fossil
             }

    if verbatimcolumn is None:
        # no authorship
        datacolumns = list(RANK_MAPPING_RENAMED.values())
    else:
        if isinstance(verbatimcolumn,str):
            verbatimcolumn = [verbatimcolumn]
        # use authorship, if any
        datacolumns = list(set(list(RANK_MAPPING_RENAMED.values()) + verbatimcolumn))

    colnames = COLNAMES + ['taxamatch_generatedby_isinworms','classif_matchtype_generatedby_isinworms']
    if check_ambiguity:
        colnames += ['issue_isinworms']

    coldiff = list(set(colnames) - set(RANK_MAPPING_RENAMED.values()))
    classification[coldiff] = pd.NA

#    process = tqdm(range(nclassification), desc=indent + 'Progress')
    for idx in range(nclassification):

        spe = tuple([classification.loc[idx,RANK_MAPPING_RENAMED['scientificname']]])

        worms_classif = filter.get_group(spe).reset_index(drop=True)
        data_classif = pd.DataFrame([classification.loc[idx,datacolumns].tolist()]*len(worms_classif),columns=datacolumns).reset_index(drop=True)

        classif = match_TaxaByFullClassification(data_classif, worms_classif, **params)

        if (classif.loc[0,'taxamatch_generatedby_isinworms'] == 'uncertain'):

            # Keep original values

            classification.loc[idx,'classif_matchtype_generatedby_isinworms'] = classif.loc[0,'classif_matchtype_generatedby_isinworms']
            classification.loc[idx,'taxamatch_generatedby_isinworms'] = classif.loc[0,'taxamatch_generatedby_isinworms']
            if check_ambiguity:
                classification.loc[idx,'issue_isinworms'] = classif.loc[0,'issue_isinworms']

        else:

            # Keep WoRMS values

            classification.loc[idx,colnames] = classif.loc[0,colnames]

        if (((idx+1)%1000) == 0) or (idx == (nclassification-1)):

            # Display code progress

            display_progress(classification, idx, verbose=verbose, indent=indent)

    return classification


def call_create_WoRMSacceptedfilter(valid_aphiaID, store=True, outputdir='./', outputfile='worms_acceptedfilter.txt', outputfile_suffix='generatedby_isinworms', overwrite=False, resume=True, resume_mode='soft', parallel=False, max_attempt=3, resume_parallel=True, store_parallel=True, overwrite_parallel=False, verbose=True, indent=''):

    # Parameters

    params_func = {
                   'wormscall': WORMSCALL,
                   'species_only': True,
                   'resume': resume,
                   'resume_mode': resume_mode,
                   'indent': indent,
                   'verbose': verbose
                  }

    params_store = {
                    'store': store,
                    'outputdir': outputdir,
                    'outputfile': outputfile,
                    'overwrite': overwrite
                  }

    params_parallel = {
                       'parallel': parallel,
                       'max_attempt': max_attempt,
                       'resume_parallel': resume_parallel,
                       'store_parallel': store_parallel,
                       'overwrite_parallel': overwrite_parallel
                      }

    if store:

        outputfile_split = outputfile.split('.')

        if len(outputfile_suffix) == 0:
            outputfile_suffix = 'generatedby_isinworms'

        if ('isinworms' not in outputfile_suffix):
            outputfile_suffix = outputfile_suffix + '_generatedby_isinworms'

        params_store['outputfile'] = outputfile_split[0] + '_' + outputfile_suffix + '.' + outputfile_split[1]

    matchfilter = cwf.create_WoRMSacceptedfilter(valid_aphiaID, **params_func, **params_store, **params_parallel)

    return matchfilter

def apply_acceptedfilter(classification, acceptedfilter=None, keep_fossil=False, store=True, outputdir='./', overwrite=False, parallel=False, verbose=True, indent='', **params_dict):

    if len(classification) == 0:
        return classification

    # Parameters

    params_store = {
                    'outputdir': outputdir,
                    'store': store,
                    'store_parallel': store,
                    'overwrite': overwrite,
                    'overwrite_parallel': overwrite
                   }

    if 'store_parallel' in params_dict.keys():
        if parallel and (store != params_dict['store_parallel']):
            raise ValueError(f'`isinworms.py` | parallel={parallel} and store={store} but store_parallel={params_dict["store_parallel"]}')
        params_store['store_parallel'] = params_dict.pop('store_parallel')

    if 'overwrite_parallel' in params_dict.keys():
        if parallel and (overwrite != params_dict['overwrite_parallel']):
            raise ValueError(f'`isinworms.py` | parallel={parallel} and overwrite={overwrite} but overwrite_parallel={params_dict["overwrite_parallel"]}')
        params_store['overwrite_parallel'] = params_dict.pop('overwrite_parallel')

    classification['valid_AphiaID'] = classification['valid_AphiaID'].astype('Float64').astype('Int64')
    if acceptedfilter is not None:
        acceptedfilter['group'] = acceptedfilter['group'].astype('Float64').astype('Int64')

    # Identify unaccepted taxa

    unaccepted_idx = classification[(classification['status'] != 'accepted') & (~pd.isnull(classification['valid_AphiaID']))].index
    nunaccepted = len(unaccepted_idx)

    # Map unaccepted taxa to their accepted classification

    if len(unaccepted_idx) != 0:

        printv(f'* WoRMS filtering (accepted taxa) | {nunaccepted} occurrences of unaccepted taxa', verbose=verbose, indent=indent)

        unique_aphiaID = classification.loc[unaccepted_idx,'valid_AphiaID'].unique().tolist()

        if acceptedfilter is None:

            # Create WoRMS accepted match filter

            printv(f'** isinworms | createwormsfilter', verbose=verbose, indent=indent)

            acceptedfilter = call_create_WoRMSacceptedfilter(unique_aphiaID, parallel=parallel, verbose=verbose, indent=indent, **params_store, **params_dict)

        else:

            # Ensure all columns required for matching are present in the WoRMS accepted match filter

            check_columns = ['group'] + WORMSCALL
            if (len(check_columns) > len(acceptedfilter.columns)) or any(col not in acceptedfilter.columns for col in check_columns):
                raise KeyError(f'`isinworms.py` | filter column names must be: {check_columns}')

            # Complete the WoRMS accepted match filter if necessary

            aphiaID2process = resume(acceptedfilter, unique_aphiaID, issciname=False)
            if len(aphiaID2process) != 0:

                printv(f'** isinworms | createwormsfilter', verbose=verbose, indent=indent)
                printv(f'UPDATE | {len(aphiaID2process)}/{len(unique_aphiaID)} ({np.round(len(aphiaID2process)/len(unique_aphiaID)*100,2)}%) unaccepted taxa remaining to be processed', verbose=verbose, indent=indent)

                params_dict['outputfile_suffix'] = 'additional'
                params_dict['resume_mode'] = 'hard'
                params_store['overwrite'] = False
                params_store['overwrite_parallel'] = False

                addacceptedfilter = call_create_WoRMSacceptedfilter(aphiaID2process, parallel=parallel, verbose=verbose, indent=indent, **params_store, **params_dict)

                acceptedfilter = pd.concat([acceptedfilter,addacceptedfilter.loc[:,acceptedfilter.columns]], axis=0)

        if len(acceptedfilter['group'].unique()) != len(acceptedfilter): #DEBUG
            raise Exception(f'`isinworms.py` | Accepted classification filter must not contain duplicates for the `valid_aphiaID` column.')

        # Match `valid_aphiaID`

        acceptedfilter = acceptedfilter.rename(columns=RANK_MAPPING_RENAMED)
        filter = acceptedfilter.set_index(['group'])
        filter = filter.loc[classification.loc[unaccepted_idx,'valid_AphiaID'].values,:].reset_index()

        classification.loc[unaccepted_idx, COLNAMES] = filter[COLNAMES].values

        # Remove above species taxa

        isabovespecies = (classification['match_type'] == 'match_abovespecies')
#        print(classification.loc[isabovespecies,:]) #debug
        classification.loc[isabovespecies,'classif_matchtype_generatedby_isinworms'] += '_taxonNoSpecies'
        classification.loc[isabovespecies,'taxamatch_generatedby_isinworms'] = 'nomatch'

        # Remove fossils

        if not keep_fossil:

            classification['isExtinct'] = classification['isExtinct'].astype('Int64')
            isfossil = (classification['isExtinct'] == 1)
            classification.loc[isfossil,'classif_matchtype_generatedby_isinworms'] += '_fossil'
            classification.loc[isfossil,'taxamatch_generatedby_isinworms'] = 'nomatch'

    return classification


def clean_taxonomy(classification, matchfilter=None, acceptedfilter=None, check_ambiguity=True, fuzzy=True, verbatimcolumn=None, verbatimauthorshiponly=None, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False, min_length=3, doublecheck=True, store=True, outputdir='./', resume=True, resume_mode='soft', verbose=True, indent='', overwrite=False, parallel=False, max_attempt=3, store_parallel=True, overwrite_parallel=False, resume_parallel=True):

    # Parameters

    params_store = {
                    'outputdir': outputdir,
                    'store': store,
                    'overwrite': overwrite,
                   }

    params_parallel = {
                       'parallel': parallel,
                       'max_attempt': max_attempt,
                       'resume_parallel': resume_parallel,
                       'store_parallel': store_parallel,
                       'overwrite_parallel': overwrite_parallel
                      }

    params_recognized = {
                         'min_length': min_length,
                         'doublecheck': doublecheck,
                         'resume': resume
                        }

    params_accepted = {
                       'resume': resume,
                       'resume_mode': resume_mode
                      }

    # Match WoRMS

    params = {
              'matchfilter': matchfilter,
              'check_ambiguity': check_ambiguity,
              'fuzzy': fuzzy,
              'fixed_allowedMismatch': fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN': fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN': fixed_allowedMismatch_withoutNaN,
              'verbatimauthorshiponly': verbatimauthorshiponly,
              'verbatimcolumn': verbatimcolumn,
              'keep_fossil': keep_fossil,
              'verbose': verbose,
              'indent': indent
             }

    classification = apply_matchfilter(classification, **params, **params_store, **params_parallel, **params_recognized)

    printv('', verbose=verbose)

    # Match accepted WoRMS

    params = {
              'acceptedfilter': acceptedfilter,
              'keep_fossil': keep_fossil,
              'verbose': verbose,
              'indent': indent
             }

    classification = apply_acceptedfilter(classification, **params, **params_store, **params_parallel, **params_accepted)

    printv('', verbose=verbose)

    return classification

def drop(df, drop_nomatch, drop_uncertain, rankcolumns_mapping, wormscolumns_mapping, drop_conditions=None, verbose=True, indent=''):

    if drop_nomatch:

        # Delete taxa that do not match any classification in WoRMS

        if drop_conditions is None:
            drop_conditions = {}
        drop_conditions['taxamatch_generatedby_isinworms'] = ['nomatch']

    if drop_uncertain:

        # Delete taxa that cannot be matched with certainty to a WoRMS classification

        if drop_conditions is None:
            drop_conditions = {}
            drop_conditions['taxamatch_generatedby_isinworms'] = ['uncertain']
        else:
            if 'taxamatch_generatedby_isinworms' in drop_conditions.keys():
                drop_conditions['taxamatch_generatedby_isinworms'].append('uncertain')
            else:
                drop_conditions['taxamatch_generatedby_isinworms'] = ['uncertain']

    if drop_conditions is not None:

        # Delete taxa matching the specified `drop_conditions`

        temp = copy.deepcopy(drop_conditions)
        for key in drop_conditions.keys():
            if key in rankcolumns_mapping.keys():
                temp[rankcolumns_mapping[key]] = temp.pop(key)
            elif key in wormscolumns_mapping.keys():
                temp[wormscolumns_mapping[key]] = temp.pop(key)

        drop_conditions = temp

    if drop_conditions is not None:

        printv(f'* Delete taxa matching the specified conditions', verbose=verbose, indent=indent)
        df = dropvalues.apply(df, **drop_conditions)

    return df

def flag(df, flag_nomatch, flag_uncertain, verbose=True, indent=''):

    flag_conditions = []

    if flag_nomatch:

        # Flag taxa that do not match any classification in WoRMS

        printv(f'* Flag taxa that do not match any classification in WoRMS', verbose=verbose, indent=indent)

        flag_conditions.append('nomatch')

    if flag_uncertain:

        # Flag taxa that cannot be matched with certainty to a WoRMS classification

        printv(f'* Flag taxa that cannot be matched with certainty to a WoRMS classification', verbose=verbose, indent=indent)

        flag_conditions.append('uncertain')

    if len(flag_conditions) != 0:

        df = isin.apply(df, key='taxamatch_generatedby_isinworms', values=flag_conditions, flag=True, verbose=verbose, indent=indent)

    return df

@export
def apply(df, *ignored_args, stdnan=True, wormscall=None, rank_mapping=None, worms_dtypes=None, matchfilter=None, acceptedfilter=None, check_ambiguity=True, fuzzy=True, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, verbatimcolumn=None, verbatimauthorshiponly=None, keep_fossil=False, min_length=3, doublecheck=True, inplace=False, resume=True, resume_mode='soft', store=True, overwrite_createwormsfilters=False, outputdir_createwormsfilters='./', outputdir_isinworms='./', outputfile='', parallel=True, max_attempt=3, store_parallel=True, overwrite_parallel_createwormsfilters=False, resume_parallel=True, drop_conditions=None, flag_nomatch=False, flag_uncertain=False, verbose=True, indent='', overwrite_isinworms=False):

    Nobs = len(df)

    # Parameters

    ## Global variables

    global WORMSCALL, WORMS_DTYPES, RANK_MAPPING, COLNAMES

    if wormscall is not None:
        WORMSCALL = wormscall

    if rank_mapping is not None:
        RANK_MAPPING = rank_mapping

    diff = set(RANK_MAPPING.values()) - set(df.columns)
    if len(diff) != 0:
        raise Exception(f'`isinworms.py` | `RANK_MAPPING`: {list(diff)} not in {list(df.columns)} columns')

    wormsranks = ['scientificname','genus','family','order','cls','phylum','kingdom']

    if len(set(RANK_MAPPING.keys()).symmetric_difference(wormsranks)) != 0:
        raise Exception(f'`isinworms.py` | `RANK_MAPPING` keys should be {wormsranks}')

    missing_keys = set(wormsranks + ['match_type','status','valid_AphiaID', 'rank']) - set(WORMSCALL)
    if len(missing_keys) != 0:
        raise Exception(f'`isinworms.py` | {missing_keys} WoRMS keys are missing in `WORMSCALL`')

#    if (wormscall is not None) or (rank_mapping is not None):
#        COLNAMES = list(set(list(set(WORMSCALL) - set(RANK_MAPPING.keys())) + list(RANK_MAPPING.values())))

    if worms_dtypes is not None:
        WORMS_DTYPES = worms_dtypes

    delkeys = list(set(WORMS_DTYPES.keys()) - set(WORMSCALL))
    for key in delkeys:
        del WORMS_DTYPES[key]

#    missing_dtypes = set(WORMSCALL) - set(WORMS_DTYPES.keys())
#    if len(missing_dtypes) != 0:
#        printv(f'INFO | No dtype specified for: {list(missing_dtypes)}', verbose=verbose, indent=indent)

    ## Arguments

    if parallel and (store != store_parallel):
        raise ValueError(f'`isinworms.py` | parallel={parallel} and store={store} but store_parallel={store_parallel}')

    if parallel and (overwrite_createwormsfilters != overwrite_parallel_createwormsfilters):
        raise ValueError(f'`isinworms.py` | parallel={parallel} and overwrite={overwrite_createwormsfilters} but overwrite_parallel={overwrite_parallel_createwormsfilters}')

    if (not keep_fossil) and ('isExtinct' not in WORMSCALL):
        raise Exception(f"`isinworms.py` | `keep_fossil`={keep_fossil} but 'isExtinct' not in `WORMSCALL`")

    if (drop_conditions is not None) and (not isinstance(drop_conditions, dict)):
        raise TypeError(f'`isinworms.py` | `drop_conditions` must be a dictionary')

#    if drop_nomatch and flag_nomatch:
#        raise ValueError(f'`isinworms.py` | drop_nomatch={drop_nomatch} but flag_nomatch={flag_nomatch}')

#    if drop_uncertain and flag_uncertain:
#        raise ValueError(f'`isinworms.py` | drop_uncertain={drop_uncertain} but flag_uncertain={flag_uncertain}')

    params = {
              'matchfilter': matchfilter,
              'acceptedfilter': acceptedfilter,
              'check_ambiguity': check_ambiguity,
              'fuzzy': fuzzy,
              'fixed_allowedMismatch': fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN': fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN': fixed_allowedMismatch_withoutNaN,
              'verbatimauthorshiponly': verbatimauthorshiponly,
              'verbatimcolumn': verbatimcolumn,
              'keep_fossil': keep_fossil,
              'min_length': min_length,
              'doublecheck': doublecheck,
              'resume': resume,
              'resume_mode': resume_mode,
              'verbose': verbose,
              'indent': indent
             }


    params_store = {
                    'outputdir': outputdir_createwormsfilters,
                    'store': store,
                    'overwrite': overwrite_createwormsfilters,
                   }


    params_parallel = {
                       'parallel': parallel,
                       'max_attempt': max_attempt,
                       'resume_parallel': resume_parallel,
                       'store_parallel': store_parallel,
                       'overwrite_parallel': overwrite_parallel_createwormsfilters
                      }

#    rankkeys = list(RANK_MAPPING.keys())
#    rankcolumns = list(itemgetter(*rankkeys)(RANK_MAPPING))
#    print(rankkeys) #debug
#    print(rankcolumns) #debug
#    rankcolumns = list(RANK_MAPPING.values())
#    wormscolumns = list(set(WORMSCALL) - set(RANK_MAPPING.keys()))

    rankcolumns_mapping = {}
    for key,rank in RANK_MAPPING.items():
        df, rankin, rankout = getcolumnname.apply(df, rank, 'isinworms', inplace)
        RANK_MAPPING_RENAMED[key] = rankin
        rankcolumns_mapping[rankin] = rankout

    rankcolumns = list(RANK_MAPPING_RENAMED.values())
    wormscolumns = list(set(WORMSCALL) - set(RANK_MAPPING_RENAMED.keys()))
    wormscolumns_mapping = {column : column + '_generatedby_isinworms' for column in wormscolumns}
    WORMS_DTYPES_RENAMED = {wormscolumns_mapping[column]:WORMS_DTYPES[column] for column in WORMS_DTYPES.keys()}
    COLNAMES = list(set(WORMSCALL) - set(RANK_MAPPING_RENAMED.keys())) + list(RANK_MAPPING_RENAMED.values())

    if verbatimcolumn is not None:

        # use authorship, if any

        if verbatimauthorshiponly is None:
            verbatimauthorshiponly = [False]*len(verbatimcolumn)

        if len(verbatimcolumn) != len(verbatimauthorshiponly):
            raise Exception(f'`isinworms.py` | `verbatimcolumn` has a length of {len(verbatimcolumn)}, whereas `verbatimauthorshiponly` has a length of {len(verbatimauthorshiponly)}')

        if ('authority' not in WORMSCALL):
            raise Exception(f"`isinworms.py` | `verbatimcolumn` is not None, but 'authority' not in `WORMSCALL`")

        if isinstance(verbatimcolumn,str):
            verbatimcolumn = [verbatimcolumn]
        for i,col in enumerate(verbatimcolumn):
            df, verbatimcolumn[i], _ = getcolumnname.apply(df, col, '', inplace=True)

        columns = list(set(rankcolumns + verbatimcolumn))

    else:

        # no authorship

        columns = rankcolumns

    if Nobs == 0:

        # no observations

        colnames = list(set(df.columns.tolist() + list(rankcolumns_mapping.values()) + ['classif_matchtype_generatedby_isinworms', 'taxamatch_generatedby_isinworms'] + list(wormscolumns_mapping.values())))
        if check_ambiguity:
            colnames += ['issue_isinworms']

        df = df.reindex(colnames, axis='columns')

        return df

    # Convert all missing values in `columns` columns to pd.NA

    if stdnan:
        df = standardizenan.apply(df, key=rankcolumns, letters_only=True)
        if verbatimcolumn is not None:
            coldiff = list(set(verbatimcolumn) - set(rankcolumns))
            df = standardizenan.apply(df, key=coldiff, letters_only=False)

    # Pre-process the raw scientific names
    # to avoid quotation mark problems with pandas

    tempspecies = rankcolumns_mapping[RANK_MAPPING_RENAMED['scientificname']]
    df[tempspecies] = preprocessquotationmark.apply(df[RANK_MAPPING_RENAMED['scientificname']])
    speidx = columns.index(RANK_MAPPING_RENAMED['scientificname'])
    columns[speidx] = tempspecies

    # Get unique classifications

    dfByClassification = df.loc[~pd.isnull(df[tempspecies]), columns].fillna('_MISSING_').groupby(columns, dropna=False) #get_group() doesn't work with NaN
    columns[speidx] = RANK_MAPPING_RENAMED['scientificname']
    taxonomy = pd.DataFrame(list(dfByClassification.groups.keys()), columns=columns)

    # Get WoRMS-accepted classifications associated with these classifications, if any

    printv('', verbose=verbose)

    if len(taxonomy) == 0:
        classification = pd.DataFrame([],columns=COLNAMES)
    else:
        classification = clean_taxonomy(taxonomy.replace('_MISSING_',pd.NA), **params, **params_store, **params_parallel)

#        print('classification len:', len(classification)) #À SUPPRIMER APRES DEBUG (il peut y en avaoir moins dans classification car suppression des nomatch
#        print('taxonomy len:', len(taxonomy))
#        idx_test=classification.index[0]
#        print('check:', taxonomy.loc[idx_test,:])
#        print('check:', classification.loc[idx_test,:])

    # Convert WORMS-specific column dtypes

    for key, value in WORMS_DTYPES.items():
        if 'int' in value.lower():
            classification[key] = classification[key].astype('Float64').astype(value)
        else:
            classification[key] = classification[key].astype(value)

    # Standardize taxonomy

    ## Prepare the dataframe

    df['classif_matchtype_generatedby_isinworms'] = 'taxonNoSpecies' # species field is null
    df['taxamatch_generatedby_isinworms'] = 'nomatch'
    df['classif_matchtype_generatedby_isinworms'] = df['classif_matchtype_generatedby_isinworms'].astype('string')
    df['taxamatch_generatedby_isinworms'] = df['taxamatch_generatedby_isinworms'].astype('string')

    if check_ambiguity:
        df['issue_isinworms'] = pd.NA
        df['issue_isinworms'] = df['issue_isinworms'].astype('string')

    wormscolumns = list(wormscolumns_mapping.values())
    df[wormscolumns] = pd.NA
    df[wormscolumns] = df[wormscolumns].astype(WORMS_DTYPES_RENAMED)

    rankcolumns = list(rankcolumns_mapping.values())
    if not inplace:
        df[rankcolumns] = pd.NA
#    df[rankcolumns] = df[rankcolumns].astype('string')

    ## Apply the standardized taxonomy

    printv(f'* Standardization via WoRMS', verbose=verbose, indent=indent)

    classification_indexes = classification.index.tolist()
    classification_columns = classification.columns.tolist()

    target_columns = []
    for column in classification_columns:
        try:
            target_columns.append(rankcolumns_mapping[column])
        except KeyError:
            try:
                target_columns.append(wormscolumns_mapping[column])
            except KeyError:
                target_columns.append(column)

    if verbose:
        process = tqdm(classification_indexes, desc=indent + 'Progress')
    else:
        process = classification_indexes
    for idx in process:
        group = tuple(taxonomy.loc[idx,columns].values)
        indexes = dfByClassification.get_group(group).index
        df.loc[indexes, target_columns] = classification.loc[idx, classification_columns].values

#    df[wormscolumns] = df[wormscolumns].astype(WORMS_DTYPES_RENAMED)
    if check_ambiguity:
        df['issue_isinworms'] = df['issue_isinworms'].astype('string')

    df[wormscolumns_mapping['rank']] = df[wormscolumns_mapping['rank']].str.upper()

    printv('', verbose=verbose)

    # Filter taxa

    df = drop(df, drop_nomatch=(not flag_nomatch), drop_uncertain=(not flag_uncertain), drop_conditions=drop_conditions, rankcolumns_mapping=rankcolumns_mapping, wormscolumns_mapping=wormscolumns_mapping, verbose=verbose, indent=indent)
    df = flag(df, flag_nomatch, flag_uncertain, verbose=verbose, indent=indent)

    # Store

    if store:

        if len(outputfile) == 0:
            outputfile = os.path.join(outputdir_isinworms, 'marinedata_processedby_isinworms.txt')
        if len(os.path.dirname(outputfile)) == 0:
            outputfile = os.path.join(outputdir_isinworms, outputfile)

        if os.path.isfile(outputfile):
            if not overwrite_isinworms:
                with open(outputfile,'r') as f:
                    header = f.readline().strip('\n').split('\t')
                df = df[header]
            else:
                printv('', verbose=verbose)
                printv(f'WARNING | {outputfile} already exists and will be overwritten', verbose=verbose, indent=indent)
        else:
            overwrite_isinworms = True

        printv('', verbose=verbose)
        writedataframe.to_txt(df, outputfile, init=overwrite_isinworms, verbose=verbose, indent=indent)

    printv('', verbose=verbose)

    return df


#À SUPPRIMER APRES DEBUG

def applyTOgz(gzfile,idcol,**params):

    outputfile = os.path.join(params['outputdir'],params['outputfile'])
    init=True
    docontinue=False

    if os.path.isfile(outputfile):

        print(f'INFO | {outputfile} exists and will be used')

#        with open(outputfile,'r') as processed_data:

#            header = processed_data.readline().strip('\n').split('\t')
#            id_index = header.index(idcol)

#            for line in processed_data:
#                line = line.strip('\n').split('\t')
#                idprocessed.append(int(line[id_index]))
#                last = int(line[id_index])
#            init=False #DEBUG
#            print("last:",last) #DEBUG
        last = 1624092725
        init=False
        docontinue=True
        print("last:",last)

#    print('INFO | Number of lines processed:',len(idprocessed))

    BATCH_SIZE=100000

    with gzip.open(gzfile,'r') as gbif_data:

        header = gbif_data.readline().decode("utf8").strip('\n').split('\t')
        header_length = len(header)
        id_index = header.index(idcol)

        batch = 0
        data2clean = []
        error = 0
        start=time.time()

        for idx, line in enumerate(gbif_data):

#           if idx<174650000:
#                continue

            # Add observations

            obs = line.decode("utf8").strip('\n').split('\t')
            obs = [preprocessquotationmark.apply(val) for val in obs]

            if len(obs)==header_length:

                 if docontinue:
                    id = int(obs[id_index])
                    if id==last:
                        docontinue=False
                    if (idx+1)%100000==0:
                        print(f'Processing | {idx+1} lines done (processed={len(idprocessed)}, data2clean={len(data2clean)})')
                 else:
                     data2clean.append(obs)
                     batch += 1

            else:

                error += 1
                print(f'SplittingError: splitting gives more fields than columns line n°{idx}, the value will be ignored')
                print(f'line n°{idx}: {line}')


            if batch==BATCH_SIZE:

                df2clean = pd.DataFrame(data2clean,columns=header)

                # Process data
                print()
                print(f'Processing | {idx+1} lines done')
                _ = apply(df2clean,**params,overwrite_isinworms=init)

                end=time.time()
                print()
                print(f'TIME : {np.round(end-start,0)}s')

                init=False
                data2clean.clear()
                batch=0
                start=time.time()

    if batch!=0:

        df2clean = pd.DataFrame(data2clean,columns=header)

        # Process data
        print()
        print(f'Processing | {idx+1} lines done')
        _ = apply(df2clean,**params,overwrite_isinworms=init)

        end=time.time()
        print()
        print(f'TIME : {np.round(end-start,0)}s')

    return True

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Create WoRMS filters')
#    parser.add_argument('data_txtfile', type=str, help='path to the tab-separated file to be processed')
    parser.add_argument('gzfile', type=str, help='path to the tab-separated file to be processed')
    parser.add_argument('--wormscall', nargs='*', type=str, help='list containing the WoRMS variables to keep', default=WORMSCALL)
    parser.add_argument('--worms_dtypes', type=json.loads, help='dictionary of the dtypes of WoRMS-specific columns', default=json.dumps(WORMS_DTYPES))
    parser.add_argument('--matchfilter_txtfile', type=str, help='path to the WoRMS match filter', default=None)
    parser.add_argument('--acceptedfilter_txtfile', type=str, help='path to the WoRMS accepted filter', default=None)
    parser.add_argument('--check_ambiguity', action=argparse.BooleanOptionalAction, help='check if a different order of the matching criteria would have led to a different result', default=True)
    parser.add_argument('--fuzzy', action=argparse.BooleanOptionalAction, help='fuzzy or exact matching on higher ranks', default=True)
    parser.add_argument('--fixed_allowedMismatch', action=argparse.BooleanOptionalAction, help='set a fixed number of allowed mismatches for higher ranks, regardless of missing values', default=False)
    parser.add_argument('--fixed_allowedMismatch_withNaN', type=int, help='number of allowed mismatches for higher ranks with missing values', default=1)
    parser.add_argument('--fixed_allowedMismatch_withoutNaN', type=int, help='number of allowed mismatches for higher ranks without missing values', default=2)
    parser.add_argument('--verbatimcolumn', nargs='*', type=str, help='columns containing authorship information', default=None)
    parser.add_argument('--verbatimauthorshiponly', nargs='*', type=str, help='`verbatimcolumn` contains only authorship information', default=None) #False avant CHECK FUNC
    parser.add_argument('--keep_fossil', action=argparse.BooleanOptionalAction, help='keep fossil taxa', default=False)
    parser.add_argument('--min_length', type=int, help='minimum length of the words comprising the scientific name', default=3)
    parser.add_argument('--doublecheck', action=argparse.BooleanOptionalAction, help='double-check or not three-word scientific names by querying only the first two words', default=True)
    parser.add_argument('--store', action=argparse.BooleanOptionalAction, help='whether to store the filters', default=True)
    parser.add_argument('--outputdir', type=str, help='path to folder where files will be stored', default='./')
    parser.add_argument('--outputfile', type=str, help='name or path to the output file', default='')
    parser.add_argument('--overwrite_createwormsfilters', action=argparse.BooleanOptionalAction, help='overwrite existing `createwormsfilters` filters', default=False)
    parser.add_argument('--resume', action=argparse.BooleanOptionalAction, help='reuse existing filters and temporary files', default=True)
    parser.add_argument('--resume_mode', type=str, help="whether to keep all previously retrieved data ('soft') or only the currently requested ones ('hard')", default='soft')
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, help='parallelize requests (maximum 2 CPUs)', default=False)
    parser.add_argument('--max_attempt', type=int, help='maximum number of retries in case of errors when running in parallelized mode', default=3)
    parser.add_argument('--store_parallel', action=argparse.BooleanOptionalAction, help='whether to store the filters in parallelized mode', default=True)
    parser.add_argument('--overwrite_parallel_createwormsfilters', action=argparse.BooleanOptionalAction, help='overwrite existing `createwormsfilters` filters in parallelized mode', default=False)
    parser.add_argument('--resume_parallel', action=argparse.BooleanOptionalAction, help='reuse existing filters in parallelized mode', default=True)
    parser.add_argument('--drop_conditions', type=json.loads, help='dictionary {"key":"value"} specifying drop conditions', default=None)
    # drop_conditions format: '{"key":"value"}'
    parser.add_argument('--overwrite_isinworms', action=argparse.BooleanOptionalAction, help='overwrite existing `isinworms` output file', default=False)

    args = parser.parse_args()

    verbatimauthorshiponly = []
    if (args.verbatimauthorshiponly is not None):

        for idx,value in enumerate(args.verbatimauthorshiponly):

            if value in ['True','False']:
                value = (value == 'True')
                verbatimauthorshiponly.append(value)

            else:
                raise ValueError(f'`isinworms.py` | `verbatimauthorshiponly` must be True or False, but `verbatimauthorshiponly[{idx}]`={value}')

    if len(args.outputfile) == 0:
        outputfile = args.data_txtfile.split('.')[0].split('/')[-1]
        outputfile = outputfile + '_processedby_isinworms.txt'
    else:
        outputfile = args.outputfile

#    df = pd.read_csv(args.data_txtfile, sep='\t', low_memory=False)
    matchfilter = pd.read_csv(args.matchfilter_txtfile, sep='\t', low_memory=False)
    acceptedfilter = pd.read_csv(args.acceptedfilter_txtfile, sep='\t', low_memory=False)

    print_params = {
                    #'data': args.data_txtfile,
                    'matchfilter': args.matchfilter_txtfile,
                    'acceptedfilter': args.acceptedfilter_txtfile
                   }

    params = {
              'gzfile':args.gzfile,
              'wormscall': args.wormscall,
              'worms_dtypes': args.worms_dtypes,
              'check_ambiguity': args.check_ambiguity,
              'fuzzy': args.fuzzy,
              'fixed_allowedMismatch': args.fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN': args.fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN': args.fixed_allowedMismatch_withoutNaN,
              'verbatimcolumn': args.verbatimcolumn,
              'verbatimauthorshiponly': verbatimauthorshiponly,
              'keep_fossil': args.keep_fossil,
              'min_length': args.min_length,
              'doublecheck': args.doublecheck,
              'resume' : args.resume,
              'resume_mode' : args.resume_mode,
              'store': args.store,
              'overwrite_createwormsfilters': args.overwrite_createwormsfilters,
              'outputdir': args.outputdir,
              'outputfile': outputfile,
              'parallel': args.parallel,
              'max_attempt': args.max_attempt,
              'resume_parallel': args.resume_parallel,
              'store_parallel': args.store_parallel,
              'overwrite_parallel_createwormsfilters': args.overwrite_parallel_createwormsfilters,
              'drop_conditions':args.drop_conditions,
              'inplace': False
             }


    print_params.update(params)

    params['matchfilter'] = matchfilter
    params['acceptedfilter'] = acceptedfilter

    print()
    print('    Parameters')
    print('    ----------')
    for key, value in print_params.items():
        print(f'    {key}: {value}')
    print()

    start=time.time()

    #_ = apply(df, **params)
    applyTOgz(**params, idcol='gbifID')

    end=time.time()

    print(f'    TIME : {round(end - start,0)}s')
