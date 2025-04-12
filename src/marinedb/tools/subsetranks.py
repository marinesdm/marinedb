#!/usr/bin/python
# coding: utf-8

# External import

import os
import yaml
import pathlib

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

def add_alternativeranks(ranks, eqranks):

    alternative_ranks = list(eqranks.keys())
    add = [r for r in alternative_ranks if eqranks[r] in ranks]

    return ranks + add

@export
def apply(identification_level, lower=False, strict=True):

    # Load `taxonomicRanks.yaml` file

    rankfile_path = os.path.join(pathlib.Path(__file__).parent.resolve(), 'taxonomicRanks.yaml')

    with open(rankfile_path,'r') as file:
        rankfile = yaml.safe_load(file)
        ranks = rankfile['ascending_ranks']
        eqranks = rankfile['equivalent_ranks']

    identification_level = identification_level.lower()

    # Retrieve all taxonomic ranks either below or above `identification_level`, depending on `lower`
    # Include the rank itself unless `strict` is True

    try:
        index = ranks.index(identification_level)
    except ValueError:
        if identification_level not in eqranks.keys():
            raise ValueError(f"`subsetranks.py` | identification_level='{identification_level}' is not a recognized taxonomic rank. See `taxonomic_ranks.yaml` for accepted values.")
        else:
            identification_level = eqranks[identification_level]
            index = ranks.index(identification_level)

    if lower:
        if strict:
            ranks = ranks[:index]
        else:
            ranks = ranks[:index+1]
    else:
        if strict:
            ranks = ranks[index+1:]
        else:
            ranks = ranks[index:]

    # Add equivalent rank names to handle alternate naming conventions

    ranks = add_alternativeranks(ranks, eqranks)

    return ranks
