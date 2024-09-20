import yaml
import pathlib

def apply(identification_level):

    rankfile_path = str(pathlib.Path(__file__).parent.resolve()) + '/taxonomic_ranks.yaml'

    with open(rankfile_path,'r') as file:
        rankfile=yaml.safe_load(file)
        ranks=rankfile['ascending_ranks']
        eqranks=rankfile['equivalent_ranks']

    identification_level=identification_level.lower()

    try:
        index=ranks.index(identification_level)
    except ValueError:
        if identification_level not in eqranks.keys():
            raise ValueError(f'{identification_level}: Unknown identification level. See `taxonomic_ranks.yaml`.')
        else:
            identification_level=eqranks[identification_level]
            index=ranks.index(identification_level)

    return ranks[index+1:]
