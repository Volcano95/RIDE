# Automatically generated by 'package.py' script.

VERSION = '0.32.1'
RELEASE = 'final'
TIMESTAMP = '20110127-183226'

def get_version(sep=' '):
    if RELEASE == 'final':
        return VERSION
    return VERSION + sep + RELEASE
