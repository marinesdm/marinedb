#!/usr/bin/python
# coding: utf-8

# External import

import os
import glob
import geodatasets
import antimeridian
import pandas as pd
from PIL import Image
import geopandas as gpd
from pathlib import Path
import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import cartopy.feature as cfeature
from matplotlib.patches import Patch, Rectangle

# Internal import

from marinedb.utils.printverbose import printv

# Visual settings

STATUS_COLORS = {
    0: "#9ACD91",  # available
    1: "#595959",  # sampled previously
    2: "#BDBDBD",  # adjacent previously
    3: "#E6550D",  # sampled currently
    4: "#FDBE85",  # adjacent currently
}

STATUS_LABELS = {
    0: "available",
    1: "sampled (previous)",
    2: "adjacent (previous)",
    3: "sampled (current)",
    4: "adjacent (current)",
}

# Geometry cache

class H3GeometryCache:
    """
    Cache H3 geometries after antimeridian correction and reprojection.
    """

    def __init__(self, target_crs: str = "EPSG:8857", backend: str = "geopandas") -> None:
        self.target_crs = target_crs
        self.backend = backend
        self._cache: dict[str, object] = {}

    def __len__(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        """Remove every cached geometry."""
        self._cache.clear()

    def _compute_missing_geometries(self, cell_ids: list[str]) -> None:
        """
        Compute and cache geometries that are not already available.
        """

        missing_cells = [cell_id for cell_id in cell_ids if cell_id not in self._cache]

        if not missing_cells:
            return

        cells_df = pd.DataFrame(index=pd.Index(missing_cells,name="cell"))

        missing_gdf = cells_df.h3.h3_to_geo_boundary()

        if missing_gdf.crs is None:
            missing_gdf = missing_gdf.set_crs("EPSG:4326")

        # H3 boundaries are initially polygons.
        # Cells crossing ±180° may become multipolygons after correction.
        missing_gdf["geometry"] = missing_gdf.geometry.apply(antimeridian.fix_polygon)

        if self.backend == "geopandas":
            missing_gdf = missing_gdf.to_crs(self.target_crs)

        for cell_id, geometry in zip(missing_gdf.index.astype(str), missing_gdf.geometry):
            self._cache[cell_id] = geometry

    def get_geodataframe(self, cell_ids, cell_column: str = "cell", explode: bool = True) -> gpd.GeoDataFrame:
        """
        Return projected geometries for the requested H3 cells.

        Parameters
        ----------
        cell_ids
            Iterable of H3 cell identifiers.
        cell_column
            Name of the output column containing H3 identifiers.
        explode
            If True, convert multipolygons into separate polygon rows. This
            simplifies color assignment for cells crossing the antimeridian.

        Returns
        -------
        geopandas.GeoDataFrame
            Projected geometries. A cell may occur on several rows when an
            antimeridian-crossing multipolygon is exploded.
        """

        unique_cells = (
            pd.Series(cell_ids, dtype="object")
            .astype(str)
            .drop_duplicates()
            .sort_values()
            .tolist()
        )

        self._compute_missing_geometries(unique_cells)

        gdf = gpd.GeoDataFrame({
                                cell_column: unique_cells,
                                "geometry": [self._cache[cell_id] for cell_id in unique_cells]
                               },
                               geometry="geometry",
                               crs=self.target_crs)

        if explode:
            gdf = gdf.explode(index_parts=False).reset_index(drop=True)

        return gdf

# Cell-status calculation

def build_cell_status(cell_ids, previous_sampled_cells, previous_adjacent_cells, sampled_cells, adjacent_cells) -> pd.Series:
    """
    Assign one status code to every H3 cell.

    Status priority
    ---------------
    1. Currently sampled
    2. Currently adjacent
    3. Previously sampled
    4. Previously adjacent
    5. Available for sampling
    """

    cells = (
        pd.Series(cell_ids, dtype="object")
        .astype(str)
        .drop_duplicates()
    )

    adjacent_cells = set(adjacent_cells - previous_adjacent_cells - sampled_cells)
    previous_adjacent_cells = set(previous_adjacent_cells - previous_sampled_cells)
    sampled_cells = set(sampled_cells - previous_sampled_cells)

    # The index contains the H3 identifiers so that status values can later
    # be mapped directly onto exploded polygon parts.
    status = pd.Series(0, index=cells, dtype="int8", name="status")

    status.loc[status.index.isin(previous_sampled_cells)] = 1
    status.loc[status.index.isin(previous_adjacent_cells)] = 2
    status.loc[status.index.isin(sampled_cells)] = 3
    status.loc[status.index.isin(adjacent_cells)] = 4

    return status

# Reusable map renderer

# Cartopy

class H3SamplingMapCartopy:

    def __init__(
        self,
        geometry_cache: H3GeometryCache | None = None,
        export_type: str = "image",
        cell_column: str = "cell",
        palette: dict[int, str] | None = None,
        show_coastlines: bool = True,
        show_legend: bool = True,
        verbose=True,
        indent=''
    ) -> None:

        if geometry_cache is None:
            print("debug")
            self.geometry_cache = H3GeometryCache(backend="cartopy")
        else:
            self.geometry_cache = geometry_cache

        self.cell_column = cell_column
        if palette is None:
            self.palette = STATUS_COLORS.copy()
        else:
            self.palette =  palette.copy()

        self.export_type = export_type
        if export_type == "gif":
            figsize = (10, 8)
            self.dpi = 80
            fontsize = 10
        else:
            figsize = (12, 10)
            self.dpi = 150
            fontsize = 11

        self.verbose = verbose
        self.indent = indent

        self.projection = ccrs.EqualEarth()

        self.fig = plt.figure(figsize=figsize, constrained_layout=True)

        self.ax = self.fig.add_subplot(1,1,1,projection=self.projection)

        figure_background_color = "#F5F5F5"
        ocean_color = "#C7E1EF"
        land_color = "#F2ECD9"

        self.fig.patch.set_facecolor(figure_background_color)

        self.ax.set_global()
        self.ax.set_xticks([])
        self.ax.set_yticks([])

        self.ax.xaxis.set_visible(False)
        self.ax.yaxis.set_visible(False)

        self.ax.add_feature(
            cfeature.OCEAN,
            facecolor=ocean_color,
            edgecolor="none",
            zorder=0,
        )
        self.ax.add_feature(
            cfeature.LAND,
            facecolor=land_color,
            edgecolor="none",
            linewidth=0.4,
            zorder=1,
        )

        if show_coastlines:
            self.ax.coastlines(
                linewidth=0.3,
                color="#A0A0A0",
                zorder=2,
            )

        self.ax.spines["geo"].set_visible(False)

        frame = Rectangle(
            (0, 0),
            1,
            1,
            transform=self.ax.transAxes,
            fill=False,
            edgecolor="black",
            linewidth=1.0,
            zorder=20,
            clip_on=False,
        )

        self.ax.add_patch(frame)

        self.title_artist = self.ax.set_title("", fontsize=fontsize + 1, pad=10, fontweight="normal")

        if show_legend:
            legend_handles = [
                Patch(
                    facecolor=self.palette[status],
                    edgecolor="white",
                    linewidth=0.5,
                    label=STATUS_LABELS[status],
                )
                for status in range(5)
            ]

            self.ax.legend(
                handles=legend_handles,
                title="CELL STATUS",
                loc="lower left",
                frameon=False,
                fontsize=(fontsize - 1),
                title_fontsize=fontsize,
            )

        self.cell_artists = []

    def update(
        self,
        cell_ids,
        previous_sampled_cells,
        previous_adjacent_cells,
        sampled_cells,
        adjacent_cells,
        species: str,
        resolution: int,
        step: int
    ) -> None:
        """
        Update the displayed cells, their colors and the map title.
        """

        for artist in self.cell_artists:
            artist.remove()
        self.cell_artists = []

        status_by_cell = build_cell_status(
            cell_ids=cell_ids,
            previous_sampled_cells=previous_sampled_cells,
            previous_adjacent_cells=previous_adjacent_cells,
            sampled_cells=sampled_cells,
            adjacent_cells=adjacent_cells,
        )

        cells_gdf = self.geometry_cache.get_geodataframe(
            cell_ids=status_by_cell.index,
            cell_column=self.cell_column,
            explode=True,
        )

        cells_gdf["status"] = (
            cells_gdf[self.cell_column]
            .map(status_by_cell)
            .astype("int8")
        )

        for status_code in sorted(self.palette):
            subset = cells_gdf.loc[
                cells_gdf["status"].eq(status_code)
            ]

            if subset.empty:
                continue

            artist = self.ax.add_geometries(
                subset.geometry,
                crs=ccrs.PlateCarree(),
                facecolor=self.palette[status_code],
                edgecolor="white",
                linewidth=0.6,
                alpha=0.65,
                zorder=3,
            )
            self.cell_artists.append(artist)

        title = f"SPECIES: {species} - RES: {resolution:02} - STEP: {step:02}"
        self.title_artist.set_text(title)

    def save(self, species: str, step: int, resolution: int, outputdir: str) -> None:
        """Save the current map state."""

        Path(outputdir).parent.mkdir(parents=True, exist_ok=True)

        outputfile = os.path.join(outputdir, f'{species}_RES{resolution:02}_STEP{step:02}.png')
        if self.export_type != 'gif':
            printv(f'INFO | save to {outputfile}', verbose=self.verbose, indent=self.indent)

        self.fig.savefig(
            outputfile,
            dpi=self.dpi,
            bbox_inches="tight",
            facecolor="white",
        )

    def close(self) -> None:
        """Close the Matplotlib figure."""
        plt.close(self.fig)

# GeoPandas

class H3SamplingMapGeoPandas:
    """
    Reusable GeoPandas/Matplotlib map for successive H3 sampling states.

    Geometries are retrieved from H3GeometryCache. The Matplotlib polygon
    collection is reused when the displayed cells remain unchanged and is
    rebuilt only when cells or resolution change.
    """

    def __init__(
        self,
        geometry_cache: H3GeometryCache | None = None,
        export_type: str = "image",
        cell_column: str = "cell",
        palette: dict[int, str] | None = None,
        show_legend: bool = True,
        show_coastlines: bool = True,
        verbose=True,
        indent=''
    ) -> None:

        if geometry_cache is None:
            self.geometry_cache = H3GeometryCache(backend="geopandas")
        else:
            self.geometry_cache = geometry_cache

        self.cell_column = cell_column
        if palette is None:
            self.palette = STATUS_COLORS.copy()
        else:
            self.palette =  palette.copy()

        self.export_type = export_type
        if export_type == "gif":
            figsize = (10, 8)
            self.dpi = 80
            fontsize = 10
        else:
            figsize = (12, 10)
            self.dpi = 150
            fontsize = 11

        self.verbose = verbose
        self.indent = indent

        self.fig, self.ax = plt.subplots(figsize=figsize, constrained_layout=True)

        figure_background_color = "#F5F5F5"
        ocean_color = "#F5F5F5" #"#C7E1EF" #"#B9DDF2" # "#FFFFFF"
        land_color = "#EFE8D2" # "#E8E8E8"

        self.fig.patch.set_facecolor(figure_background_color)
        self.ax.set_facecolor(ocean_color)

        # Equal Earth world background

        self.world = gpd.read_file(geodatasets.get_path("naturalearth.land")).to_crs(self.geometry_cache.target_crs)

        self.world.plot(
            ax=self.ax,
            color=land_color,
            edgecolor="none",
            linewidth=0,
            zorder=1,
        )

        if show_coastlines:
            self.world.boundary.plot(
                ax=self.ax,
                color="#333333",
                linewidth=0.1,
                zorder=2,
            )

        bounds = self.world.total_bounds

        self.ax.set_xlim(bounds[0], bounds[2])
        self.ax.set_ylim(bounds[1], bounds[3])
#        self.ax.set_axis_off()
        self.ax.set_xticks([])
        self.ax.set_yticks([])

        for spine in self.ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(1.0)
            spine.set_edgecolor("black")

        self.title_artist = self.ax.set_title("", fontsize=fontsize + 1, pad=10, fontweight="normal")

        if show_legend:
            legend_handles = [
                Patch(
                    facecolor=self.palette[status],
                    edgecolor="white",
                    linewidth=0.5,
                    label=STATUS_LABELS[status],
                )
                for status in range(5)
            ]

            self.ax.legend(
                handles=legend_handles,
                title="CELL STATUS",
                loc="lower left",
                frameon=False,
                fontsize=(fontsize - 1),
                title_fontsize=fontsize,
            )

        # Current Matplotlib collection and its geometry order.
        self.cell_collection = None
        self.current_polygon_cells: tuple[str, ...] | None = None

    def update(
        self,
        cell_ids,
        previous_sampled_cells,
        previous_adjacent_cells,
        sampled_cells,
        adjacent_cells,
        species: str,
        resolution: int,
        step: int
    ) -> None:
        """
        Update the displayed cells, their colors and the map title.
        """

        status_by_cell = build_cell_status(
            cell_ids=cell_ids,
            previous_sampled_cells=previous_sampled_cells,
            previous_adjacent_cells=previous_adjacent_cells,
            sampled_cells=sampled_cells,
            adjacent_cells=adjacent_cells,
        )

        cells_gdf = self.geometry_cache.get_geodataframe(
            cell_ids=status_by_cell.index,
            cell_column=self.cell_column,
            explode=True,
        )

        cells_gdf["status"] = (
            cells_gdf[self.cell_column]
            .map(status_by_cell)
            .astype("int8")
        )

        facecolors = (
            cells_gdf["status"]
            .map(self.palette)
            .tolist()
        )

        # This tuple includes repeated identifiers when an antimeridian cell
        # has been exploded into several polygon parts.
        polygon_cells = tuple(cells_gdf[self.cell_column].astype(str))

        same_geometries = (
            self.cell_collection is not None
            and self.current_polygon_cells == polygon_cells
        )

        if same_geometries:
            # Only status colors changed.
            self.cell_collection.set_facecolor(facecolors)

        else:
            # Cells or resolution changed: remove the old collection and
            # create a new one using cached projected geometries.
            if self.cell_collection is not None:
                self.cell_collection.remove()

            cells_gdf.plot(
                ax=self.ax,
                color=facecolors,
                edgecolor="white",
                linewidth=0.6,
                alpha=0.65,
                zorder=3,
            )

            self.cell_collection = self.ax.collections[-1]
            self.current_polygon_cells = polygon_cells

        title = f"SPECIES: {species} - RES: {resolution:02} - STEP: {step:02}"
        self.title_artist.set_text(title)

    def save(self, species: str, step: int, resolution: int, outputdir: str) -> None:
        """Save the current map state."""

        Path(outputdir).parent.mkdir(parents=True, exist_ok=True)

        outputfile = os.path.join(outputdir, f'{species}_RES{resolution:02}_STEP{step:02}.png')
        if self.export_type != 'gif':
            printv(f'INFO | save to {outputfile}', verbose=self.verbose, indent=self.indent)

        self.fig.savefig(
            outputfile,
            dpi=self.dpi,
            bbox_inches="tight",
            facecolor="white",
        )

    def close(self) -> None:
        """Close the Matplotlib figure."""
        plt.close(self.fig)

def create_gif_H3_sampling(outputdir, species, export_type='gif', duration=2000, verbose=True, indent=''):

    Image.MAX_IMAGE_PIXELS = None

    image_paths = sorted(glob.glob(os.path.join(outputdir,f'{species}_RES*')))

    try:
        frames = []
        for image_path in image_paths:
            with Image.open(image_path) as image:
                frames.append(image.copy())

        reference_size = frames[0].size
        if any(frame.size != reference_size for frame in frames):
            frames = [
                      frame.resize(reference_size, resample=Image.Resampling.LANCZOS)
                      for frame in frames
            ]

        gif_path = os.path.join(outputdir, f'{species}_H3_sampling.gif')
        printv(f'INFO | save to {gif_path}', verbose=verbose, indent=indent)
        frames[0].save(gif_path, format="GIF", append_images=frames[1:], save_all=True, duration=duration, loop=0, disposal=2)

    finally:
        for frame in frames:
            frame.close()

    if (export_type == 'gif'):
        for image in image_paths:
            os.remove(image)

    return gif_path

# Basemap

def plot_h3grid_sampling(df, latkey, lonkey, speciesidkey, sampled_cells, adjacent_cells, previous_sampled_cells, previous_adjacent_cells, species, resolution, step, init, export_type='image', outputdir='./', verbose=True, indent=''):

    import shapely
    import antimeridian
    import geodatasets
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from descartes import PolygonPatch
    from matplotlib.patches import Patch
    from mpl_toolkits.basemap import Basemap
    from matplotlib.collections import PatchCollection
    from matplotlib.colors import ListedColormap

    if resolution > 1: # debug
        for filename in glob.glob(f'*{species}*'):
            os.remove(filename) # data_paper
        return None

    global projected_geom_cache
    try:
        projected_geom_cache
    except NameError:
        projected_geom_cache = {}

    cmap = ListedColormap(['seagreen', 'black', 'grey', 'salmon', 'orange'])
    labels = ['available', 'sampled (previous)', 'adjacent (previous)', 'sampled (current)', 'adjacent (current)']
    if export_type == 'gif':
        dpi = 80
    else:
        dpi = 150

    if init:
        plt.close()

        global basemap
        global fig
        global ax

        water = 'lightskyblue'
        earth = 'cornsilk'

        if export_type == 'gif':
            figsize = (10, 8)
            fontsize = 10
        else:
            figsize = (12, 10)
            fontsize = 11
        fig, ax = plt.subplots(figsize=figsize)

        basemap = Basemap(
                          llcrnrlat = -80,
                          urcrnrlat = 80,
                          llcrnrlon = -180,
                          urcrnrlon = 180,
                          projection = 'merc',
                          resolution = 'i',
                          ellps = 'WGS84',
                          ax = ax
                         )

        basemap.drawcoastlines()
        basemap.drawcountries()
        basemap.drawmapboundary(fill_color=water)
        _ = basemap.fillcontinents(color=earth,lake_color=water)
        legend_elements = []
        for i in range(len(labels)):
            legend_elements.append(Patch(facecolor=cmap(i), edgecolor='white', label=labels[i]))
        ax.legend(handles=legend_elements, loc='lower right', title='CELL STATUS', fontsize=(fontsize - 1), title_fontsize=fontsize) # fontsize = 16

    df_plot = df[['cell', latkey, lonkey]].copy()
    df_plot = df_plot.groupby(['cell'])[[latkey, lonkey]].mean().reset_index()

    adjacent_cells = set(adjacent_cells - previous_adjacent_cells - sampled_cells)
    previous_adjacent_cells = set(previous_adjacent_cells - previous_sampled_cells)
    sampled_cells = set(sampled_cells - previous_sampled_cells)

    df_plot['set'] = 0
    df_plot.loc[df_plot['cell'].isin(previous_sampled_cells),'set'] = 1
    df_plot.loc[df_plot['cell'].isin(previous_adjacent_cells),'set'] = 2
    df_plot.loc[df_plot['cell'].isin(sampled_cells),'set'] = 3
    df_plot.loc[df_plot['cell'].isin(adjacent_cells),'set'] = 4

    df_plot = df_plot.set_index('cell').h3.h3_to_geo_boundary().reset_index()

    patches = []
    colors = []
    cells = df_plot['cell'].to_numpy()
    geoms = df_plot.geometry.to_list()
    sets  = df_plot['set'].to_numpy()

    for cell, polygon, set_id in zip(cells, geoms, sets):
        if cell not in projected_geom_cache:
            polygon = antimeridian.fix_polygon(polygon)
            projected_geom_cache[cell] = shapely.ops.transform(basemap, polygon)
        patches.append(PolygonPatch(projected_geom_cache[cell]))
        colors.append(cmap(set_id))

    p = PatchCollection(patches, alpha=0.8, edgecolor='white', linewidths=0.5, zorder=2, facecolors=colors)
    ax.add_collection(p)
    title = ax.set_title(f'SPECIES: {species} - RES: {resolution:02} - STEP: {step:02}')

    outputfile = os.path.join(outputdir, f'{species}_RES{resolution:02}_STEP{step:02}.png')
    if export_type != 'gif':
        printv(f'INFO | save to {outputfile}', verbose=verbose, indent=indent)
    plt.savefig(outputfile, dpi=dpi, bbox_inches='tight')

    p.remove()

    return None

