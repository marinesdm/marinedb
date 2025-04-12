#!/usr/bin/python
# coding: utf-8

# External import

import numpy as np
import argparse
import cv2
import os

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Generate a mask differentiating land, sea, and coast', formatter_class=arggparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--dirpath', type=str, help='directory containing the GLOBE mask', default='./')
    args = parser.parse_args()

    directory = args.dirpath

    # Load the GLOBE mask

    data = np.load(os.path.join(directory,'globe_mask.npz'))
    mask_globe = data['mask'].copy()
    lat_globe = data['lat']
    lon_globe = data['lon']

    mask_globe = mask_globe.astype('uint8')

    # Identify locations that can be easily classified as land or sea,
    # i.e., those that are not on the coast
    # note: the morphological gradient is the difference between dilation and erosion of an image

    kernel = np.ones((51, 51), np.uint8) # square kernel
    # note: for an elliptical kernel, use kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(25,25))
    gradient_mask_globe = cv2.morphologyEx(mask_globe, cv2.MORPH_GRADIENT, kernel)

    # Create the final mask distinguishing land, sea, and coast

    full_mask_globe = np.maximum(gradient_mask_globe*2, mask_globe)
    np.savez_compressed(os.path.join(directory,'globe_mask_coastline.npz'), lat=lat_globe, lon=lon_globe, mask=full_mask_globe)
