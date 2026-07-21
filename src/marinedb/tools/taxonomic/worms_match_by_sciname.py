import pandas as pd
import argparse
from tqdm import tqdm
import math
import requests
import time
import os

WORMSCALL = [
             'AphiaID',
             'scientificname',
             'genus',
             'family',
             'order',
             'class',
             'phylum',
             'kingdom',
             'authority',
             'status',
             'rank',
             'valid_AphiaID',
             'parentNameUsageID',
             'originalNameUsageID',
             'isExtinct',
             'isMarine',
             'isBrackish',
             'isFreshwater',
             'isTerrestrial',
             'match_type'
            ]

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=str)
    parser.add_argument('--marine-only', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--extant-only', action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    if args.marine_only:
        marine_only = "true"
    else:
        marine_only = "false"

    if args.extant_only:
        extant_only = "true"
    else:
        extant_only = "false"


    url = "https://www.marinespecies.org/rest/AphiaRecordsByMatchNames"
    params = {
        "marine_only": marine_only,
        "extant_only": extant_only
    }


    species = pd.read_csv(args.file, sep='\t')['species'].tolist()

    res = []
    nspecies = 0

    nbatch = math.ceil(len(species) / 50)
    print(f'{nbatch} batches')

    for i in tqdm(range(nbatch)):

        retry = 0
        params["scientificnames[]"] = species[i*50:i*50+50]

        array_of_results_array = requests.get(url, params=params).json()

        while ((len(array_of_results_array) == 0) or (len(array_of_results_array) != len(params["scientificnames[]"]))) and (retry <= 20):
            retry += 1
            print(f'retry n°{retry}')
            print(params["scientificnames[]"])
            raise Exception

        for k,results_array in enumerate(array_of_results_array):

            nspecies += 1

            if len(results_array) == 0:
                worms_data = [species[i*50+k], 'nomatch'] + [pd.NA] * len(WORMSCALL)
                res.append(worms_data)

            for aphia_object in results_array:

                if aphia_object['status'] not in ["quarantined","deleted"]:
                    worms_data = [species[i*50+k], 'match'] + [aphia_object[v] for v in WORMSCALL]
                    res.append(worms_data)

                else:
                    worms_data = [species[i*50+k], 'quarantined_deleted'] + [pd.NA] * len(WORMSCALL)
                    res.append(worms_data)

    res = pd.DataFrame(res, columns=['input_sciname','match']+WORMSCALL)
    name, ext = os.path.splitext(args.file)
    outputfile = name + '_worms' + ext
    print(f'[INFO] Storing in {outputfile}')
    res.to_csv(outputfile, sep='\t', mode='w', index=False)
