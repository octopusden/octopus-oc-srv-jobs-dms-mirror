#!/usr/bin/env python3

import unittest
from . import test_dms_mirror

def dms_mirror_test_suite():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(test_dms_mirror)
    return suite

