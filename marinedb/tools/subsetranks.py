import yaml
import pathlib
from operator import itemgetter

def _add_alternativeranks(ranks, eqranks):
    alternative_ranks = list(eqranks.keys())
    add = [r for r in alternative_ranks if eqranks[r] in ranks]
    return ranks + add

def apply(identification_level, lower=False, strict=True):

    rankfile_path = str(pathlib.Path(__file__).parent.resolve()) + '/taxonomicRanks.yaml'

    with open(rankfile_path,'r') as file:
        rankfile=yaml.safe_load(file)
        ranks=rankfile['ascending_ranks']
        eqranks=rankfile['equivalent_ranks']

    identification_level=identification_level.lower()

    try:
        index=ranks.index(identification_level)
    except ValueError:
        if identification_level not in eqranks.keys():
            raise ValueError(f'{identification_level} is an unknown identification level. See `taxonomic_ranks.yaml`.')
        else:
            identification_level=eqranks[identification_level]
            index=ranks.index(identification_level)

    if lower:
        if strict:
            ranks=ranks[:index]
        else:
            ranks=ranks[:index+1]
    else:
        if strict:
            ranks=ranks[index+1:]
        else:
            ranks=ranks[index:]

    return _add_alternativeranks(ranks, eqranks)
