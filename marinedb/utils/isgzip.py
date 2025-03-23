
def apply(filepath):
    with open(filepath, 'rb') as test:
        return (test.read(2) == b'\x1f\x8b')
