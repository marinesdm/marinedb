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
from marinedb.filters import higherranksthan
from marinedb.utils import regexstrip

#Rank names in the file to be processed
#Schema: RANK = {rank_name: rank_name_in_the_file}
RANK = {
        'species':'species',
        'genus':'genus',
        'family':'family',
        'order':'order',
        'class':'class',
        'phylum':'phylum',
        'kingdom':'kingdom'
       }


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


class NotImplemented(Exception):
    pass

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

    try:
        verbatim = verbatim.encode('latin-1').decode('utf-8')
    except UnicodeDecodeError:
        pass
    verbatim = unidecode(verbatim.strip())
    speidx = candidates.columns.to_list().index(RANK["species"])
    wormsspecies = unidecode(candidates.iloc[0,speidx].strip())

    # Find the species name in `verbatim`

    ## Determine the spelling of the species name components in `verbatim` using `wormsspecies`
    # (take misspelling into account e.g. "Clatria rubens" for "Clathria rubens")
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
        candidates[["sensu_conflict","datematch_diff","datematch","authormatch_ratio","authormatch"]]=pd.NA

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
            candidates[["datematch_diff","datematch","authormatch_ratio","authormatch"]]=pd.NA
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

            if "match" not in candidates.columns:
                candidates["match"]=pd.NA
            candidates[["datematch","datematch_diff","authormatch","authormatch_ratio"]]=pd.NA
            candidates[["match","datematch","authormatch"]]=candidates[["match","datematch","authormatch"]].astype("boolean")
            candidates["datematch_diff"]=candidates["datematch_diff"].astype("Int64")
            candidates["authormatch_ratio"]=candidates["authormatch_ratio"].astype("Float64")

            # if `verbatim_authorship` does not contain "sensu":
            #   for candidates containing "sensu" (i.e sensu_conflict=True), `verbatim_authorship` must match one of the candidates' authors
            #     if `verbatim_authorhip` matches a candidate's two authors, store the best match information, if any
            #       if the best match is not obvious, keep the information of the candidate whose author is the best match

            doescandidatecontain = (candidates.index.isin(index)) & (candidates["sensu_conflict"])

            if any(doescandidatecontain):

                doescandidatecontain = doescandidatecontain[doescandidatecontain].index.to_list()

                temp = candidates_authorships.loc[doescandidatecontain,:].copy()
                temp_match = temp[["match1","match2"]].sum(axis=1)

                # no match
                index_nomatch = temp_match[temp_match==0].index.to_list()
                if len(index_nomatch)!=0:
                    candidates.loc[index_nomatch,"match"]=False

                idx1 = []
                idx2 = []

                # only one match
                index_singlematch = temp_match[temp_match==1].index.to_list()
                if len(index_singlematch)!=0:
                    singlematch = idxmax(temp.loc[index_singlematch,:], ["match1","match2"], axis=1, skipna=True)
                    idx1 = idx1 + singlematch[singlematch=="match1"].index.to_list()
                    idx2 = idx2 + singlematch[singlematch=="match2"].index.to_list()

                # more than one match
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

    return candidates, ismore #if ismore & all(~candidates["match"]), new WoRMS request with verbatim


def _exactmatch_TaxaByHigherRanks(ranks1, ranks2, fixed_allowedMismatch=False, auto_allowedMismatch=NaN2AllowedMismatch, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2):

    #print(ranks1)
    #print(ranks2)
    #print()
    ranks1 = ranks1.replace('',pd.NA)
    ranks2 = ranks2.replace('',pd.NA)
    ranks1 = ranks1.astype('string')
    ranks2 = ranks2.astype('string')

    diff = (ranks1.fillna('')!=ranks2.fillna(''))

    #isnan = (ranks1.isna() + ranks2.isna())
    isnan = (ranks1.isna()!=ranks2.isna()) #if both pd.NA, match=True
    match = pd.DataFrame(diff[~isnan].sum(axis=1).astype(int), columns=["Nmismatch"])

    match["Nnan"] = isnan.sum(axis=1)
    match["isnan"] = isnan.any(axis=1)

    allowedMismatchByNaN = pd.DataFrame.from_dict(auto_allowedMismatch, orient='index', columns=["max_mismatch"])
    if fixed_allowedMismatch:
        allowedMismatchByNaN.iloc[0,0]=fixed_allowedMismatch_withoutNaN
        allowedMismatchByNaN.iloc[1:-1,0]=fixed_allowedMismatch_withNaN
        allowedMismatchByNaN.iloc[-1,0]=-1

    #Naive matching, the level of non-matching ranks is not taken into account

    match.loc[:,"match"] = (match.loc[:,"Nmismatch"].values <= allowedMismatchByNaN.loc[match.loc[:,"Nnan"],"max_mismatch"].values)

    return match

def _match_TaxaByFullClassification(gbif_classif, worms_classif, verbatimcolumn=None, fuzzy=True, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, keep_fossil=False):

    #higherranks = list(gbif_classif.columns)
    higherranks = list(set(RANK.values()) - set([RANK['species']]))
    wormscolumns = list(worms_classif.columns)
    colnames = ["classif_matchtype"] + wormscolumns
    #print()
    #print('gbif_classif')
    #print(gbif_classif)
    if any(worms_classif["worms_matchtype"]=="nomatch"):

        # No match in WoRMS

        if len(worms_classif)>1: # something wrong
            raise NotImplementedError("More than one candidate, but one is a 'nomatch'")

        else:
            match_idx = None
            classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)


    else:

        # WoRMS match

        params = {'fixed_allowedMismatch':fixed_allowedMismatch,
                  'fixed_allowedMismatch_withNaN':fixed_allowedMismatch_withNaN,
                  'fixed_allowedMismatch_withoutNaN':fixed_allowedMismatch_withoutNaN}

        if fuzzy:
            match = _fuzzymatch_TaxaByHigherRanks(worms_classif.loc[:,higherranks], gbif_classif.loc[:,higherranks], **params)
        else:
            match = _exactmatch_TaxaByHigherRanks(worms_classif.loc[:,higherranks], gbif_classif.loc[:,higherranks], **params)

       # worst-case strategy (risk aversion): n certain non-matches are preferred to (n+1) potential non-matches (and therefore also to (n+1) potential matches)
        match["mismatch_level"] = match["Nmismatch"] + match["Nnan"]

        if any(match["match"]):

            # Higher ranks match

            if match["match"].sum()==1:

                # Only one full match

                match_idx = np.where(match["match"])[0][0]
                classif = pd.DataFrame([["near1"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)

            else:

                # More than one full match

                match = match[match["match"]]
                match_index = match.index.tolist()

                processed=False

                # Step n°1: Do all candidates refer to the same accepted species?

                unique_aphiaID = worms_classif.loc[match_index,'valid_aphiaID'].unique()
                if len(unique_aphiaID)==1:

                    # All candidates refer to the same accepted species
                    # By default, keep the first one

                    match_idx = match_index[0]
                    classif = pd.DataFrame([["singleAphiaID"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                    processed=True

                # Step n°2: Does one of the candidates best match both the species name and the classification?

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

                        ## Best species name match: species name with the highest number of components and the best Levenstein ratio
                        # e.g. species: "Haliclona (Rhizoniera) viscosa" (may be misspelled)
                        #      worms: "Haliclona (Rhizoniera) viscosa" & "Haliclona viscosa"
                        #      the result should be "Haliclona (Rhizoniera) viscosa",
                        #      even if the Levenstein ratio is lower due to spelling mistakes

                        bestspecies = match[(match["Nspeciesmatch"]==match["Nspeciesmatch"].max()) & (match["speciesratio"]>=0.8)] #threshold of 0.8 to avoid false matches
                        if len(bestspecies)>=1:
                            bestspecies = bestspecies[bestspecies["speciesratio"]==bestspecies["speciesratio"].max()]
                        else:
                            bestspecies = match[match["speciesratio"]==match["speciesratio"].max()]

                        bestspecies_index = bestspecies.index[0]

                        if len(bestspecies)==1:

                            # Only one match with the best species name

                            ## Best classif. match: classif. with the lowest `mismatch_level` and the lowest number of mismatches within that level
                            bestclassif = match[(match["mismatch_level"]==match["mismatch_level"].min())]
                            bestclassif = bestclassif[(bestclassif["Nmismatch"]==bestclassif["Nmismatch"].min())]
                            minNmismatch = list(set(bestclassif["Nmismatch"]))

                            minNmismatch_bestspecies = bestspecies.loc[0,"Nmismatch"]

                            if (len(minNmismatch)!=1): #À SUPPRIMER APRES DEBUG
                                raise Exception

                            ## Does the best match for species name have fewer or as many mismatches as the best match for classification?
                            if minNmismatch_bestspecies<=minNmismatch:

                                 # Keep the candidate that best matches the species name

                                 match_idx = bestspecies.index[0]
                                 classif = pd.DataFrame([["bestSpeciesName"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                                 processed=True

                        if bestspecies_index!=match_index[bestspecies_index]: #À SUPPRIMER APRES DEBUG
                            raise Exception

                        # Keep the WoRMS species name that best matches the name of the species being processed
                        # for later use in the _match_TaxaByAuthorship() function
                        del match_index[bestspecies_index]
                        match_index.insert(0,bestspecies_index)
                        match = match.loc[match_index,:]

                # Step n°3: Do all candidates have the same classification and "accepted" status?

                if not processed:

                    unique_ClassifStatus = worms_classif.loc[match_index, higherranks + ["worms_status"]].fillna('').drop_duplicates(inplace=False)
                    if (len(unique_ClassifStatus)==1) and (unique_ClassifStatus.loc[0,"worms_status"]=="accepted"):

                        if len(worms_classif.loc[match_index,"valid_aphiaID"].unique())!=1: #À SUPPRIMER APRES DEBUG
                            raise Exception

                        # All candidates have the same classification and “accepted” status, only the authority changes
                        # They most likely refer to the same species, so by default, keep the first one.

                        match_idx = match_index[0]
                        classif = pd.DataFrame([["allAccepted"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                        processed=True

               # Step n°4: Is it possible to decide between candidates on the basis of the information contained in the raw data?

               if (not processed) and (verbatimcolumn is not None):

                   verbatim = gbif_classif.loc[0,verbatimcolumn]
                   candidates = worms_classif.loc[match_index,:]

                   if (not pd.isnull(verbatim)) and (not verbatim==''):
                       candidates, ismore = _match_TaxaByAuthorship(verbatim, candidates)

#CONTINUER !!!!!!!!!!!

               # Step n°5: Default rules

#CONTINUER !!!!!!!!!!!

                candidates = match[match["Nmismatch"]==(match["Nmismatch"].min())]

                if len(candidates) == 1:

                    # Keep the candidate with the lowest number of mismatches

                    match_idx = candidates.index[0]
                    classif = pd.DataFrame([["near2"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)

                elif candidates["isnan"].sum()==1: #not tested

                    # Keep the candidate with:
                    # - the lowest number of mismatches
                    # - and the lowest number of missing values

                    match_idx = np.where(~candidates["isnan"])[0][0]
                    classif = pd.DataFrame([["near3"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)

                else: #faire check verbatim

                    # Several candidates have the same number of mismatches and missing values

                    candidates = worms_classif.loc[candidates.index.tolist(),:]
                    candidates = candidates[candidates["worms_status"]=="accepted"]

                    #In GBIF, the `species` value corresponds to the accepted name
                    #for the species from the GBIF backbone matched to this occurrence
                    #If in doubt, choose the taxon accepted in WoRMS

                    if len(candidates) == 1:

                        # Keep the candidate with:
                        # - the lowest number of mismatches
                        # - the lowest number of missing values
                        # - and whose status is "accepted"

                        match_idx = candidates.index[0]
                        classif = pd.DataFrame([["near4"] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)

                    elif len(candidates) > 1:

                        # Several candidates have the same classification and “accepted” status, only the authority changes
                        # They refer to the same species, so by default, keep the first one.
                        #print('worms')
                        #print(candidates)
                        match_idx = candidates.index[0]
                        classif = pd.DataFrame([["near5"] + candidates.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)
                        #print()
                    else:

                        # Impossible to decide, check by hand

                        match_idx = None
                        classif = pd.DataFrame([["undecided"] + [pd.NA]*len(wormscolumns)], columns=colnames)
        else:

            # No match for higher ranks

            candidates = worms_classif[worms_classif["worms_matchtype"].isin(["exact","exact_subgenus"])] #(["exact","exact_subgenus","phonetic","near_1"])]
            candidates = candidates[candidates[RANK["kingdom"]]==gbif_classif.loc[0,RANK["kingdom"]]]

            if len(candidates)!=0:

                # If the species match is high, check by hand

                match_idx = None
                classif = pd.DataFrame([["undecided"] + [pd.NA]*len(wormscolumns)], columns=colnames)

            else:

                match_idx = None
                classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)


    # Remove fossils

    if not keep_fossil:

        indexes = worms_classif[worms_classif["isextinct"]==1].index

        if match_idx in indexes:
             classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)
             print(gbif_classif)
             print(worms_classif) 
       #worms_classif = worms_classif.drop(index=indexes).reset_index(drop=True)

    #if len(worms_classif)==0: # can occur after fossils have been removed

        #classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)


    return classif



def apply_matchfilter(classification, verbatimcolumn=None, matchfilter=None, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, outputpath='./', keep_fossil=False):

    nclassification = len(classification)
    print(f'            * WoRMS filtering (recognized marine taxa) | {nclassification} unique classifications')

    if keep_fossil:
        del worms_mapping['extinct']

    wormscolumns = list(worms_mapping.keys())
    #higherranks = list(set(RANK.values()) - set([RANK['species']]))
    if verbatimcolumn is None:
        gbifcolumns = list(RANK.values())
    else:
        gbifcolumns = list(RANK.values()) + verbatimcolumn

    if matchfilter is None:

        print(f'            ** isinworms | createwormsfilter')
        unique_species = classification[RANK['species']].unique().tolist()
        wormscallK = list(worms_mapping.keys())
        wormscallV = list(itemgetter(*wormscallK)(worms_mapping))
        wormscall = dict(zip(wormscallV,wormscallK))
        matchfilter = cwf.match_WoRMS(unique_species, store=True, wormscall=wormscall, overwrite=False, outputpath=outputpath)

    else:

        check_columns = ['group'] + wormscolumns
        if (len(check_columns)!=len(matchfilter.columns)) or any(np.sort(check_columns) != np.sort(matchfilter.columns)):
           raise KeyError(f"Filter column names must be: {check_columns}")

    filter = matchfilter.groupby(['group'])

    for idx in range(nclassification):

        spe = tuple([classification.loc[idx,RANK['species']]])
        #print()
        worms_classif = filter.get_group(spe).reset_index(drop=True)
        # À FAIRE : garder l'espèce dans gbif_classif, espèce de colonne verbatimcpecies donnée en argument, i.e même colonne que celle utilisée pour createworms pour JeDI, et une autre colonne que celle utilisée pour createworms pour gbif
        #gbif_classif = pd.DataFrame([classification.loc[idx,higherranks]]*len(worms_classif),columns=higherranks).reset_index(drop=True)
        gbif_classif = pd.DataFrame([classification.loc[idx,gbifcolumns]]*len(worms_classif),columns=gbifcolumns).reset_index(drop=True)
        #print(worms_classif)
        #print(gbif_classif)

        classif = _match_TaxaByFullClassification(gbif_classif, worms_classif, verbatimcolumn=verbatimcolumn, fixed_allowedMismatch, fixed_allowedMismatch_withNaN, fixed_allowedMismatch_withoutNaN, keep_fossil=keep_fossil)

        if (classif["classif_matchtype"].values=="nomatch") or (classif["classif_matchtype"].values=="undecided"):

            classification.loc[idx,"classif_matchtype"] = classif["classif_matchtype"].values
            classification.loc[idx,["worms_matchtype","worms_status","valid_aphiaID"]] = pd.NA

        else:

            classification.loc[idx,wormscolumns + ["classif_matchtype"]] = classif[wormscolumns + ["classif_matchtype"]].values.flatten()


        if (((idx+1)%1000)==0) or (idx==(nclassification-1)):

            # Display code progress

            classif = classification.iloc[:idx,:]
            Nnomatch = len(classif[classif["classif_matchtype"]=="nomatch"])
            Nmatch = len(classif) - Nnomatch
            percentage = np.round((idx+1)/nclassification*100,2)
            print(f'            Processing | {idx+1}/{nclassification} classifications done ({percentage}%): no_match={Nnomatch}, match={Nmatch}') 


    classification = classification[classification["classif_matchtype"]!="nomatch"]

    print(f'            Done | before: {nclassification}, after: {len(classification)} classifications')

    return classification



def apply_acceptedfilter(classification, acceptedfilter=None, outputpath='./'):

    if len(classification)==0:
        return classification

    unaccepted_idx = classification[(classification['worms_status']!="accepted") & (classification['worms_status']!="deleted") & (~pd.isnull(classification['valid_aphiaID']))].index
    nunaccepted = len(unaccepted_idx)

    if len(unaccepted_idx) != 0:

        print(f'            * WoRMS filtering (accepted taxa) | {nunaccepted} occurrences associated with an unaccepted taxon')

        if acceptedfilter is None:

            print(f'            ** isinworms | createwormsfilter')
            valid_aphiaID = classification.loc[unaccepted_idx,"valid_aphiaID"].unique().tolist()
            acceptedfilter = cwf.get_AcceptedWoRMS(valid_aphiaID, store=True, overwrite=False, outputpath=outputpath)

        else:

            check_columns = ["group"] + list(worms_mapping.keys())
            if (len(check_columns)!=len(acceptedfilter.columns)) or any(np.sort(check_columns) != np.sort(acceptedfilter.columns)):
                raise KeyError(f"Filter column names must be: {check_columns}")

        if len(acceptedfilter['group'].unique()) != len(acceptedfilter):
            raise Exception(f"The filter of accepted species names must not contain duplicates for the `valid_aphiaID` column.")

        filter = acceptedfilter.set_index(['group'])
        filter = filter.loc[classification.loc[unaccepted_idx,"valid_aphiaID"].values,:].reset_index()
        #filter["unaccepted_idx"] = unaccepted_idx
        #filter = filter[(filter["rank"]=="Species") | (filter["rank"]=="Subspecies")] #no rank higher than species
        #unaccepted_idx = filter.loc[:,"unaccepted_idx"].tolist()

        wormscolumns=list(worms_mapping.keys())
        filter = filter[wormscolumns]
        classification.loc[unaccepted_idx, wormscolumns] = filter.values

        #classification.loc[unaccepted_idx, list(RANK.values())] = classification.loc[unaccepted_idx, "valid_aphiaID"].apply(lambda aphiaID : filter.loc[aphiaID,:])

    return classification



def clean_taxonomy(classification, verbatimcolumn=None, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, matchfilter=None, acceptedfilter=None, outputpath='./', keep_fossil=False):

    # Match WoRMS

    classification = apply_matchfilter(classification, matchfilter=matchfilter, verbatimcolumn=verbatimcolumn, fixed_allowedMismatch=fixed_allowedMismatch, fixed_allowedMismatch_withNaN=fixed_allowedMismatch_withNaN, fixed_allowedMismatch_withoutNaN=fixed_allowedMismatch_withoutNaN, outputpath=outputpath, keep_fossil=keep_fossil)

    # Match accepted WoRMS

    classification = apply_acceptedfilter(classification, acceptedfilter=acceptedfilter, outputpath=outputpath)

    return classification



def drop(df, drop_conditions):

    df['rank']=df['rank'].str.lower()

    if len(drop_conditions)!=0:

        print(f'            * WoRMS filtering | Drop conditions')

        if 'identification_level' in drop_conditions.keys():
            dropranks=higherranksthan.apply(drop_conditions['identification_level'])
            drop_conditions['rank']=dropranks
            del drop_conditions['identification_level']

        df = dropvalues.apply(df, **drop_conditions)

    else:
        print(f'            * WoRMS filtering | No drop conditions')

    return df



def apply(df, *ignored_args, verbatimcolumn=None, fixed_allowedMismatch=False, fixed_allowedMismatch_withNaN=1, fixed_allowedMismatch_withoutNaN=2, matchfilter=None, acceptedfilter=None, keep_fossil=False, outputpath='./', drop_conditions={'classif_matchtype':'nomatch', 'worms_matchtype':'match_deleted'}):

    Nobs = len(df)

    wormscolumns = list(worms_dtypes.keys()) #list(set(worms_mapping.keys()) - set(RANK.values()))
    rankcolumns = list(RANK.values())

    if Nobs == 0:

        df.rename(columns={"species":"species_unprocessed"}, inplace=True)
        df = df.reindex(df.columns.tolist() + ["species", "classif_matchtype"] + wormscolumns, axis=1)

        return df

    if verbatimcolumn is not None:
        columns = rankcolumns + [verbatimcolumn]
    else:
        columns = rankcolumns

    dfByClassification = df[columns].fillna('unk').groupby(columns, dropna=False) #get_group() doesn't work with NaN
    taxonomy = pd.DataFrame(list(dfByClassification.groups.keys()), columns=rankcolumns)

    classification = clean_taxonomy(taxonomy.replace('unk',pd.NA), verbatimcolumn=verbatimcolumn, fixed_allowedMismatch=fixed_allowedMismatch, fixed_allowedMismatch_withNaN=fixed_allowedMismatch_withNaN, fixed_allowedMismatch_withoutNaN=fixed_allowedMismatch_withoutNaN, acceptedfilter=acceptedfilter, matchfilter=matchfilter, outputpath=outputpath, keep_fossil=keep_fossil)
    #classification[wormscolumns]=classification[wormscolumns].astype(worms_dtypes)

    df.rename(columns={"species":"species_unprocessed"}, inplace=True)
    df["species"]=pd.NA
    df["species"]=df["species"].astype('string')
    df["classif_matchtype"]="nomatch"
    df[wormscolumns] = pd.NA
    #types = classification[wormscolumns].dtypes.todict()
    df[wormscolumns] = df[wormscolumns].astype(worms_dtypes)
    df[rankcolumns] = df[rankcolumns].astype('string')
    #print(df[list(worms_mapping.keys())].dtypes)

    print(f'            * WoRMS filtering | Full dataset')


    classification_indexes = classification.index
    classification_columns = classification.columns

    for idx in classification_indexes:

        group = tuple(taxonomy.iloc[idx,:].values)
        indexes = dfByClassification.get_group(group).index
        df.loc[indexes, classification_columns] = classification.loc[idx,:].values

    df=drop(df, drop_conditions)
    #print(df[list(worms_mapping.keys())].dtypes)

    df.rename(columns={"valid_aphiaID":"worms_aphiaID"}, inplace=True)

    print(f'            Done | before : {Nobs}, after : {len(df)} observations')

    return df


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


