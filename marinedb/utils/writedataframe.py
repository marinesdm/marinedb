
def to_txt(df, txt_filename, init=False, verbose=False, indent=''):

    if verbose:
        print(indent + f'Storing in {txt_filename} | {len(df)} observations')

    if init:
        df.to_csv(txt_filename, mode='w', index=False, header=True, sep='\t')
    else:
        df.to_csv(txt_filename, mode='a', index=False, header=False, sep='\t')

    return True

