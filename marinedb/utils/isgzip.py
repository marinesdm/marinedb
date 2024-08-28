
def apply(filepath):
    with open(filepath, 'rb') as test:
        return test_f.read(2) == b'\x1f\x8b'
