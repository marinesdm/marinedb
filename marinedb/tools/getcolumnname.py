


def apply(df, key, modulename, inplace):

    ismodulename = (len(modulename) != 0)

    if (not ismodulename) and (not inplace):
        raise Exception(f'`getcolumnname.py` | inplace={inplace} but modulename={modulename}. Assign a value to `modulename` or set `inplace` to True.')

    # Check if `key` has been previously processed and not modified in place,
    # as indicated by the naming pattern '{key}_processedby_{modulename}_...'

    processedkey = [col for col in df.columns if (f'{key}_processedby' in col)]

    if len(processedkey) > 1:
        # unexpected
        raise Exception(f"`getcolumnname.py` | Multiple processed columns found for '{key}': {processedkey}. An issue may have occurred during execution.")

    if len(processedkey) == 1:
        # Previously processed and not modified in place
        inputkey = processedkey[0]
        isgenerated = False

    else:
        # Either unprocessed, modified in place or newly created
        inputkey = key
        isgenerated = (inputkey in df.columns)

    outputkey = inputkey
    if ismodulename:
        # Maintain a record of curation process
        if isgenerated:
            outputkey += f'_processedby_{modulename}'
        else:
            outputkey += f'_{modulename}'

    if inplace and (outputkey != inputkey):
        # If `inplace` is True, overwrite the original column
        df.rename(columns={inputkey:outputkey}, inplace=True)
        inputkey = outputkey

    return df, inputkey, outputkey
