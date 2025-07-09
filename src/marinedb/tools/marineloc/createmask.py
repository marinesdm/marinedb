#!/usr/bin/python
# coding: utf-8

# External import

from importlib.resources import files
import numpy as np
import argparse
import cv2
import os

# Internal import

from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv

# Global variable

__all__ = [] # populated using the @export decorator

GLOBEMASK_PATH = files('marinedb.tools.data').joinpath('globe_mask.npz')

@export
def apply(kernel_type='square', kernel_size=51, outputdir='./', verbose=True, indent=''):

    printv(f'* Load the land/sea mask from {GLOBEMASK_PATH}', verbose=verbose, indent=indent)

    data = np.load(GLOBEMASK_PATH)
    mask_globe = data['mask'].copy()
    lat_globe = data['lat']
    lon_globe = data['lon']

    mask_globe = mask_globe.astype('uint8')

    # Identify locations that can be easily classified as land or sea,
    # i.e., those that are not on the coast
    # note: the morphological gradient is the difference between dilation and erosion of an image

    printv('* Generate the land/sea/coast mask', verbose=verbose, indent=indent)

    if kernel_type == 'square':
        # square kernel
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
    elif kernel_type == 'ellipse':
        # elliptical kernel
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(kernel_size, kernel_size))
    else:
        raise ValueError(f"`createmask.py` | `kernel_type` must be either 'square' or 'ellipse', got '{args.kernel_type}'")

    gradient_mask_globe = cv2.morphologyEx(mask_globe, cv2.MORPH_GRADIENT, kernel)

    # Create the final mask distinguishing land, sea, and coast

    full_mask_globe = np.maximum(gradient_mask_globe*2, mask_globe)

    # Store

    outputfile = os.path.join(outputdir,'globe_mask_coastline.npz')

    printv(f'* Save the land/sea/coast mask to {outputfile}', verbose=verbose, indent=indent)

    np.savez_compressed(outputfile, lat=lat_globe, lon=lon_globe, mask=full_mask_globe)

    return outputfile

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Generate a mask differentiating land, sea, and coast', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--kernel-type', type=str, help='kernel type (square or ellipse)', default='square')
    parser.add_argument('--kernel-size', type=int, help='kernel size', default=51)
    parser.add_argument('--outputdir', type=str, help='path to the directory where the output .npz file will be stored', default='./')
    args = parser.parse_args()

    # Load the GLOBE mask

    print(f'`createmask.py` | Generate a mask differentiating land, sea, and coast')

    _ = apply(kernel_type=args.kernel_type, kernel_size=args.kernel_size, outputdir=args.outputdir)
