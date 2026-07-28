#!/usr/bin/python
# coding: utf-8

# External import

import os
import json
import shutil
import psutil
import subprocess
import pandas as pd
import dask.dataframe as dd
from collections import deque
from importlib.resources import files

# Internal import

from marinedb.utils import resolvepath
from marinedb.utils import convertbytes
from marinedb.utils.allexport import export
from marinedb.utils.printverbose import printv
from marinedb.utils import getdefaultoutputfile

from marinedb.tools import getcolumnname
from marinedb.tools.taxonomic import taxasubset_lowerbound
from marinedb.tools.taxonomic import taxasubset_upperbound

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(inputfile, sep='\t', lowerbound=-1, upperbound=-1, flag=False, dropna=False, force_distributed=False, speciesidkey=None, specieskey=None, genuskey=None, familykey=None, orderkey=None, classkey=None, phylumkey=None, kingdomkey=None, latkey=None, lonkey=None, resolution=8, cleanup=False, dtypesfile=None, outputdir='./', outputfile=None, export_process=False, export_type='both', verbose=True, verbose_level=2, indent=''):
    """Filter underrepresented taxa and spatially subsample overrepresented taxa.

    Controls species representation using optional lower and upper occurrence
    thresholds. The two operations can be applied independently or together:

    - `lowerbound` flags sufficiently represented taxa or excludes taxa with
    fewer occurrences than the specified minimum.
    - `upperbound` spatially subsamples taxa exceeding the specified maximum
    while promoting broad and spatially dispersed geographic coverage.

    When both thresholds are enabled, the lower-bound operation is performed
    first and its output is passed to the upper-bound operation. When neither
    threshold is greater than zero, no processing is performed and `inputfile`
    is returned unchanged.

    Taxa are evaluated using a species identifier. This identifier may be
    supplied through `speciesidkey` or constructed from the available
    taxonomic classification columns when no identifier is provided.

    !!! warning

        The following behavior applies to the lower-bound operation:

        - When `flag=True`, records belonging to taxa represented by at least
        `lowerbound` occurrences are flagged.

        - When `flag=False`, records belonging to taxa represented by fewer
        than `lowerbound` occurrences are excluded.

    !!! warning

        Upper-bound processing assumes that species identifiers and
        geographic coordinates have already been cleaned. It should be
        applied only to datasets without missing or invalid values in the
        identifier, latitude, and longitude columns.

    Args:
        inputfile (str):
            Path to the input tabular file.

        sep (str, optional):
            Field delimiter used in the input and output files. 

        speciesidkey (str, optional):
            Name of the column containing the species identifier used to
            group records and count occurrences. When omitted, species
            identifiers are constructed from the available taxonomic
            classification columns.

            When `taxasubset` is used after `isinworms` in the integrated
            workflow, this argument is supplied automatically and corresponds
            to the WoRMS `AphiaID`. 

        specieskey (str, optional):
            Name of the species column used, together with the available
            higher-rank columns, to construct species identifiers when
            `speciesidkey` is not provided. 

        genuskey (str, optional):
            Name of the genus column used to construct species identifiers
            when needed. 

        familykey (str, optional):
            Name of the family column used to construct species identifiers
            when needed.

        orderkey (str, optional):
            Name of the order column used to construct species identifiers
            when needed. 

        classkey (str, optional):
            Name of the class column used to construct species identifiers
            when needed. 

        phylumkey (str, optional):
            Name of the phylum column used to construct species identifiers
            when needed. 

        kingdomkey (str, optional):
            Name of the kingdom column used to construct species identifiers
            when needed.

        lowerbound (int, optional):
            Minimum number of occurrences required for a taxon to satisfy the
            lower-bound criterion. Taxa represented by fewer records are
            considered underrepresented. Set to a value greater than zero to
            enable lower-bound processing. 

        flag (bool, optional):
            **Used only when** `lowerbound > 0`. Whether to add a Boolean flag 
            instead of excluding underrepresented taxa. When `True`, all 
            records are retained and `flag_taxasubset_isabove_<lowerbound>` 
            is `True` for records belonging to taxa represented by at least 
            `lowerbound` occurrences, `False` for underrepresented taxa, and 
            missing when the species identifier is missing.  

        dropna (bool, optional):
            **Used only when** `lowerbound > 0`. Whether to also exclude records 
            with a missing species identifier when `flag=False`. Missing 
            identifiers are retained when `False`. This parameter has no effect 
            when `flag=True`. 

        force_distributed (bool, optional):
            **Used only when** `lowerbound > 0`. Whether to use distributed 
            processing regardless of the available memory. 

        upperbound (int, optional):
            Maximum number of records to retain per taxon. Taxa represented
            by at least `upperbound` records are spatially subsampled, whereas 
            taxa below the threshold are retained unchanged. Set to a value 
            greater than zero to enable upper-bound processing. 

        latkey (str, optional):
            **Required when** `upperbound > 0`. Name of the column containing 
            decimal latitude values.

        lonkey (str, optional):
            **Required when** `upperbound > 0`. Name of the column containing 
            decimal longitude values. 

        resolution (int, optional):
            **Used only when** `upperbound > 0`. Maximum H3 resolution used to 
            discretize occurrence locations during upper-bound processing. 
            Sampling begins at resolution `0` and progresses toward this 
            maximum as additional discrete locations are needed. Valid 
            values range from `0` to `15`.

            The default resolution of `8` corresponds to cells of
            approximately 0.74 km², with a maximum within-cell distance of
            approximately 1.06 km.

        cleanup (bool, optional):
            **Used only when** `upperbound > 0`. Whether to remove the input file 
            after successful processing when its name differs from the resulting 
            output file.

        export_process (bool, optional):
            **Used only when** `upperbound > 0`. Whether to export a visualization 
            of each discrete-location selection step for every taxon submitted 
            to spatial subsampling. Exports are written under `sampling/location` 
            within the output directory unless that directory already contains a 
            `sampling` component.  

        export_type ({"gif", "image", "both"}, optional):
            **Used only when** `upperbound > 0` and `export_process=True`. Format 
            used to export the location-selection process. 

            - `"image"` retains one image for each sampling step
            - `"gif"` combines the images into an animation and removes the 
            individual images
            - `"both"` retains both outputs

        dtypesfile (str, optional):
            Path to a JSON file defining column data types. During
            lower-bound processing, the Boolean type of a generated flag
            column is added to this file. 

        outputdir (str, optional):
            Directory in which to write the processed dataset and any
            requested sampling visualizations. 

        outputfile (str, optional):
            Path or name of the output file. When omitted, empty, or identical
            to `inputfile`, a default filename is generated using the
            `taxasubset` processing suffix. 

    Returns:
        (str):
            Path to the final processed file. When neither threshold is
            enabled, or when upper-bound processing is aborted because of
            insufficient memory, the relevant input file is returned
            unchanged.

    Raises:
        ValueError:
            If `latkey` or `lonkey` is omitted when `upperbound > 0`.
        ValueError:
            If `export_type` is invalid when process visualization is enabled.
        ValueError:
            If `resolution` is outside the supported H3 range from `0`
            to `15`.
        Exception:
            If distributed lower-bound processing is required but the output
            directory does not provide enough free disk space.

    !!! Notes

        **Processing modes**:

        The lower-bound operation can use either in-memory or distributed
        processing. The upper-bound operation is not currently distributed
        and requires the full input dataset to fit in memory. When
        insufficient memory is available, upper-bound processing is aborted
        and the intermediate input file is left unchanged.

        **Upper-bound processing**:

        For overrepresented taxa, occurrence locations are discretized using
        the H3 hierarchical hexagonal grid. Discrete locations are selected
        from coarse to fine resolutions, with selection probabilities
        proportional to cell area and neighboring cells temporarily excluded
        to reduce spatial clustering.

        Records are then sampled as evenly as possible across the selected
        cells, subject to local data availability. The procedure normally
        retains exactly `upperbound` records for each subsampled taxon. In
        exceptional cases involving H3 grid-edge effects, fewer records may
        be retained.

        Sampling within cells is random and no fixed random seed is currently
        exposed. Upper-bound results are therefore not guaranteed to be
        reproducible across runs.
    """

    if (upperbound <= 0) and (lowerbound <= 0):

        # Do not filter taxa based on their number of occurrences in the dataset

        outputfile = inputfile

        return outputfile

    outputdir = resolvepath.apply(outputdir)
    if (outputfile is None) or (len(outputfile) == 0) or (inputfile == outputfile):
        outputfile = getdefaultoutputfile.apply(inputfile, 'taxasubset', outputdir=outputdir, verbose=verbose, indent=indent)

    current_inputfile = inputfile

    if lowerbound > 0:

        # Filter taxa with less than `lowerbound` occurrences in the dataset

        printv('* lowerbound', verbose=verbose, indent=indent)

        params = {
                  'inputfile': current_inputfile,
                  'sep': sep,
                  'limit': lowerbound,
                  'flag': flag,
                  'dropna': dropna,
                  'force_distributed': force_distributed,
                  'speciesidkey': speciesidkey,
                  'specieskey': specieskey,
                  'genuskey': genuskey,
                  'familykey': familykey,
                  'orderkey': orderkey,
                  'classkey': classkey,
                  'phylumkey': phylumkey,
                  'kingdomkey': kingdomkey,
                  'dtypesfile': dtypesfile,
                  'outputdir': outputdir,
                  'outputfile': outputfile,
                  'verbose': verbose,
                  'indent': indent + '  '
                 }

        outputfile, speciesidkey = taxasubset_lowerbound.apply(**params)
        printv('', verbose=verbose, indent=indent)

        current_inputfile  = outputfile

    if upperbound > 0:

        # Limit the number of observations per taxon to `upperbound`

        printv('* upperbound', verbose=verbose, indent=indent)
        printv('', verbose=verbose, indent=indent)

        if latkey is None:
            raise ValueError(f'`taxasubset.py` | `latkey` must be provided')
        if lonkey is None:
            raise ValueError(f'`taxasubset.py` | `lonkey` must be provided')

        params = {
                   'sep': sep,
                   'limit': upperbound,
                   'latkey': latkey,
                   'lonkey': lonkey,
                   'speciesidkey':speciesidkey,
                   'specieskey':specieskey,
                   'genuskey':genuskey,
                   'familykey':familykey,
                   'orderkey':orderkey,
                   'classkey':classkey,
                   'phylumkey':phylumkey,
                   'kingdomkey':kingdomkey,
                   'resolution': resolution,
                   'cleanup': cleanup,
                   'dtypesfile': dtypesfile,
                   'outputdir': outputdir,
                   'outputfile': outputfile,
                   'export_process': export_process,
                   'export_type': export_type,
                   'verbose': verbose,
                   'verbose_level': verbose_level,
                   'indent': indent + '  '
                 }

        outputfile = taxasubset_upperbound.apply(current_inputfile, **params)
        printv('', verbose=verbose, indent=indent)

    return outputfile

