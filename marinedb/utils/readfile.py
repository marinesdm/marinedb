
# Local import

from marinedb.utils import isgzip

def apply(filepath):

    if isgzip.apply(filepath):
        open_file = gzip.open
        decode_line = lambda line: line.decode('utf8')
    else:
        open_file = open
        decode_line = lambda line: line

    return open_file, decode_line

