#!/usr/bin/python
# coding: utf-8

# from: https://stackoverflow.com/questions/185936/how-to-delete-the-contents-of-a-folder

# External import

import os

# Global variable

__all__ = ['apply']

def apply(dirpath):

    for filename in os.listdir(dirpath):
        filepath = os.path.join(dirpath, filename)
        if os.path.isfile(filepath) or os.path.islink(filepath):
            os.remove(filepath)
        if os.path.isdir(filepath):
            os.rmdir(filepath)

    return None
