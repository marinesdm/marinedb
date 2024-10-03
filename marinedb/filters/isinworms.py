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

import time

# Local imports

from marinedb.filters import createwormsfilters as cwf
from marinedb.filters import dropvalues
from marinedb.filters import subsetranks
from marinedb.utils import regexstrip
from marinedb.utils import getdefaultargs

# Global variables

# Rank names in the file to be processed
# schema: RANK = {rank_name: rank_name_in_the_file}
# ! do not change `rank_name`, modify only `rank_name_in_the_file`, if necessary
RANK = {
        'species':'species',
        'genus':'genus',
        'family':'family',
        'order':'order',
        'class':'class',
        'phylum':'phylum',
        'kingdom':'kingdom'
       }

# Mapping custom vocabulary to WoRMS vocabulary
# ! custom vocabulary must be the same as that used in createwormsfilters.py,
# ! if filters have been created upstream
worms_mapping = {
                  RANK['species']:'scientificname',
                  RANK['genus']:'genus',
                  RANK['family']:'family',
                  RANK['order']:'order',
                  RANK['class']:'cls',
                  RANK['phylum']:'phylum',
                  RANK['kingdom']:'kingdom',
                  'worms_matchtype':'match_type',
                  'worms_status':'status',
                  'valid_aphiaID':'valid_AphiaID',
                  'isextinct':'isExtinct',
                  'rank':'rank',
                  'authority':'authority'
                 }

# WORMS-specific column dtypes
worms_dtypes = {'worms_matchtype':'string',
                'worms_status':'string',
                'valid_aphiaID':'Int64',
                'isextinct':'Int64',
                'rank':'string'}


#Number of mismatches allowed according to the number of missing values
NaN2AllowedMismatch = {0:2,
                       1:2,
                       2:1,
                       3:0,
                       4:0,
                       5:0,
                       6:-1}


class NotImplemented(Exception): #À SUPPRIMER APRES DEBUG
    pass

def resume_process(filter, values):

    valuesprocessed = set(filter['group'].tolist())
    values2process = set(values) - valuesprocessed

    return list(values2process)

def handlenan(func):

    @wraps(func)
    def nanfunc(df, keys, **options):

        if isinstance(keys, str):
            keys = [keys]

        # Process cases with only missing values separately (return pd.NA)
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

    temp = pd.concat([series1,series2], axis="columns")
    isallnan = temp.isna().all(axis="columns")

    # Process cases with only missing values separately (return pd.NA)
    res = pd.Series([pd.NA]*len(series1), dtype='boolean', index=series1.index.to_list())
    res[~isallnan] = series1[~isallnan].eq(series2[~isallnan])

    return res


def elementwise_LevensteinRatio(strings, refstrings, difflib_cutoff=0.5): #!one-way

    if pd.isnull(refstrings) or len(refstrings)==0 or pd.isnull(strings) or len(strings)==0:
        return pd.NA, pd.NA

    # Preparing strings
    refstrings = clean_split_strings(refstrings)
    strings = clean_split_strings(strings)

    ratio=0
    Nmatch=0
    for string in strings:

        ## Find the component closest to `string` in `refstrings`
        stringbestmatch = get_close_matches(string, refstrings, n=1, cutoff=difflib_cutoff) #difflib: cutoff=0.6 by default

        ## Compute the Levenstein ratio between `string` and `stringbestmatch`
        if len(stringbestmatch)!=0:
            Nmatch+=1
            stringbestmatch=stringbestmatch[0]
            ratio+=Levenshtein.ratio(string, stringbestmatch)
            del refstrings[refstrings.index(stringbestmatch)]

    return np.round(ratio/len(strings),2), Nmatch


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
        pattern="\s((and)|(et)|(und)|[yie])\s"
        strings=re.sub(pattern, ' ', strings)

    # Split `authors` into author names (or components of author names)

    strings=np.array(re.split(r'\s+',strings))

    # Clean authors' names

    keep=[]
    for i, string in enumerate(strings):
        strings[i]=clean_string(string)
        if len(strings[i])!=0:
            keep.append(i)

    # Keep only non-empty strings

    return list(strings[keep])


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

        # Find the component closest to `string` in `verbatimspecies`
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

    if pd.isnull(authorship) or len(authorship)==0: # i.e pd.NA or authorship==''
        return pd.NA, pd.NA, pd.NA

    # Find the date if there is one

    pattern=r'[0-9]{4}'
    res=re.finditer(pattern,authorship)
    match = [m for m in res]

    # Find the author(s)

    if len(match)>1:

        # More than one date

        raise Exception

    elif len(match)==0:

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

        elif authorship[start-1]=="(" and authorship[stop]!=")":

            # Date preceded by a parenthesis
            # Find the closing parenthesis

            res=re.fullmatch(fr"(?P<more1>.*?)\({authorship[start:stop]}(?P<author>.+)\)(?P<more2>.*)", authorship)

            if res:

                # assumption : the text up to the last closing parenthesis corresponds to the authors' names
                # i.e more (date author) more
                author = regexstrip.apply(res['author'],r'[^a-zA-Z0-9]+')
                more = regexstrip.apply(res['more1'],r'[^a-zA-Z0-9]+') + regexstrip.apply(res['more2'],r'[^a-zA-Z0-9]+')
                processed=True

            else:
                processed=False

        elif authorship[stop]==")" and authorship[start-1]!="(":

            # Date followed by a parenthesis
            # Find the opening parenthesis

            res=re.fullmatch(fr"(?P<more1>.*?)\((?P<author>.+?){authorship[start:stop]}\)(?P<more2>.*)", authorship)

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
                # assumption: the string preceding the date corresponds to the authors' names, in accordance with conventions
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

    if pd.isnull(refauthors) or len(refauthors)==0 or pd.isnull(authors) or len(authors)==0:
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

    authorship["date"]=authorship["date"].astype('Int64')
    refauthorships["date"]=refauthorships["date"].astype('Int64')

    refauthorships["datematch_diff"]=pd.NA
    refauthorships["datematch"]=pd.NA
    refauthorships["authormatch_ratio"]=pd.NA
    refauthorships["authormatch"]=pd.NA

    # Date match

    if any(~pd.isnull(authorship["date"])):

        refauthorships["datematch_diff"] = np.abs(refauthorships["date"] - authorship.loc[0,"date"])
        refauthorships["datematch"] = (refauthorships["datematch_diff"] <= date_tolerance)
        refauthorships.loc[(pd.isnull(refauthorships["date"])),"datematch"] = pd.NA

        index = refauthorships[(pd.isnull(refauthorships["date"])) | (refauthorships["datematch"])].index
        index = list(index)

    else:
        # no date
        index = list(refauthorships.index)

    # Author match

    params = {'difflib_cutoff':difflib_cutoff,
              'levenshtein_tolerance':levenshtein_tolerance,
              'author_tolerance':author_tolerance}

    for i, refauthors in enumerate(refauthorships.loc[index,"author"]):
        refauthorships.loc[index[i],["authormatch","authormatch_ratio"]] = _match_AuthorshipByAuthors(refauthors, authorship.loc[0,"author"], **params)

    # Final match
    # date and author must both match when known,
    # otherwise date or author, whichever is known, must match

    refauthorships["match"] = pdmin(refauthorships, ["datematch","authormatch"], axis=1, skipna=True).astype('boolean')
    refauthorships["datematch_diff"] = refauthorships["datematch_diff"].astype("Int64")
    refauthorships["authormatch_ratio"] = refauthorships["authormatch_ratio"].astype("Float64")

    return refauthorships


def _match_TaxaByAuthorship(verbatim, candidates, date_tolerance=2, difflib_cutoff=0.5, levenshtein_tolerance=0.7, author_tolerance=0.7): #species, authorship, worms status dataframe #same species

    params = {'date_tolerance':date_tolerance,
              'difflib_cutoff':difflib_cutoff,
              'levenshtein_tolerance':levenshtein_tolerance,
              'author_tolerance':author_tolerance}

    candidates[["sensu_conflict","match","datematch","datematch_diff","authormatch","authormatch_ratio"]]=pd.NA
    candidates[["sensu_conflict","match","datematch","authormatch"]]=candidates[["sensu_conflict","match","datematch","authormatch"]].astype("boolean")
    candidates["datematch_diff"]=candidates["datematch_diff"].astype("Int64")
    candidates["authormatch_ratio"]=candidates["authormatch_ratio"].astype("Float64")
    ismore = False

    if pd.isnull(verbatim) or (len(verbatim)==0):
        return candidate, ismore

    try:
        verbatim = verbatim.encode('latin-1').decode('utf-8')
    except UnicodeDecodeError:
        pass
    verbatim = unidecode(verbatim.strip())
    speidx = candidates.columns.to_list().index(RANK["species"])
    wormsspecies = unidecode(candidates.iloc[0,speidx].strip())

    # Find the species name in `verbatim`

    ## Determine the spelling of the species name components in `verbatim` using `wormsspecies`
    # i.e take misspelling into account e.g. "Clatria rubens" for "Clathria rubens"

    if "worms_status" in candidates.columns:
        status = candidates["worms_status"].tolist()
        if "phonetic" in status:
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
        wormsspecies_pattern = "".join(fr'{string}(?P<more{i}>.*?)' for i,string in enumerate(wormsspecies_split[:-1])) + wormsspecies_split[-1]
        speciesmatch = re.search(fr'(?<![a-zA-Z]){wormsspecies_pattern}', verbatim, flags=re.IGNORECASE)

        if speciesmatch: # species name found

            # Put aside the species name to find the authorship information

            start, end = speciesmatch.span()
            verbatim_species = verbatim[start:end]
            verbatim_authorship = verbatim[:start] + verbatim[end:]

            more = "".join(speciesmatch.groups())
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

        candidates["match"] = True
        #candidates[["sensu_conflict","datematch_diff","datematch","authormatch_ratio","authormatch"]]=pd.NA

    else:

        # Authorship match

        ## Does verbatim authorship contain "sensu"?

        doescontainsensu_verbatim = ("sensu" in verbatim_authorship)

        ## Do the authorship candidates contain "sensu"?

        doescontainsensu_candidates = candidates["authorship"].str.contains("sensu")

        ## Are there "sensu" conflicts between verbatim and authorship candidates?
        # `verbatim_authorship` does not contain "sensu" & one or more candidates contain "sensu"
        #  OR
        # `verbatim_authorship` contain "sensu" & one or more candidates does not contain "sensu"

        candidates["sensu_conflict"] = False
        candidates.loc[doescontainsensu_candidates!=doescontainsensu_verbatim, "sensu_conflict"] = True

        if doescontainsensu_verbatim:

            # `verbatim_authorship` contains "sensu"

            verbatim_authorship = verbatim_authorship.split("sensu")

            if len(verbatim_authorship)>2:

                # more than one "sensu": unexpected

                raise NotImplemented(f'More than one "sensu" in the authorship ({verbatim}).') #pour le débug, à supprimer ensuite
                #print(f"WARNING | More than one 'sensu' in {verbatim}. Exit `_match_TaxaByAuthorship`.")
                #return None

            # for candidates not containing "sensu", no match is possible

            candidates.loc[~doescontainsensu_candidates, "match"] = False
            candidates_authorships = candidates.loc[doescontainsensu_candidates,["authorship"]].copy()

        else:

            # `verbatim_authorship` does not contain "sensu"
            # but one or more candidates may contain "sensu"
            # and `verbatim_authorship` could match one of the authors of these candidates

            candidates_authorships = candidates[["authorship"]].copy()


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

            candidates_sensusplit = candidates_authorships["authorship"].str.split("sensu")

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
            verbatim_authorship=pd.DataFrame([verbatim_authorship], columns=["date1","author1","more1", "date2", "author2", "more2"])

            if any(verbatim_authorship["more1"].str.len()>0) or any(verbatim_authorship["more2"].str.len()>0):
                ismore=True

            # `candidates_authorships`

            candidates_authorships["authorship1"] = candidates_sensusplit.str[0]
            candidates_authorships["authorship2"] = candidates_sensusplit.str[1] #pd.NA if len<2
            index = candidates_authorships.index.to_list()

            for i, authorship in enumerate(candidates_authorships[["authorship1","authorship2"]].values):
                candidates_authorships.loc[index[i],["date1","author1","more1"]] = split_authorship(authorship[0])
                candidates_authorships.loc[index[i],["date2","author2","more2"]] = split_authorship(authorship[1])

            ## Match authorships, both before and after "sensu", by date and author

            colmap1, colmap2 = {'date1':'date','author1':'author'}, {'date2':'date','author2':'author'}
            res1 =_match_AuthorshipsByDatesAuthors(candidates_authorships[list(colmap1.keys())].rename(columns=colmap1), verbatim_authorship[list(colmap1.keys())].rename(columns=colmap1), **params)
            res2 =_match_AuthorshipsByDatesAuthors(candidates_authorships[list(colmap2.keys())].rename(columns=colmap2), verbatim_authorship[list(colmap2.keys())].rename(columns=colmap2), **params)

            columns = ["match","datematch","datematch_diff","authormatch","authormatch_ratio"]

            res1, res2 = res1[columns], res2[columns]
            colmap1 = dict(zip(res1.columns, (res1.columns + "1")))
            colmap2 = dict(zip(res2.columns, (res2.columns + "2")))
            res1 = res1.rename(columns=colmap1)
            res2 = res2.rename(columns=colmap2)
            candidates_authorships = pd.concat([candidates_authorships,res1[list(colmap1.values())],res2[list(colmap2.values())]],axis=1)

            ## Final match

            # if `verbatim_authorship` does not contain "sensu":
            #   for candidates containing "sensu" (i.e sensu_conflict=True), `verbatim_authorship` must match one of the candidates' authors
            #     if `verbatim_authorhip` matches a candidate's two authors, store the best match information, if any
            #       if the best match is not obvious, keep the information of the candidate whose author is the best match

            doescandidatecontain = (candidates.index.isin(index)) & (candidates["sensu_conflict"])

            if any(doescandidatecontain):

                doescandidatecontain = doescandidatecontain[doescandidatecontain].index.to_list()

                temp = candidates_authorships.loc[doescandidatecontain,:].copy()
                temp_match = temp[["match1","match2"]].sum(axis=1)

                # No match

                index_nomatch = temp_match[temp_match==0].index.to_list()
                if len(index_nomatch)!=0:
                    candidates.loc[index_nomatch,"match"]=False

                idx1 = []
                idx2 = []

                # Only one match

                index_singlematch = temp_match[temp_match==1].index.to_list()
                if len(index_singlematch)!=0:
                    singlematch = idxmax(temp.loc[index_singlematch,:], ["match1","match2"], axis=1, skipna=True)
                    idx1 = idx1 + singlematch[singlematch=="match1"].index.to_list()
                    idx2 = idx2 + singlematch[singlematch=="match2"].index.to_list()

                # More than one match

                index_morematch = temp_match[temp_match>1].index.to_list()
                if len(index_morematch)!=0:

                    #(~morematch_eqauthors) & (~morematch_eqdates) & (morematch_eqbest) : best author (equivalent to best date)
                    #(~morematch_eqauthors) & (~morematch_eqdates) & (~morematch_eqbest) : if conflict between best author and best date, best author by default
                    #(~morematch_eqauthors) & (morematch_eqdates) : best author
                    #(morematch_eqauthors) & (~morematch_eqdates) : best date
                    #(morematch_eqauthors) & (morematch_eqdates) : best author (equivalent to best date)

                    morematch = temp.loc[index_morematch,:]

                    morematch_eqauthors = ((morematch["authormatch_ratio1"]-morematch["authormatch_ratio2"]).abs() <= 1e-2)
                    isnull = morematch[["authormatch_ratio1","authormatch_ratio2"]].isna().sum(axis=1)
                    morematch_eqauthors[isnull==1] = False
                    morematch_eqauthors[isnull==2] = True

                    morematch_eqdates = naneqsingle(morematch["datematch_diff1"], morematch["datematch_diff2"])
                    morematch_eqdates[pd.isnull(morematch_eqdates)] = True

                    morematch_bestauthor = idxmax(morematch, ["authormatch_ratio1","authormatch_ratio2"], axis=1, skipna=True).str[-1]
                    morematch_bestdate = idxmin(morematch, ["datematch_diff1","datematch_diff2"], axis=1, skipna=True).str[-1]

                    conditions11 = (morematch_eqauthors) & (~morematch_eqdates) & (morematch_bestdate=="1")
                    conditions12 = ((~morematch_eqauthors) | (morematch_eqdates)) & (morematch_bestauthor=="1")
                    idx1 = idx1 + morematch[conditions11 | conditions12].index.to_list()

                    conditions21 = (morematch_eqauthors) & (~morematch_eqdates) & (morematch_bestdate=="2")
                    conditions22 = ((~morematch_eqauthors) | (morematch_eqdates)) & (morematch_bestauthor=="2")
                    idx2 = idx2 + morematch[conditions21 | conditions22].index.to_list()


                if len(idx1)!=0:
                    candidates.loc[idx1, columns] = candidates_authorships.loc[idx1,list(itemgetter(*columns)(colmap1))].values
                if len(idx2)!=0:
                    candidates.loc[idx2, columns] = candidates_authorships.loc[idx2,list(itemgetter(*columns)(colmap2))].values

            # else:
            #   both authorships must match when known
            #   otherwise, whichever is known, must match

            doescandidateequal = (candidates.index.isin(index)) & (~candidates["sensu_conflict"])
            doescandidateequal = doescandidateequal[doescandidateequal].index.to_list()

            candidates.loc[doescandidateequal,"match"] = pdmin(candidates_authorships.loc[doescandidateequal,:],["match1","match2"], axis=1, skipna=True).astype("boolean")
            candidates.loc[doescandidateequal,"datematch"] = pdmin(candidates_authorships.loc[doescandidateequal,:],["datematch1","datematch2"], axis=1, skipna=True).astype("boolean")
            candidates.loc[doescandidateequal,"authormatch"] = pdmin(candidates_authorships.loc[doescandidateequal,:],["authormatch1","authormatch2"], axis=1, skipna=True).astype("boolean")
            candidates.loc[doescandidateequal,"datematch_diff"] = candidates_authorships.loc[doescandidateequal,["datematch_diff1","datematch_diff2"]].sum(axis=1, skipna=True, min_count=1).astype('Int64')
            candidates.loc[doescandidateequal,"authormatch_ratio"] = pdmean(candidates_authorships.loc[doescandidateequal,:],["authormatch_ratio1","authormatch_ratio2"], axis=1, skipna=True).astype('Float64')

    return candidates, ismore  #if ismore & all(~candidates["match"]), new WoRMS request with verbatim


def _match_TaxaByVerbatim(verbatim, candidates, verbatimcolumn=None, verbatimauthorshiponly=False):

    processed = False
    classif = None

    if pd.isnull(verbatim) or (len(verbatim)==0):
        return candidates, processed, classif

    # Match taxa by verbatim authorship

    candidates, ismore = _match_TaxaByAuthorship(verbatim, candidates)
    candidates = candidates[candidates["match"]]

    if len(candidates)==0:

        # No match

        if ismore and (not verbatimauthorshiponly):

            # other information available but not used

            match_idx = None
            classif = ["ismore"] + [pd.NA]*len(wormscolumns)

        else:

            match_idx = None
            classif = ["nomatch"] + [pd.NA]*len(wormscolumns)

       processed = True

    elif len(candidates)==1:

        # Only one match

        match_idx = candidates.index[0]
        classif = ["singleVerbatimMatch"] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
        processed = True

    else:

        # More than one match

        if not all(candidates["authormatch_ratio"].isna()):

            # Keep the candidate that best matches the verbatim author names

            candidates = candidates[~pd.isnull(candidates["authormatch_ratio"])]
            max_authormatch_ratio = candidates["authormatch_ratio"].max()
            candidates = candidates[(max_authormatch_ratio - candidates["authormatch_ratio"])<=1e-2]

            if len(candidates)==1:

                # Only one match

                match_idx = candidates.index[0]
                classif = ["bestAuthorMatch"] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
                processed = True

        if (not processed) and (not all(candidates["datematch_diff"].isna())):

            # Keep the candidate that best matches:
            # - the verbatim author names, if any
            # - and the verbatim authorship date

            candidates = candidates[~pd.isnull(candidates["datematch_diff"])]
            min_datematch_diff = candidates["datematch_diff"].min()
            candidates = candidates[candidates["datematch_diff"]==min_datematch_diff]

            if len(candidates)==1:

                # Only one match

                match_idx = candidates.index[0]
                classif = ["bestDateMatch"] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
                processed = True

        if (not processed) and (not all(candidates["sensu_conflict"].isna())):

            # Keep the candidate that best matches:
            # - the verbatim author names, if any
            # - the verbatim authorship date, if any
            # and with no "sensu" conflict
            # e.g. `verbatim`="(Slabber, 1769)"
            #      `candidate1`="(Slabber, 1769)"
            #      `candidate2`="(Slabber, 1769) sensu Holmes, 1905"
            #       the result should be `candidate1`

            candidates = candidates[~candidates["sensu_conflict"]]

            if len(candidates)==1:

                # Only one match

                match_idx = candidates.index[0]
                classif = ["noSensuConflict"] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()
                processed = True

        return candidates, processed, classif


def _fuzzymatch_HigherRanks(ranks1, ranks2, levenshtein_tolerance=0.7):

    diffnan = (ranks1.isna()!=ranks2.isna()) # if both pd.NA, match=True

    match = []

    for c in range(ranks1.shape[0]): # candidate

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

    match = pd.DataFrame(match, columns=["Nmismatch","Nnan","isnan"])

    return match

def _exactmatch_HigherRanks(ranks1, ranks2):

    diff = (ranks1.fillna('')!=ranks2.fillna('')) # difference
    #isnan = (ranks1.isna() + ranks2.isna())
    isnan = (ranks1.isna()!=ranks2.isna()) # if both pd.NA, match=True

    match = pd.DataFrame(diff[~isnan].sum(axis=1).astype(int), columns=["Nmismatch"])

    match["Nnan"] = isnan.sum(axis=1) # number of NaNs
    match["isnan"] = isnan.any(axis=1)

    return match

def _match_TaxaByHigherRanks(ranks1, ranks2, fuzzy=False, fixed_allowedMismatch=False, auto_allowedMismatch=NaN2AllowedMismatch, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2):

    #print(ranks1)
    #print(ranks2)
    #print()
    ranks1 = ranks1.replace('',pd.NA)
    ranks2 = ranks2.replace('',pd.NA)
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

    allowedMismatchByNaN = pd.DataFrame.from_dict(auto_allowedMismatch, orient='index', columns=["max_mismatch"])
    if fixed_allowedMismatch:
        allowedMismatchByNaN.iloc[0,0]=fixed_allowedMismatch_withoutNaN
        allowedMismatchByNaN.iloc[1:-1,0]=fixed_allowedMismatch_withNaN
        allowedMismatchByNaN.iloc[-1,0]=-1

    # Full naive matching
    # naive because the level of non-matching ranks is not taken into account

    match.loc[:,"match"] = (match.loc[:,"Nmismatch"].values <= allowedMismatchByNaN.loc[match.loc[:,"Nnan"],"max_mismatch"].values)

    return match


def _match_TaxaByFullClassification(gbif_classif, worms_classif, verbatimcolumn=None, verbatimauthorshiponly=False, fuzzy=True, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False):

    #higherranks = list(gbif_classif.columns)
    higherranks = list(set(RANK.values()) - set([RANK['species']]))
    wormscolumns = list(worms_classif.columns)
    colnames = ["classif_matchtype"] + wormscolumns
    #print()
    #print('gbif_classif')
    #print(gbif_classif)
    if worms_classif["worms_matchtype"].isin(["nomatch"]).any():

        # No match in WoRMS

        if len(worms_classif)>1: # something wrong
            raise NotImplementedError("More than one candidate, but one is a 'nomatch'")

        else:
            match_idx = None
            classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)
            processed = True

    elif worms_classif["worms_matchtype"].isin(["match_quarantine","match_deleted"]).all():

        # No match in WoRMS

        match_idx = None
        classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)
        processed = True

    else:

        # WoRMS match

        params = {'fuzzy':fuzzy,
                  'fixed_allowedMismatch':fixed_allowedMismatch,
                  'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
                  'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN}

        processed = False

        # STEP N°1: Do the higher ranks match?

        match = _match_TaxaByHigherRanks(worms_classif.loc[:,higherranks], gbif_classif.loc[:,higherranks], **params)

        # Worst-case strategy (risk aversion):
        # N certain non-matches are preferred to (N+1) potential non-matches, and therefore also to (N+1) potential matches
        # Best classification:
        # classification with the lowest `mismatch_level` and the lowest number of mismatches within that level (`Nmismatch`)
        match["mismatch_level"] = match["Nmismatch"] + match["Nnan"]

        if any(match["match"]):

            # Higher ranks match

            if match["match"].sum()==1:

                # Only one full match

                match_idx = np.where(match["match"])[0][0]
                classif = pd.DataFrame([["singleMatch"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                processed = True

            else:

                # More than one full match

                match = match[match["match"]]
                match_index = match.index.tolist()

                # STEP N°2: Do all candidates refer to the same accepted species?

                unique_aphiaID = worms_classif.loc[match_index,'valid_aphiaID'].unique()
                if len(unique_aphiaID)==1:

                    # By default, keep the first one
                    # all candidates refer to the same accepted species

                    match_idx = match_index[0]
                    classif = pd.DataFrame([["singleAphiaID"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                    processed=True

                # STEP N°3: Does one of the candidates best match both the species name and the classification?

                if not processed:

                    unique_wormsspecies = worms_classif.loc[match_index,RANK['species']].unique()
                    if len(unique_wormsspecies)>1:

                        # More than one species name among WoRMS candidates

                        match[["speciesratio","Nspeciesmatch"]]=pd.NA
                        match["speciesratio"]=match["speciesratio"].astype('Float64')
                        match["Nspeciesmatch"]=match["Nspeciesmatch"].astype('Int64')

                        ## Compute the Levenstein ratio between each unique WoRMS species name and the name of the species being processed

                        indexBywormsspecies = worms_classif.loc[match_index,RANK['species']].groupby([RANK['species']]).indices
                        gbifspe = gbif_classif.loc[0,RANK['species']]
                        for wormsspe in unique_wormsspecies:
                            match.loc[indexBywormsspecies[wormsspe],["speciesratio","Nspeciesmatch"]] = elementwise_LevensteinRatio(wormsspe, gbifspe)

                        ## Best species name
                        # i.e  species name with the highest number of components and the best Levenstein ratio
                        # e.g. species: "Haliclona (Rhizoniera) viscosa" (may be misspelled)
                        #      worms: "Haliclona (Rhizoniera) viscosa" & "Haliclona viscosa"
                        #      the result should be "Haliclona (Rhizoniera) viscosa",
                        #      even if the Levenstein ratio is lower due to spelling mistakes

                        bestspecies = match[(match["Nspeciesmatch"]==match["Nspeciesmatch"].max()) & (match["speciesratio"]>=0.8)] #threshold of 0.8 to avoid false matches
                        if len(bestspecies)>=1:
                            max_speciesratio = bestspecies["speciesratio"].max() # no NaN
                            bestspecies = bestspecies[(max_speciesratio - bestspecies["speciesratio"])<1e-2]
                        else:
                            max_speciesratio = match["speciesratio"].max() # no NaN
                            bestspecies = match[(max_speciesratio - match["speciesratio"])<1e-2]

                        bestspecies_index = bestspecies.index[0]

                        if len(bestspecies)==1:

                            # Only one match

                            ## Best classification match

                            bestclassif = match[(match["mismatch_level"]==match["mismatch_level"].min())]
                            bestclassif = bestclassif[(bestclassif["Nmismatch"]==bestclassif["Nmismatch"].min())]
                            minNmismatch = list(set(bestclassif["Nmismatch"]))

                            minNmismatch_bestspecies = bestspecies.loc[0,"Nmismatch"]

                            if (len(minNmismatch)!=1): #À SUPPRIMER APRES DEBUG
                                raise Exception

                            ## Does the best match for species name have fewer or as many mismatches as the best match for classification?

                            if minNmismatch_bestspecies<=minNmismatch:

                                 # Keep the candidate that best matches the species name

                                 match_idx = bestspecies_index
                                 classif = pd.DataFrame([["bestSpeciesName"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                                 processed=True

                        if bestspecies_index!=match_index[bestspecies_index]: #À SUPPRIMER APRES DEBUG
                            raise Exception

                        # Keep the WoRMS species name that best matches the name of the species being processed
                        # for later use in the _match_TaxaByAuthorship() function

                        del match_index[bestspecies_index]
                        match_index.insert(0,bestspecies_index)
                        #match = match.loc[match_index,:]

                candidates = worms_classif.loc[match_index,:]

                # STEP N°4: Do all candidates have the same classification and "accepted" status?

                if not processed:

                    unique_ClassifStatus = candidates[higherranks + ["worms_status"]].fillna('').drop_duplicates(inplace=False)
                    if (len(unique_ClassifStatus)==1) and (unique_ClassifStatus.loc[0,"worms_status"]=="accepted"):

                        if len(candidates["valid_aphiaID"].unique())!=1: #À SUPPRIMER APRES DEBUG
                            raise Exception

                        # By default, keep the first one
                        # all candidates have the same classification and “accepted” status, only the authority changes
                        # they most likely refer to the same species

                        match_idx = match_index[0]
                        classif = pd.DataFrame([["allAccepted"] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                        processed=True

               # STEP N°5: Is it possible to decide between candidates on the basis of the information contained in the raw data?

               if (not processed) and (verbatimcolumn is not None):

                    verbatim = gbif_classif.loc[0,verbatimcolumn]
                    if (not pd.isnull(verbatim)) and (not len(verbatim)==0):
                        candidates, processed, classif = _match_TaxaByVerbatim(verbatim, candidates, verbatimcolumn=verbatimcolumn, verbatimauthorshiponly=verbatimauthorshiponly)

                    if processed:

                        # Keep the candidate whose authorship best matches the verbatim authorship, if any

                        classif = pd.DataFrame([classif], columns=colnames)

               # STEP N°6: Default rules

               if (not processed):

                   ## Best classification match

                   candidates = candidates[(candidates["mismatch_level"]==candidates["mismatch_level"].min())]
                   candidates = candidates[(candidates["Nmismatch"]==candidates["Nmismatch"].min())]

                   if len(candidates)==1:

                       # Only one match

                       match_idx = candidates.index[0]
                       classif = pd.DataFrame([["bestClassification"] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                       processed = True

                   else:

                       # Impossible to decide, check by hand or delete

                       match_idx = None
                       classif = pd.DataFrame([["undecided"] + [pd.NA]*len(wormscolumns)], columns=colnames)
                       processed = True


        else:

            # No match for higher ranks

            candidates = worms_classif[worms_classif["worms_matchtype"].isin(["exact","exact_subgenus","phonetic","near_1","near_2","near_3"])]

            if fuzzy:
                gbif_kingdom=gbif_classif.loc[0,RANK["kingdom"]]
                match = [(Levenshtein.ratio(kingdom, gbif_kingdom)>=0.7) for _,kingdom in enumerate(candidates[RANK["kingdom"]])]
                candidates = candidates[match]
            else:
                candidates = candidates[candidates[RANK["kingdom"]]==gbif_classif.loc[0,RANK["kingdom"]]]

            if len(candidates)!=0:

                if (verbatimcolumn is not None):

                    # If species match is high, use verbatim authorship
                    # because classification may have changed

                    verbatim = gbif_classif.loc[0,verbatimcolumn]
                    candidates, processed, classif = _match_TaxaByVerbatim(verbatim, candidates)

                    if processed:

                        # Keep the candidate whose authorship best matches the verbatim authorship, if any

                        classif = pd.DataFrame([classif], columns=colnames)
                        classif["classif_matchtype"] = classif["classif_matchtype"] + "_nomatch"

                if (not processed):

                    # Check by hand or delete

                    match_idx = None
                    classif = pd.DataFrame([["suspicious"] + [pd.NA]*len(wormscolumns)], columns=colnames)
                    processed = True

            else:

                match_idx = None
                classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)
                processed = True


    # Remove fossils

    if not keep_fossil:

        indexes = worms_classif[worms_classif["isextinct"]==1].index

        if match_idx in indexes:

             classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)
             print(gbif_classif)
             print(worms_classif)


    return classif

def _display_progress(classification, idx):

    classif = classification.iloc[:idx,:]

    nclassification = len(classification)
    Nnomatch = len(classif[classif["classif_matchtype"]=="nomatch"])
    Nmatch = len(classif) - Nnomatch
    percentage = np.round((idx+1)/nclassification*100,2)

    print(f'            Processing | {idx+1}/{nclassification} classifications done ({percentage}%): no_match={Nnomatch}, match={Nmatch}') 

    return True

def _call_match_WoRMS(species, store=True, outputpath='./', overwrite=False, **kwargs):

    wormscallK = list(worms_mapping.keys())
    wormscallV = list(itemgetter(*wormscallK)(worms_mapping))
    wormscall = dict(zip(wormscallV,wormscallK))

    params = {'wormscall':wormscall,
              'store':store,
              'outputpath':outputpath,
              'overwrite':overwrite}

    if store:

        outputfile_split = getdefaultargs.apply(cwf.match_WoRMS)['outputfile'].split('.')

        if ('outputfile_suffix' in kwargs.keys()):
            kwargs['outputfile_suffix'] = 'isinworms_' + kwargs['outputfile_suffix']
        else:
            kwargs['outputfile_suffix'] = 'isinworms'

        params['outputfile'] = outputfile_split[0] + '_' + kwargs['outputfile_suffix'] + '.' + outputfile_split[1]

    matchfilter = cwf.match_WoRMS(species, **params)

    return matchfilter

def apply_matchfilter(classification, matchfilter=None, fuzzy=True, verbatimcolumn=None, verbatimauthorshiponly=False, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False, store=True, outputpath='./', **kwargs):

    nclassification = len(classification)
    print(f'            * WoRMS filtering (recognized marine taxa) | {nclassification} unique classifications')

    # Match taxa to a WoRMS classification, based on:
    # - species name
    # - higher ranks
    # - and possibly authorship

    if keep_fossil:
        # do not delete fossil occurrences
        del worms_mapping['extinct']

    wormscolumns = list(worms_mapping.keys())
    if verbatimcolumn is None:
        # no authorship
        gbifcolumns = list(RANK.values())
    else:
        # use authorship, if any
        gbifcolumns = list(RANK.values()) + verbatimcolumn


    ## Match species name

    unique_species = classification[RANK['species']].unique().tolist()

    if matchfilter is None:

        # Create WoRMS match filter

        print(f'            ** isinworms | createwormsfilter')

        matchfilter = _call_match_Worms(unique_species, store=store, outputpath=outputpath, overwrite=False, **kwargs)

    else:

        # Check that all the columns required for filtering are present in the WoRMS match filter

        check_columns = ['group'] + wormscolumns
        if (len(check_columns)>len(matchfilter.columns)) or any(col not in check_columns for col in matchfilter.columns):
           raise KeyError(f"Filter column names must be: {check_columns}")

        # Complete WoRMS match filter if necessary

        species2process = resume_process(matchfilter, unique_species)
        if len(species2process)!=0:

            print(f'            ** isinworms | createwormsfilter')
            print(f'            UPDATE | {len(species2process)}/{len(unique_species)} ({np.round(len(species2process)/len(unique_species)*100,2)}%) remaining species to be processed')

            kwargs['outputfile_suffix']='add'
            addmatchfilter = _call_match_WoRMS(species2process, store=store, outputpath=outputpath, overwrite=False, **kwargs)

            matchfilter = pd.concat([matchfilter,addmatchfilter], axis=0)


    ## Match higher ranks & authorship

    filter = matchfilter.groupby(['group'])

    params = {'fuzzy':fuzzy,
              'fixed_allowedMismatch':fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN,
              'verbatimauthorshiponly':verbatimauthorshiponly,
              'verbatimcolumn':verbatimcolumn}

    for idx in range(nclassification):

        spe = tuple([classification.loc[idx,RANK['species']]])

        worms_classif = filter.get_group(spe).reset_index(drop=True)
        gbif_classif = pd.DataFrame([classification.loc[idx,gbifcolumns]]*len(worms_classif),columns=gbifcolumns).reset_index(drop=True)
        #print(worms_classif)
        #print(gbif_classif)

        classif = _match_TaxaByFullClassification(gbif_classif, worms_classif, **params)

        if classif["classif_matchtype"].values in ["nomatch", "undecided", "suspicious", "ismore", "ismore_nomatch"]:

            # Keep original values

            classification.loc[idx,"classif_matchtype"] = classif["classif_matchtype"].values
            classification.loc[idx,["worms_matchtype","worms_status","valid_aphiaID"]] = pd.NA

        else:

            # Keep WoRMS values

            classification.loc[idx,wormscolumns + ["classif_matchtype"]] = classif[wormscolumns + ["classif_matchtype"]].values.flatten()


        if (((idx+1)%1000)==0) or (idx==(nclassification-1)):

            # Display code progress

            _display_progress(classification, idx)

    # Delete taxa that do not match any WoRMS classification

    classification = classification[classification["classif_matchtype"]!="nomatch"]

    print(f'            Done | before: {nclassification}, after: {len(classification)} classifications')

    return classification


def _call_get_AcceptedWoRMS(valid_aphiaID, store=True, outputpath='./', overwrite=False, **kwargs):

    wormscallK = list(worms_mapping.keys())
    wormscallV = list(itemgetter(*wormscallK)(worms_mapping))
    wormscall = dict(zip(wormscallV,wormscallK))

    params = {'wormscall':wormscall,
              'store':store,
              'outputpath':outputpath,
              'overwrite':overwrite}

    if store:

        outputfile_split = getdefaultargs.apply(cwf.get_AcceptedWoRMS)['outputfile'].split('.')

        if ('outputfile_suffix' in kwargs.keys()):
            kwargs['outputfile_suffix'] = 'isinworms_' + kwargs['outputfile_suffix']
        else:
            kwargs['outputfile_suffix'] = 'isinworms'

        params['outputfile'] = outputfile_split[0] + '_' + kwargs['outputfile_suffix'] + '.' + outputfile_split[1]

    matchfilter = cwf.get_AcceptedWoRMS(valid_aphiaID, **params)

    return matchfilter

def apply_acceptedfilter(classification, acceptedfilter=None, store=True, outputpath='./', **kwargs):

    if len(classification)==0:
        return classification

    # Identify unaccepted taxa

    unaccepted_idx = classification[(~classification['worms_status'].isin(["accepted","deleted"])) & (~pd.isnull(classification['valid_aphiaID']))].index
    nunaccepted = len(unaccepted_idx)

    # Match unaccepted taxa to their accepted classification

    if len(unaccepted_idx) != 0:

        print(f'            * WoRMS filtering (accepted taxa) | {nunaccepted} occurrences associated with an unaccepted taxon')

        unique_aphiaID = classification.loc[unaccepted_idx,"valid_aphiaID"].unique().tolist()

        if acceptedfilter is None:

            # Create WoRMS accepted match filter

            print(f'            ** isinworms | createwormsfilter')

            acceptedfilter = _call_get_AcceptedWoRMS(unique_aphiaID, store=store, outputpath=outputpath, overwrite=False, **kwargs)

        else:

            # Check that all the columns required for matching are present in the WoRMS accepted match filter

            check_columns = ["group"] + list(worms_mapping.keys())
            if (len(check_columns)>len(acceptedfilter.columns)) or any(col not in check_columns for col in acceptedfilter.columns):
                raise KeyError(f"Filter column names must be: {check_columns}")

            # Complete WoRMS accepted match filter if necessary

            aphiaID2process = resume_process(acceptedfilter, unique_aphiaID)
            if len(aphiaID2process)!=0:

                print(f'            ** isinworms | createwormsfilter')
                print(f'            UPDATE | {len(aphiaID2process)}/{len(unique_aphiaID)} ({np.round(len(aphiaID2process)/len(unique_aphiaID)*100,2)}%) remaining unaccepted taxa to be processed')

                kwargs['outputfile_suffix']='add'
                addacceptedfilter = _call_get_AcceptedWoRMS(aphiaID2process, store=store, outputpath=outputpath, overwrite=False, **kwargs)

                acceptedfilter = pd.concat([acceptedfilter,addacceptedfilter], axis=0)

        if len(acceptedfilter['group'].unique()) != len(acceptedfilter):
            raise Exception(f"The filter of accepted classifications must not contain duplicates for the `valid_aphiaID` column.")

        # Match `valid_aphiaID`

        filter = acceptedfilter.set_index(['group'])
        filter = filter.loc[classification.loc[unaccepted_idx,"valid_aphiaID"].values,:].reset_index()

        wormscolumns = list(worms_mapping.keys())
        classification.loc[unaccepted_idx, wormscolumns] = filter[wormscolumns].values

    return classification



def clean_taxonomy(classification, matchfilter=None, fuzzy=True, verbatimcolumn=None, verbatimauthorshiponly=False, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False, acceptedfilter=None, store=True, outputpath='./')

    # Match WoRMS

    params = {'matchfilter':matchfilter,
              'fuzzy':fuzzy,
              'fixed_allowedMismatch':fixed_allowedMismatch,
              'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
              'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN,
              'verbatimauthorshiponly':verbatimauthorshiponly,
              'verbatimcolumn':verbatimcolumn,
              'keep_fossil':keep_fossil,
              'store':store,
              'outputpath':outputpath}

    classification = apply_matchfilter(classification, **params)

    # Relaunch WoRMS matching for classifications tagged "ismore"

    ismore_index = classification[classification["classif_matchtype"].str.contains("ismore")].index.tolist()
    if len(ismore_index)!=0:

        if verbatimauthorshiponly: #À SUPPRIMER APRES DEBUG
            raise Exception

        params['matchfilter']=None
        params['outputfile_suffix']='ismore'

        speciesrank = RANK["species"]
        worms_mapping[verbatimcolumn]=worms_mapping.pop(RANK["species"])
        RANK["species"] = verbatimcolumn

        temp = apply_matchfilter(classification.loc[ismore_index,:], **params).rename(columns={RANK["species"]:speciesrank})
        classification.loc[ismore_index,:] = temp.loc[ismore_index,classification.columns] # specify indexes and columns to make sure everything has gone well

        worms_mapping[speciesrank]=worms_mapping.pop(verbatimcolumn)
        RANK["species"] = speciesrank

    debug = classification[classification["classif_matchtype"].str.contains("ismore")] #À SUPPRIMER APRES DEBUG
    if len(debug)!=0:
       print(len(debug))
       print(debug[RANK["species"]].tolist())
       raise Exception

    # Match accepted WoRMS

    params = {'acceptedfilter':acceptedfilter,
              'store':store,
              'outputpath':outputpath}

    classification = apply_acceptedfilter(classification, **params)

    return classification



def drop(df, drop_conditions):

    df['rank']=df['rank'].str.lower()

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

def apply(df, *ignored_args, overwrite=True, verbatimcolumn=None, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, matchfilter=None, acceptedfilter=None, keep_fossil=False, store=True, outputpath='./', drop_conditions={'classif_matchtype':'nomatch', 'worms_matchtype':'match_deleted'}):

    Nobs = len(df)

    wormscolumns = list(worms_dtypes.keys())
    rankcolumns = list(RANK.values())

    if Nobs == 0:

        df.rename(columns={"species":"species_unprocessed"}, inplace=True)
        df = df.reindex(df.columns.tolist() + ["species", "classif_matchtype"] + wormscolumns, axis=1)

        return df

    if verbatimcolumn is not None:
        # use authorship, if any
        columns = rankcolumns + [verbatimcolumn]
    else:
        # no authorship
        columns = rankcolumns

    # Get unique classifications

    dfByClassification = df.loc[(~pd.isnull(df[RANK["species"])), columns].fillna('unk').groupby(columns, dropna=False) #get_group() doesn't work with NaN
    taxonomy = pd.DataFrame(list(dfByClassification.groups.keys()), columns=rankcolumns)

    # Get WoRMS-accepted classifications associated with these classifications, if any

    classification = clean_taxonomy(taxonomy.replace('unk',pd.NA), verbatimcolumn=verbatimcolumn, fixed_allowedMismatch=fixed_allowedMismatch, fixed_allowedMismatch_withNaN=fixed_allowedMismatch_withNaN, fixed_allowedMismatch_withoutNaN=fixed_allowedMismatch_withoutNaN, acceptedfilter=acceptedfilter, matchfilter=matchfilter, outputpath=outputpath, keep_fossil=keep_fossil)
    print("index:", classification.index) #À SUPPRIMER APRES DEBUG

    # Standardize taxonomy

    ## Prepare the dataframe

    if overwrite:
        print(f"            WARNING | {rankcolumns} columns already exists and will be overwritten")
        rankcolumns_mapping = {rank : rank for rank in rankcolumns}
    else:
        rankcolumns_mapping = {rank : rank + '_processedby_isinworms' for rank in rankcolumns}
        rankcolumns = list(rankcolumns_mapping.values())
        df[rankcolumns]=pd.NA

    df["classif_matchtype"]="nomatch"
    df[wormscolumns] = pd.NA
    df[wormscolumns] = df[wormscolumns].astype(worms_dtypes)

    rankcolumns = list(rankcolumns_mapping.values())
    df[rankcolumns] = df[rankcolumns].astype('string')

    ## Apply the standardized taxonomy

    print(f'            * Standardization via WoRMS | Full dataset')

    classification_indexes = classification.index
    classification_columns = classification.columns
    target_columns = []
    for column in classification_columns:
        try:
            target_columns.append(rankcolumns_mapping[column])
        except KeyError:
            target_columns.append(column)

    print("target_columns",target_columns) #À SUPPRIMER APRES DEBUG

    for idx in classification_indexes:

        group = tuple(taxonomy.loc[idx,:].values)
        indexes = dfByClassification.get_group(group).index
        df.loc[indexes, target_columns] = classification.loc[idx, classification_columns].values

    # Delete matches deemed insufficient

    df=drop(df, drop_conditions)

    df.rename(columns={"valid_aphiaID":"worms_aphiaID"}, inplace=True)

    print(f'            Done | before : {Nobs}, after : {len(df)} observations')

    return df


#À SUPPRIMER APRES DEBUG

def test():

    df = pd.read_csv('/data/smartbiodiv/eberhocoi/useverbatim.csv',sep='\t')
    dfgb = df.groupby(['verbatim'])
    for key in dfgb.groups.keys():
        verbatim = key
        candidates = dfgb.get_group((key,))[["species","authorship","status"]]

        print("verbatim :", verbatim)
        print("candidates")
        print(candidates)
        print(_match_TaxaByAuthorship(verbatim, candidates))
        print()
        print()

if __name__ == "__main__":
    test()


