#!/usr/bin/python
# coding: utf-8

# from https://stackoverflow.com/questions/24983493/tracking-progress-of-joblib-parallel-execution

# External import

import contextlib
import joblib
from tqdm import tqdm

# Global variable

__all__ = ['apply']

@contextlib.contextmanager
def apply(tqdm_object):

    """Context manager to patch joblib, enabling progress reporting in the provided tqdm progress bar"""

    class TqdmBatchCompletionCallback(joblib.parallel.BatchCompletionCallBack):
        def __call__(self, *args, **kwargs):
            tqdm_object.update(n=self.batch_size)
            return super().__call__(*args, **kwargs)

    old_batch_callback = joblib.parallel.BatchCompletionCallBack
    joblib.parallel.BatchCompletionCallBack = TqdmBatchCompletionCallback
    try:
        yield tqdm_object
    finally:
        joblib.parallel.BatchCompletionCallBack = old_batch_callback
        tqdm_object.close()
