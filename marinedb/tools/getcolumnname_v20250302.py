
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

        if ismodulename:

            outputkey = inputkey + f'_{modulename}'

            if inplace:

                # Even when `inplace`=True, maintain a record of curation steps
                # if any previous processing was not performed in place
                # Note: to override this behavior, set `modulename` to an empty string

                df.rename(columns={inputkey:outputkey}, inplace=True)
                inputkey = outputkey

        else:

            outputkey = inputkey

    else:

        # Either not previously processed or modified in place

        if inplace:
            inputkey = key
            outputkey = key
        else:
            inputkey = key
            if ismodulename:
                outputkey = f'{key}_processedby_{modulename}'
            else:
                outputkey = inputkey

    return df, inputkey, outputkey
