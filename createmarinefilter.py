import glob

import argparse
import numpy as np
import pandas as pd
from tqdm import tqdm

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Extract marine occurrence indexes')
    parser.add_argument('dir', type=str, help='path to directory containing files to be processed')
    parser.add_argument('--output_file', type=str, help='output file path', default='marine_filter.csv')
    args = parser.parse_args()

    files = sorted(glob.glob(args.dir + '*'))
    initialize=True

    for file in tqdm(files, total=len(files)):

        df_file = pd.read_csv(file, header=0)
        df_file = df_file[~df_file.is_land]

        if initialize and len(df_file) != 0:

            gbif_ocean = df_file[["index","mask","latitude","longitude"]].values
            initialize=False

        elif len(df_file) != 0:
            gbif_ocean = np.append(gbif_ocean, df_file[["index","mask","latitude","longitude"]].values, axis=0)

    gbif_ocean = pd.DataFrame(gbif_ocean, columns=["index","mask","latitude","longitude"])
    gbif_ocean["index"] = gbif_ocean["index"].astype(int)
    gbif_ocean.to_csv(args.output_file,index=False)
