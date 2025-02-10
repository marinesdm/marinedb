#!/usr/bin/python

# External imports
import pandas as pd
import numpy as np
import argparse
from operator import itemgetter

import sys

from suds import null, WebFault
from suds.client import Client
from suds.sudsobject import items
import inspect

import time

# Local imports
import getwormsfilters as gwf
import dropvalues as dropvalues




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


#Matching conditions
#allowed_mismatch_withoutNaN = 2
#allowed_mismatch_withNaN = 1


#WoRMS
#cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1', timeout=4000)

#scinames = cl.factory.create('scientificnames')
#scinames["_arrayType"] = "string[]"

#aphiaID = cl.factory.create("aphiaids")
#aphiaID["_arrayType"] = "int[]"

worms_mapping = {
                  RANK['species']:'scientificname',
                  RANK['genus']:'genus',
                  RANK['family']:'family',
                  RANK['order']:'order',
                  RANK['class']:'cls',
                  RANK['phylum']:'phylum',
                  RANK['kingdom']:'kingdom',
                  'matchtype_species':'match_type',
                  'status':'status',
                  'valid_aphiaID':'valid_AphiaID',
                  'extinct':'isExtinct'
                 }



def match_TaxaByHigherRanks(ranks1, ranks2, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN):
    
    #print(ranks1)
    #print(ranks2)
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

def match_TaxaByFullClassification(gbif_classif, worms_classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN, keep_fossil=False):

    gbifhigherranks = list(gbif_classif.columns)
    wormscolumns = list(worms_classif.columns)
    colnames = ["matchtype_classif"] + wormscolumns

    # Remove fossils

    if not keep_fossil:

        indexes = worms_classif[worms_classif["isExtinct"]==1].index
        worms_classif = worms_classif.drop(index=indexes).reset_index(drop=True)

    if len(worms_classif)==0: # can occur after fossils have been removed

        classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)

    elif any(worms_classif["matchtype_species"]=="nomatch"):

        # No match in WoRMS

        if len(worms_classif)>1: # something wrong
            raise NotImplementedError("More than one candidate, but one is a 'nomatch'")

        else:
            classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)

    else:

        # WoRMS match

        match = match_TaxaByHigherRanks(worms_classif.loc[:,gbifhigherranks], gbif_classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN)

        if any(match["match"]):

            # Higher ranks match

            if match["match"].sum()==1:

                # Only one full match

                match_idx = np.where(match["match"])[0][0]
                #print(['bli']+worms_classif.loc[match_idx,wormscolumns].values.flatten())
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
                    candidates = candidates[candidates["status"]=="accepted"] 

                    #In GBIF, the `species` value corresponds to the accepted name
                    #for the species from the GBIF backbone matched to this occurrence
                    #If in doubt, choose the taxon accepted in WoRMS

                    if len(candidates) == 1:

                        # Keep the candidate with:
                        # - the lowest number of mismatches
                        # - the lowest number of missing values
                        # - and whose status is "accepted"
                        
                        classif = pd.DataFrame([["near4"] + candidates.loc[:,wormscolumns].values.flatten().tolist()], columns=colnames)

                    else:

                        # Impossible to decide, check by hand
                        
                        classif = pd.DataFrame([["undecided"] + [pd.NA]*len(wormscolumns)], columns=colnames)
        else:

            # No match for higher ranks

            candidates = worms_classif[worms_classif["matchtype_species"].isin(["exact","exact_subgenus"])] #(["exact","exact_subgenus","phonetic","near_1"])]

            if len(candidates)!=0:

                # If the species match is high, check by hand
                
                classif = pd.DataFrame([["undecided"] + [pd.NA]*len(wormscolumns)], columns=colnames)

            else:

                classif = pd.DataFrame([["nomatch"] + [pd.NA]*len(wormscolumns)], columns=colnames)

    print(classif["matchtype_species"]=="match_quarantine")
    
    return classif


def apply_matchfilter(classification, matchfilter=None, allowed_mismatch_withNaN=1, allowed_mismatch_withoutNaN=2, outputpath='./', keep_fossil=False):

    #unique_species = classification[RANK['species']].unique().tolist()
    nclassification = len(classification)
    print(f'            * WoRMS filtering (recognized marine taxa) | {nclassification} unique classifications')

    columns = list(worms_mapping.keys())
    gbifhigherranks = list(set(RANK.values()) - set([RANK['species']]))

    if keep_fossil:

        del worms_mapping['extinct']

    if matchfilter is None:

        unique_species = classification[RANK['species']].unique.tolist()
        wormscall = dict(zip(list(worms_mapping.values()),list(worms_mapping.keys())))
        matchfilter = gwf.match_WoRMS(unique_species, store=True, wormscall=wormscall, overwrite=False, outputpath=outputpath)

    else:

        check_columns = ['group'] + columns
        if (len(check_columns)!=len(matchfilter.columns)) or any(np.sort(check_columns) != np.sort(matchfilter.columns)):
           raise KeyError(f"Filter column names must be: {check_columns}")
    
    filter = matchfilter.groupby(['group'])

    for idx in range(len(classification)):
        #try:
            #spe = tuple([classification.loc[idx,RANK['species']]])        
            #worms_classif = filter.get_group(spe).reset_index(drop=True)
        #except KeyError:
            #print(classification.loc[idx,:])
            #sys.exit(1)

        spe = tuple([classification.loc[idx,RANK['species']]])
        worms_classif = filter.get_group(spe).reset_index(drop=True)
        #worms_classif = filter.get_group(classification.loc[idx,RANK['species']])
        gbif_classif = pd.DataFrame([classification.loc[idx,gbifhigherranks]]*len(worms_classif),columns=gbifhigherranks).reset_index(drop=True)

        classif = match_TaxaByFullClassification(gbif_classif, worms_classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN, keep_fossil=keep_fossil)
        #print(classif["matchtype_classif"].values=="nomatch")
        if (classif["matchtype_classif"].values=="nomatch") or (classif["matchtype_classif"].values=="undecided"):
            
            classification.loc[idx,"matchtype_classif"] = classif["matchtype_classif"].values
            classification.loc[idx,["matchtype_species","status","valid_aphiaID"]] = pd.NA

        else:
            classification.loc[idx,columns + ["matchtype_classif"]] = classif[columns + ["matchtype_classif"]].values.flatten()

        if ((idx+1)%1000==0):

            # Display code progress

            classif = classification.iloc[:idx,:]
            Nnomatch = len(classif[classif["matchtype_classif"]=="nomatch"])
            Nmatch = len(classif) - Nnomatch
            percentage = np.round((idx+1)/nclassification*100,2)
            print(f'                Processing | {idx+1}/{nclassification} classifications done ({percentage}%): no_match={Nnomatch}, match={Nmatch}') 
    
    classification = classification[classification["matchtype_classif"]!="nomatch"]
    
    print(f'                Done | before: {nclassification}, after: {len(classification)} classifications')
    print("worms :", any(classification["matchtype_classif"]=="match_quarantine"))

    return classification


def apply_acceptedfilter(classification, acceptedfilter=None, outputpath='./'):

    if len(classification)==0:
        return classification

    unaccepted_idx = classification[(classification['status']!="accepted") & (classification['status']!="deleted") & (~pd.isnull(classification['valid_aphiaID']))].index
    nunaccepted = len(unaccepted_idx)

    print("accepted")
    print(len(classification))

    if len(unaccepted_idx) != 0:

        print(f'            * WoRMS filtering (accepted taxa) | {nunaccepted} unaccepted taxa')

        if acceptedfilter is None:
        
            valid_aphiaID = classification.loc[unaccepted_idx,"valid_aphiaID"].unique().tolist()
            acceptedfilter = gwf.get_AcceptedWoRMS(valid_aphiaID, store=True, overwrite=False, outputpath=outputpath)

        else:

            check_columns = ["group"] + list(worms_mapping.keys())
            if (len(check_columns)!=len(acceptedfilter.columns)) or any(np.sort(check_columns) != np.sort(acceptedfilter.columns)):
                raise KeyError(f"Filter column names must be: {check_columns}")

        if len(acceptedfilter['group'].unique()) != len(acceptedfilter):
            #duplicates = acceptedfilter.loc[acceptedfilter.duplicated(subset=['valid_aphiaID'], keep=False)==True,'valid_aphiaID']
            #if any(~pd.isnull(duplicates)):
            raise Exception(f"The filter of accepted species names must not contain duplicates for the `valid_aphiaID` column.")
        
        filter = acceptedfilter.set_index(['group'])
        filter = filter[list(RANK.values())]

        classification.loc[unaccepted_idx, list(RANK.values())] = classification.loc[unaccepted_idx, "valid_aphiaID"].apply(lambda aphiaID : filter.loc[aphiaID,:])

    print(len(classification))

    return classification


def clean_taxonomy(classification, allowed_mismatch_withNaN=1, allowed_mismatch_withoutNaN=2, matchfilter=None, acceptedfilter=None, outputpath='./', keep_fossil=False):

    # Match WoRMS
        
    classification = apply_matchfilter(classification, matchfilter=matchfilter, allowed_mismatch_withNaN=allowed_mismatch_withNaN, allowed_mismatch_withoutNaN=allowed_mismatch_withoutNaN, outputpath=outputpath, keep_fossil=keep_fossil)

    # Match accepted WoRMS

    classification = apply_acceptedfilter(classification, acceptedfilter=acceptedfilter, outputpath=outputpath)

    return classification


def apply(df, *ignored_args, allowed_mismatch_withNaN=1, allowed_mismatch_withoutNaN=2, matchfilter=None, acceptedfilter=None, outputpath='./', drop_conditions={'matchtype_classif':'nomatch', 'matchtype_species':'match_deleted'}):

    Nobs = len(df)

    if Nobs == 0:
        #print(df)
        df.rename(columns={"species":"gbif_species"}, inplace=True)
        df = df.reindex(df.columns.tolist() + ["species", "matchtype_classif", "matchtype_species", "status", "valid_aphiaID"], axis=1)
        #print(df)
        return df

    #if matchfilter is not None:
        #matchfilter = pd.read_csv(matchfilter_path, sep='\t')

    #if acceptedfilter is not None:
        #acceptedfilter = pd.read_csv(acceptedfilter_path, sep='\t')

    columns = list(RANK.values())

    dfByClassification = df[columns].fillna('unk').groupby(columns, dropna=False) #['gbifID']
    taxonomy = pd.DataFrame(list(dfByClassification.groups.keys()), columns=columns)
    #taxonomy=dfByclassification.count().reset_index().drop(columns=['gbifID'])

    classification = clean_taxonomy(taxonomy.replace('unk',pd.NA), allowed_mismatch_withNaN=allowed_mismatch_withNaN, allowed_mismatch_withoutNaN=allowed_mismatch_withoutNaN, acceptedfilter=acceptedfilter, matchfilter=matchfilter, outputpath=outputpath)
    

    df.rename(columns={"species":"gbif_species"}, inplace=True)
    df["species"]=pd.NA
    df["matchtype_classif"]="nomatch"
    df["matchtype_species"]=pd.NA
    df["status"]=pd.NA
    df["valid_aphiaID"]=pd.NA

    print(f'            * WoRMS filtering | Full dataset')

    #taxonomy = taxonomy.replace(pd.NA,-1)
    classification_indexes = classification.index
    for idx in classification_indexes:
        group = tuple(taxonomy.iloc[idx,:].values)
        indexes = dfByClassification.get_group(group).index
        df.loc[indexes, classification.columns] = classification.loc[idx,:].values

    df = dropvalues.apply(df, **drop_conditions)

    #or_condition = None
    #for key, value in conditions.items():

        #if isinstance(value,list | tuple):
        #    condition = df[key].isin(value)
        #else:
        #    condition = df[key] == value

        #if or_condition is None:
        #    or_condition = condition
        #else:
        #    or_condition = or_condition | condition

    #df = df[~or_condition].reset_index(drop=True)

    #df = df[(df['matchtype_classif']!='nomatch') & (df['matchtype_species']!='match_deleted')].reset_index(drop=True)


    df["valid_aphiaID"] = df["valid_aphiaID"].astype("Int64")

    print(f'                Done | before : {Nobs}, after : {len(df)} observations')

    return df



def _match_TaxaByClassification(classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN):
    
    print(f'                    ** WoRMS API call')
    scinames["scientificname"] = list(classif[RANK["species"]])
    results = cl.service.matchAphiaRecordsByNames(scinames, marine_only="true")

    classif["matchtype"]="nomatch"
    classif["matchtype_worms"]=None
    classif["status"]="unknown"
    classif["valid_aphiaID"]=None

    wormsranks = list(wormsrank_mapping.keys())
    wormscall = wormsranks + ['match_type', 'status', 'valid_AphiaID']
    gbifhigherranks = list(set(RANK.values()) - set([RANK['species']]))
    columns = list(itemgetter(*wormsranks)(wormsrank_mapping)) + ["matchtype_worms", "status", "valid_aphiaID"]
    
    print(f'                    ** WoRMS/GBIF match')
    for idx, resultsBySciname in enumerate(results):

         if len(resultsBySciname)!=0:
              worms_classif=[]
              for taxonomy in resultsBySciname:
                  taxonomy = dict(items(taxonomy))
                  worms_classif.append(itemgetter(*wormscall)(taxonomy))
    #COUPER EN DEUX ICI : trouver classif dans fonction séparée , partie avant = getwormsfilters.match_ClassificationByScinames OU direct matchfilter csv              
              worms_classif = pd.DataFrame(worms_classif,columns=columns)
              gbif_classif = pd.DataFrame([classif.loc[idx,gbifhigherranks]]*len(worms_classif),columns=gbifhigherranks).reset_index(drop=True)
              match = match_HigherRanks(worms_classif.loc[:,gbifhigherranks], gbif_classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN)
              if any(match["match"]):

                  if match["match"].sum()==1:
                      classif.loc[idx,"matchtype"]="worms_classif_near1"
                      match_idx = np.where(match["match"])[0][0]
                      classif.loc[idx, columns] = worms_classif.loc[match_idx, columns].values

                  else:

                      candidates = match[match["nmismatch"]==match["nmismatch"].min()]

                      if len(candidates) == 1:
                          classif.loc[idx,"matchtype"]="worms_classif_near2"
                          match_idx = candidates.index[0]
                          classif.loc[idx, columns] = worms_classif.loc[match_idx, columns].values

                      elif candidates["isnan"].sum()==1: #not tested
                          classif.loc[idx,"matchtype"]="worms_classif_near3"
                          match_idx = np.where(candidates["isnan"])[0][0]
                          classif.loc[idx, columns] = worms_classif.loc[match_idx, columns].values

                      else:
                          candidates = worms_classif[worms_classif["status"]=="accepted"] 
                          #In GBIF, the `species` value corresponds to the accepted name
                          #If in doubt, choose the taxon accepted in WoRMS
                          if len(candidates) == 1:
                              classif.loc[idx,"matchtype"] = "worms_classif_near4"
                              classif.loc[idx, columns] = candidates.loc[:,columns].values
                          else:
                              classif.loc[idx,"matchtype"] = "worms_classif_undecided"
              else:

                  candidates = worms_classif[worms_classif["matchtype_worms"].isin(["exact","exact_subgenus","phonetic","near_1"])]

                  if len(candidates)!=0:
                      classif.loc[idx,"matchtype"] = "worms_classif_nomatch"
    
    return classif


def _get_AcceptedClassification(valid_aphiaID): 

    aphiaID["aphiaids"] = valid_aphiaID
    results = cl.service.getAphiaRecordsByIDs(aphiaID)

    classif = []
    keys = list(wormsrank_mapping.keys())
    for result in results:
        classif.append(itemgetter(*keys)(result))

    classif = pd.DataFrame(classif,columns=itemgetter(*keys)(wormsrank_mapping))

    return classif


def _apply(df, *ignored_args, allowed_mismatch_withNaN=1, allowed_mismatch_withoutNaN=2):

    if len(df) == 0:
        return df

    dfByclassification = df.groupby(list(RANK.values()), dropna=False)['gbifID']
    taxonomy=dfByclassification.count().reset_index().drop(columns=['gbifID'])
    nclassification = len(taxonomy)
    print(f'            * WoRMS filtering (recognized marine taxa) | {nclassification} unique classifications')
    

    nbatch = int(np.ceil(nclassification/50))
    for batch in range(nbatch):
        
        start_idx = batch*50
        if batch == (nbatch-1):
            end_idx = nclassification
        else:
            end_idx = start_idx + 50

        classif = taxonomy.iloc[start_idx:end_idx,:].copy(deep=True).reset_index(drop=True)
        classif = match_TaxaByClassification(classif, allowed_mismatch_withNaN, allowed_mismatch_withoutNaN)

        if batch==0:
            classif_clean = classif #classif.values
        else:
            #classif_clean = np.concatenate((classif_clean,classif.values), axis=0)
            classif_clean = pd.concat([classif_clean,classif], axis=0, ignore_index=True)

        nnomatch = len(classif[classif["matchtype_classif"]=="nomatch"])
        nmatch = len(classif) - nnomatch
        done = ((batch - 1)*50 + 50) + (end_idx-start_idx)
        percentage = np.round(done/nclassification*100,2)
        print(f'                Processing | {done}/{nclassification} classifications done ({percentage}%): no_match={nnomatch}, match={nmatch}') 
    
    classif_clean = classif_clean[classif_clean["matchtype_classif"]!="nomatch"]
    print(f'                Done | before: {nclassification}, after: {len(classif_clean)} classifications')

    unaccepted_idx = classif_clean[(classif_clean['status']!="accepted") & (~pd.isnull(classif_clean['valid_aphiaID']))].index
    nunaccepted = len(unaccepted_idx)
    if len(unaccepted_idx) != 0:

        print(f'            * WoRMS filtering (accepted taxa) | {nunaccepted} unaccepted taxa')

        nbatch = int(np.ceil(len(unaccepted_idx)/50))
        for batch in range(nbatch):
        
            start_idx = batch*50
            if batch == (nbatch-1):
                end_idx = nunaccepted
            else:
                end_idx = start_idx + 50
        
            valid_aphiaID = list(classif_clean.loc[unaccepted_idx[start_idx:end_idx],"valid_aphiaID"].values)
            classif = get_AcceptedClassification(valid_aphiaID)
            
            if batch==0:
                classif_accepted = classif
            else:
                classif_accepted = pd.concat([classif_accepted,classif], axis=0, ignore_index=True)

            done = ((batch - 1)*50 + 50) + (end_idx-start_idx)
            percentage = np.round(done/nunaccepted*100,2)
            print(f'                Processing | {done}/{nunaccepted} taxa done ({percentage}%)')

        classif_clean.loc[unaccepted_idx, classif_accepted.columns] = classif_accepted.values

    #à supprimer quand ça fonctionnera (sauf peut-être nomatch pour éliminer facilement ce qu'il reste ?)
    df["matchtype_classif"]="nomatch"
    df["matchtype_species"]=None
    df["status"]="unknown"
    df["valid_aphiaID"]=None

    print(f'            * WoRMS filtering | Full dataset')
    classif_idx = classif_clean.index
    for idx in classif_idx:
        group = tuple(taxonomy.iloc[idx,:].values)
        gbifID = dfByclassification.get_group(group)
        df.loc[df['gbifID'].isin(gbifID), classif_clean.columns] = classif_clean.loc[idx,:].values

    df = df[(df['matchtype_classif']!='nomatch') & (df['matchtype_species']!='match_deleted')].reset_index(drop=True)

    return df


if __name__ == '__main__':

    import csv
    
    parser = argparse.ArgumentParser(description='WoRMS taxon filtering')
    parser.add_argument('gbif_tsv_file', type=str, help='path to the tab-separated file from GBIF to be processed (must fit in RAM)')   
    parser.add_argument('--matchfilter', type=str, help='path to the tab-separated file containing WoRMS matches')
    parser.add_argument('--acceptedfilter', type=str, help='path to the tab-separated file containing taxonomies accepted by WoRMS')
    parser.add_argument('--output_path', type=str, help='path to folder where output files will be stored', default='./')
    args = parser.parse_args()

    
    start=time.time()
    
    df = pd.read_csv(args.gbif_tsv_file, sep='\t',quoting=csv.QUOTE_NONE, quotechar='"')
    matchfilter = pd.read_csv(args.matchfilter, sep='\t')
    acceptedfilter = pd.read_csv(args.acceptedfilter, sep='\t')

    df = apply(df, matchfilter=matchfilter, acceptedfilter=acceptedfilter)

    end=time.time()

    outputfile = args.output_path + 'gbif_clean.tsv'

    print(f'            * Storing in  {outputfile} | time: {np.round(end - start,2)}s')
    df.to_csv(outputfile, sep='\t',index=False)

