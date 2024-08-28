#!/usr/bin/python

# External imports
import pandas as pd
import numpy as np
import argparse
from operator import itemgetter

from suds import null, WebFault
from suds.client import Client
from suds.sudsobject import items

import time

# Local imports
import filters.createwormsfilters as cwf
import filters.dropvalues as dropvalues




#Rank names in the GBIF file
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
                  'rank':'rank'
                 }



def _match_TaxaByHigherRanks(ranks1, ranks2, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN):

    #print(ranks1)
    #print(ranks2)
    #print()
    diff = (ranks1!=ranks2)
    isnan = (ranks1.isna() + ranks2.isna())
    match = pd.DataFrame(diff[~isnan].sum(axis=1).astype(int), columns=["nmismatch"])
    fullnan = isnan.sum(axis=1)==len(isnan.columns)
    isnan = isnan.any(axis=1)
    match["isnan"]=isnan

    #Naive matching, the level of non-matching ranks is not taken into account

    match.loc[isnan,"match"] = match.loc[isnan,"nmismatch"] <= allowed_mismatch_withNaN
    match.loc[~isnan,"match"] = match.loc[~isnan,"nmismatch"] <= allowed_mismatch_withoutNaN
    match.loc[fullnan,"match"] = False

    return match



def _match_TaxaByFullClassification(gbif_classif, worms_classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN, keep_fossil=False):

    gbifhigherranks = list(gbif_classif.columns)
    wormscolumns = list(worms_classif.columns)
    colnames = ["classif_matchtype"] + wormscolumns

    if any(worms_classif["worms_matchtype"]=="nomatch"):

        # No match in WoRMS

        if len(worms_classif)>1: # something wrong
            raise NotImplementedError("More than one candidate, but one is a 'nomatch'")

        else:
            match_idx = None
            classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)


    else:

        # WoRMS match

        match = _match_TaxaByHigherRanks(worms_classif.loc[:,gbifhigherranks], gbif_classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN)

        if any(match["match"]):

            # Higher ranks match

            if match["match"].sum()==1:

                # Only one full match

                match_idx = np.where(match["match"])[0][0]
                classif = pd.DataFrame([["near1"] + worms_classif.loc[match_idx,wormscolumns].values.flatten().tolist()], columns=colnames)

            else:

                # More than one full match

                candidates = match[match["nmismatch"]==match["nmismatch"].min()]

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

                else:

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
                        classif = pd.DataFrame([["near4"] + candidates.loc[:,wormscolumns].values.flatten().tolist()], columns=colnames)

                    elif len(candidates) > 1:

                        # Several candidates have the same classification and “accepted” status, only the authority changes
                        # They refer to the same species, so by default, keep the first one.

                        match_idx = candidates.index[0]
                        classif = pd.DataFrame([["near5"] + candidates.loc[0,wormscolumns].values.flatten().tolist()], columns=colnames)

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
 
       #worms_classif = worms_classif.drop(index=indexes).reset_index(drop=True)

    #if len(worms_classif)==0: # can occur after fossils have been removed

        #classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)


    return classif



def apply_matchfilter(classification, matchfilter=None, allowed_mismatch_withNaN=1, allowed_mismatch_withoutNaN=2, outputpath='./', keep_fossil=False):

    nclassification = len(classification)
    print(f'            * WoRMS filtering (recognized marine taxa) | {nclassification} unique classifications')

    columns = list(worms_mapping.keys())
    gbifhigherranks = list(set(RANK.values()) - set([RANK['species']]))

    if keep_fossil:
        del worms_mapping['extinct']

    if matchfilter is None:

        unique_species = classification[RANK['species']].unique.tolist()
        wormscall = dict(zip(list(worms_mapping.values()),list(worms_mapping.keys())))
        matchfilter = cwf.match_WoRMS(unique_species, store=True, wormscall=wormscall, overwrite=False, outputpath=outputpath)

    else:

        check_columns = ['group'] + columns
        if (len(check_columns)!=len(matchfilter.columns)) or any(np.sort(check_columns) != np.sort(matchfilter.columns)):
           raise KeyError(f"Filter column names must be: {check_columns}")

    filter = matchfilter.groupby(['group'])

    for idx in range(len(classification)):

        spe = tuple([classification.loc[idx,RANK['species']]])
        #print()
        worms_classif = filter.get_group(spe).reset_index(drop=True)
        gbif_classif = pd.DataFrame([classification.loc[idx,gbifhigherranks]]*len(worms_classif),columns=gbifhigherranks).reset_index(drop=True)
        #print(worms_classif)
        #print(gbif_classif)

        classif = _match_TaxaByFullClassification(gbif_classif, worms_classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN, keep_fossil=keep_fossil)

        if (classif["classif_matchtype"].values=="nomatch") or (classif["classif_matchtype"].values=="undecided"):

            classification.loc[idx,"classif_matchtype"] = classif["classif_matchtype"].values
            classification.loc[idx,["worms_matchtype","worms_status","valid_aphiaID"]] = pd.NA

        else:

            classification.loc[idx,columns + ["classif_matchtype"]] = classif[columns + ["classif_matchtype"]].values.flatten()


        if ((idx+1)%1000==0):

            # Display code progress

            classif = classification.iloc[:idx,:]
            Nnomatch = len(classif[classif["classif_matchtype"]=="nomatch"])
            Nmatch = len(classif) - Nnomatch
            percentage = np.round((idx+1)/nclassification*100,2)
            print(f'                Processing | {idx+1}/{nclassification} classifications done ({percentage}%): no_match={Nnomatch}, match={Nmatch}') 


    classification = classification[classification["classif_matchtype"]!="nomatch"]

    print(f'                Done | before: {nclassification}, after: {len(classification)} classifications')

    return classification



def apply_acceptedfilter(classification, acceptedfilter=None, outputpath='./'):

    if len(classification)==0:
        return classification

    unaccepted_idx = classification[(classification['worms_status']!="accepted") & (classification['worms_status']!="deleted") & (~pd.isnull(classification['valid_aphiaID']))].index
    nunaccepted = len(unaccepted_idx)

    if len(unaccepted_idx) != 0:

        print(f'            * WoRMS filtering (accepted taxa) | {nunaccepted} unaccepted taxa')

        if acceptedfilter is None:

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
        filter["unaccepted_idx"] = unaccepted_idx
        filter = filter[filter["rank"]=="Species"] #no subspecies
        unaccepted_idx = filter.loc[:,"unaccepted_idx"].tolist() 

        filter = filter[list(RANK.values())]
        classification.loc[unaccepted_idx, list(RANK.values())] = filter.values

        #classification.loc[unaccepted_idx, list(RANK.values())] = classification.loc[unaccepted_idx, "valid_aphiaID"].apply(lambda aphiaID : filter.loc[aphiaID,:])

    return classification



def clean_taxonomy(classification, allowed_mismatch_withNaN=1, allowed_mismatch_withoutNaN=2, matchfilter=None, acceptedfilter=None, outputpath='./', keep_fossil=False):

    # Match WoRMS

    classification = apply_matchfilter(classification, matchfilter=matchfilter, allowed_mismatch_withNaN=allowed_mismatch_withNaN, allowed_mismatch_withoutNaN=allowed_mismatch_withoutNaN, outputpath=outputpath, keep_fossil=keep_fossil)

    # Match accepted WoRMS

    classification = apply_acceptedfilter(classification, acceptedfilter=acceptedfilter, outputpath=outputpath)

    return classification



def apply(df, *ignored_args, allowed_mismatch_withNaN=1, allowed_mismatch_withoutNaN=2, matchfilter=None, acceptedfilter=None, keep_fossil=False, outputpath='./', drop_conditions={'classif_matchtype':'nomatch', 'worms_matchtype':'match_deleted'}):

    Nobs = len(df)

    new_columns = list(set(worms_mapping.keys()) - set(RANK.values()))

    if Nobs == 0:

        df.rename(columns={"species":"gbif_species"}, inplace=True)
        df = df.reindex(df.columns.tolist() + ["species", "classif_matchtype"] + new_columns, axis=1)

        return df

    columns = list(RANK.values())

    dfByClassification = df[columns].fillna('unk').groupby(columns, dropna=False) #get_group() doesn't work with NaN
    taxonomy = pd.DataFrame(list(dfByClassification.groups.keys()), columns=columns)

    classification = clean_taxonomy(taxonomy.replace('unk',pd.NA), allowed_mismatch_withNaN=allowed_mismatch_withNaN, allowed_mismatch_withoutNaN=allowed_mismatch_withoutNaN, acceptedfilter=acceptedfilter, matchfilter=matchfilter, outputpath=outputpath, keep_fossil=keep_fossil)


    df.rename(columns={"species":"gbif_species"}, inplace=True)
    df["species"]=pd.NA
    df["classif_matchtype"]="nomatch"
    df[new_columns] = pd.NA
    #df["worms_matchtype"]=pd.NA
    #df["worms_status"]=pd.NA
    #df["valid_aphiaID"]=pd.NA

    print(f'            * WoRMS filtering | Full dataset')


    classification_indexes = classification.index

    for idx in classification_indexes:

        group = tuple(taxonomy.iloc[idx,:].values)
        indexes = dfByClassification.get_group(group).index
        df.loc[indexes, classification.columns] = classification.loc[idx,:].values

    df = dropvalues.apply(df, **drop_conditions)


    df["valid_aphiaID"] = df["valid_aphiaID"].astype("Int64")
    df.rename(columns={"valid_aphiaID":"worms_aphiaID"}, inplace=True)

    print(f'                Done | before : {Nobs}, after : {len(df)} observations')

    return df
