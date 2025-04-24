#!/usr/bin/python
# coding: utf-8

# Internal import

from marinedb.utils.allexport import export

# Global variable

__all__ = [] # populated using the @export decorator

@export
def apply(df, key, modulename, inplace, minimize_columns=True):

    """
    Parameters
    ----------
    minimize_columns : bool
        If True, minimizes the number of generated columns by modifying derived columns inplace
        If False, a new column may be created for each processing step (i.e., when inplace=False),
        allowing fine-grained tracking of the data curation process
    """

    ismodulename = (len(modulename) != 0)

    if (not ismodulename) and (not inplace):
        raise Exception(f"`getcolumnname.py` | inplace={inplace} but modulename='{modulename}'. Assign a value to `modulename` or set `inplace` to True.")

    # Check if `basekey` has been previously processed and not modified in place,
    # as indicated by the naming pattern '{basekey}_processedby_...'

    basekey = key.split('_processedby_')[0]
    pattern = f'{basekey}_processedby'
    processedkey = [col for col in df.columns if (col[:len(pattern)] == pattern)]

    if len(processedkey) > 1:
        processedkey = sorted(processedkey, key=len)
        if minimize_columns:
            raise Exception(f"`getcolumnname.py` | Multiple derived columns found for '{basekey}': {processedkey}.  An issue may have occurred during execution.")
        else:
            for col in processedkey:
                coldiff = set(col) - set(processedkey[-1])
                if (len(coldiff) != 0):
                    # unexpected
                    raise Exception(f"`getcolumnname.py` | Multiple independently processed columns found for '{basekey}': {processedkey}. An issue may have occurred during execution.")
            processedkey = processedkey[-1:]

    if len(processedkey) == 1:

        # Previously processed

        inputkey = processedkey[0]
        isprocessed = True
        isgenerated = False

        if minimize_columns:
            # To prevent the proliferation of columns resulting from
            # inplace=False settings in various processing steps, stop
            # generating new columns after the first derived column is created
            inplace = True

    else:

        # Either:
        # - unprocessed,
        # - modified in place with the column name left unchanged
        # - or newly created

        inputkey = basekey
        isprocessed = False
        isgenerated = (inputkey not in df.columns)

    outputkey = inputkey
    if ismodulename:

        # Maintain a record of curation process

        if isprocessed:
            if modulename in inputkey:
                raise Exception(f"`getcolumnname.py` | '{basekey}' has already been processed by `{modulename}`: '{inputkey}'")
            else:
                outputkey += f'_{modulename}'
        else:
            if isgenerated:
                outputkey += f'_generatedby_{modulename}'
                inputkey = outputkey
            else:
                outputkey += f'_processedby_{modulename}'

    if inplace and (outputkey != inputkey):

        # Overwrite the original column

        df.rename(columns={inputkey:outputkey}, inplace=True)
        inputkey = outputkey

    return df, inputkey, outputkey
