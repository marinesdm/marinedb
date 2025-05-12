import numpy as np
import matplotlib.pyplot as plt

if __name__=='__main__':

    mask = np.load('globe_mask_coastline.npz')
    mask = mask['mask']

    fig = plt.figure(figsize=(30,20))
    cmap = plt.cm.viridis
    plt.imshow(mask, vmin=0, vmax=2, cmap=cmap)
    plt.axis('off')
    plt.savefig('globe_mask_coastline', bbox_inches='tight',dpi=96)
