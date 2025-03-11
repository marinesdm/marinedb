
def apply(df, key, modulename, inplace):

    ismodulename = (len(modulename) != 0)

    if (not ismodulename) and (not inplace):
        raise Exception(f"`getcolumnname.py` | inplace={inplace} but modulename='{modulename}'. Assign a value to `modulename` or set `inplace` to True.")

    # Check if `basekey` has been previously processed and not modified in place,
    # as indicated by the naming pattern '{basekey}_processedby_{modulename}_...'

    basekey = key.split('_processedby_')[0]
    processedkey = [col for col in df.columns if (f'{basekey}_processedby' in col)]

    if len(processedkey) > 1:
        processedkey = sorted(processedkey, key=len)
        for col in processedkey:
            coldiff = set(col) - set(processedkey[-1])
            if (len(coldiff) != 0):
                # unexpected
                raise Exception(f"`getcolumnname.py` | Multiple processed columns found for '{basekey}': {processedkey}. An issue may have occurred during execution.")
        processedkey = processedkey[-1:]

    if len(processedkey) == 1:
        # Previously processed and not modified in place
        inputkey = processedkey[0]
        isprocessed = True
        isgenerated = False

    else:
        # Either unprocessed, modified in place or newly created
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
            outputkey += f'_processedby_{modulename}'
            if isgenerated:
                inputkey = outputkey

    if inplace and (outputkey != inputkey):
        # If `inplace` is True, overwrite the original column
        df.rename(columns={inputkey:outputkey}, inplace=True)
        inputkey = outputkey

    return df, inputkey, outputkey
