#!/usr/bin/python
# coding: utf-8

# External import

import re
import os
import json
import time
import argparse
import requests
import pandas as pd
from tqdm import tqdm

from marinedb.utils.printverbose import printv

BASE_URL = "https://www.marinespecies.org/rest"
ENDPOINT = "AphiaClassificationByAphiaID"

RANK_COLUMNS_ALL = [
                "superdomain",
                "domain",
                "kingdom",
                "subkingdom",
                "infrakingdom",
                "phylum",
                "subphylum",
                "infraphylum",
                "superclass",
                "class",
                "subclass",
                "infraclass",
                "superorder",
                "order",
                "suborder",
                "infraorder",
                "superfamily",
                "family",
                "subfamily",
                "tribe",
                "subtribe",
                "genus",
                "subgenus",
                "species",
                "subspecies",
                ]

# but also: Gigaclass, Megaclass, Parvphylum, Section, Subsection, Subterclass

RANK_COLUMNS = [
                "kingdom",
                "phylum",
                "class",
                "order",
                "family",
                "genus",
                "species"
                ]

RANK_PATTERN = re.compile(
    r"^(" + "|".join(sorted(map(re.escape, RANK_COLUMNS), key=len, reverse=True)) + r")\b",
    flags=re.IGNORECASE,
)

# for example: "Phylum (Division)"

def normalize_rank(rank):
    if rank is None:
        return None

    rank = str(rank).strip().lower()
    match = RANK_PATTERN.search(rank)

    if match is None:
        return None

    return match.group(1).lower()

def fetch_aphia_classification(aphia_id, session, max_attempt=10, pause_duration=20, timeout=30):

    url = f"{BASE_URL}/{ENDPOINT}/{int(aphia_id)}"

    last_err = None

    for attempt in range(1, max_attempt + 1):

        try:

            response = session.get(url, timeout=timeout, headers={"User-Agent": "WoRMS-classification-script/1.0"})
            response.raise_for_status()
            return response.json()

        except Exception as err:

            last_err = err

            if attempt < max_attempt:
                time.sleep(pause_duration)
            else:
                raise RuntimeError(
                    f"Failed to fetch classification for AphiaID={aphia_id}: {type(last_err).__name__}: {last_err}"
                )

def flatten_classification_tree(classification):

    levels = []
    current = classification

    while isinstance(current, dict):

        levels.append({
            "AphiaID": current.get("AphiaID"),
            "rank": current.get("rank"),
            "scientificname": current.get("scientificname"),
        })

        current = current.get("child")

    return levels

def add_nodes_to_taxon_dict(classification, taxon_dict):
    """
    Example
    -------
        {
            "123": {
                "rank": "Species",
                "scientificname": "Abra alba"
            }
        }
    """

    for level in flatten_classification_tree(classification):

        aphia_id = level.get("AphiaID")

        if aphia_id is None:
            continue

        taxon_dict[str(aphia_id)] = {
            "rank": level.get("rank"),
            "scientificname": level.get("scientificname"),
        }

def classification_to_wide_row(input_aphia_id, classification, unknown_ranks=None):

    row = {"input_AphiaID": input_aphia_id }

    for rank in RANK_COLUMNS:
#        row[rank] = pd.NA
        row[f"{rank}_AphiaID"] = pd.NA

    if classification is None:
        row["classification_status"] = "not_found"
        return row

    row["classification_status"] = "found"

    if unknown_ranks is None:
        unknown_ranks = set()

    for level in flatten_classification_tree(classification):

        rank = level["rank"]

        if rank is None:
            continue

        rank_key = normalize_rank(level.get("rank"))

        if rank_key in RANK_COLUMNS:
#            row[rank_key] = level["scientificname"]
            row[f"{rank_key}_AphiaID"] = level["AphiaID"]
        else:
            unknown_ranks.add(level.get("rank"))

    return row, unknown_ranks

def save(rows, taxon_dict, output_file_txt, output_file_json, verbose=True, init=''):

    out = pd.DataFrame(rows)

    printv(f"[INFO] Storing in {output_file_txt}", verbose=verbose, init=init)
    printv(f"[INFO] Storing in {output_file_json}", verbose=verbose, init=init)

    out.to_csv(output_file_txt, sep="\t", index=False)

    with open(output_file_json, "w", encoding="utf-8") as f:
        json.dump(taxon_dict, f, ensure_ascii=False, indent=4, sort_keys=True)

    return output_file_txt

def main(file, aphiaid_column, max_attempt=10, pause_duration=20, timeout=30):

    input_dir = os.path.dirname(file)
    name, ext = os.path.splitext(file)
    output_file_txt = name + "_worms_classification" + ext
    output_file_json = os.path.join(input_dir,"aphiaid_taxon_mapping.json")

    df = pd.read_csv(file, sep="\t")

    if aphiaid_column not in df.columns:
        raise ValueError(
            f"Column {args.aphiaid_column!r} not found in {args.file}. "
            f"Available columns: {list(df.columns)}"
        )

    aphia_ids = df[aphiaid_column].dropna().astype(int).drop_duplicates().tolist()

    print(f"[INFO] {len(aphia_ids)} unique AphiaIDs")

    rows = []
    taxon_dict = {}
    unknown_ranks = set()
    n_request = 0

    with requests.Session() as session:

        for aphia_id in tqdm(aphia_ids):

            classification = fetch_aphia_classification(
                aphia_id,
                session=session,
                max_attempt=max_attempt,
                pause_duration=pause_duration,
                timeout=timeout,
            )

            row, unknown_ranks = classification_to_wide_row(input_aphia_id=aphia_id, classification=classification, unknown_ranks=unknown_ranks)
            rows.append(row)

            if classification is not None:
                add_nodes_to_taxon_dict(classification, taxon_dict)

            n_request += 1
            if n_request == 1000:
                save(rows, taxon_dict, output_file_txt, output_file_json, verbose=False)
                n_request = 0

    if len(unknown_ranks) != 0:
        print("[INFO] Unknown ranks:", sorted(list(unknown_ranks)))

    save(rows, taxon_dict, output_file_txt, output_file_json, verbose=True)

    return output_file_txt

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=str)
    parser.add_argument("--aphiaid-column", type=str, default="AphiaID", help="Name of the column containing the AphiaIDs")
    parser.add_argument("--max-attempt", type=int, default=10)
    parser.add_argument("--pause-duration", type=float, default=20)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()

    file = args.file
    aphiaid_column = args.aphiaid_column
    max_attempt = args.max_attempt
    pause_duration = args.pause_duration
    timeout = args.timeout

    main(file, aphiaid_column=aphiaid_column, max_attempt=max_attempt, pause_duration=pause_duration, timeout=timeout)
