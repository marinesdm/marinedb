#!/usr/bin/python
# coding: utf-8

# External import

import os
import time

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variable

__all__ = [] # populated using the @export decorator

@export
def to_txt(df, txt_filename, init=False, verbose=False, indent=''):

    printv(f'Storing in {txt_filename} | {len(df)} observations', indent=indent, verbose=verbose)

    if init:
        if os.path.isfile(txt_filename):
            printv(f"WARNING | {txt_filename} already exists and will be overwritten", verbose=verbose, indent=indent)
            time.sleep(1)
        df.to_csv(txt_filename, mode='w', index=False, header=True, sep='\t')
    else:
        df.to_csv(txt_filename, mode='a', index=False, header=False, sep='\t')

    return True

