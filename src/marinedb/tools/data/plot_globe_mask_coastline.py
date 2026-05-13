import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

if __name__=='__main__':

    black_and_white = True

    mask = np.load('globe_mask_coastline.npz')
    mask = mask['mask']

    if black_and_white:

        colors = [
            '#F5F3EE', # land
            '#CDD3D1', # sea
            '#B86A63'  # coast
        ]

        cmap = ListedColormap(colors)

        filename = 'globe_mask_coastline_gray'

    else:

        cmap = plt.cm.viridis

        filename = 'globe_mask_coastline_viridis'

    fig = plt.figure(figsize=(30,20))

    plt.imshow(mask, vmin=0, vmax=2, cmap=cmap)
    plt.axis('off')
    plt.savefig(filename, bbox_inches='tight',dpi=96)
