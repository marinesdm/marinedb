import numpy as np
import cv2

# Load the GLOBE mask
data = np.load('globe_combined_mask_compressed.npz')
mask_globe = data['mask'].copy()
lat_globe = data['lat']
lon_globe = data['lon']

mask_globe = mask_globe.astype('uint8')

# Identify locations that can be easily classified as land/sea, i.e. not on the coast.
# Morphological gradient = difference between dilation and erosion of an image
kernel = np.ones((51, 51), np.uint8) #square
#kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(25,25)) #ellipse
gradient_mask_globe = cv2.morphologyEx(mask_globe, cv2.MORPH_GRADIENT, kernel)
full_mask_globe = np.maximum(gradient_mask_globe*2, mask_globe)

np.savez_compressed('globe_mask_coastline.npz', lat=lat_globe, lon=lon_globe, mask=full_mask_globe)