#!/usr/bin/env python3

from setuptools import setup

__version = "1.5.4"

setup(
    name="oc-dms-mirror",
    version=__version,
    description="Tool for mirroring DMS artifacts",
    long_description="Tool for mirroring DMS artifacts",
    long_description_content_type="text/plain",
    install_requires=[
        "oc-cdtapi >= 3.11.6",
        "oc-checksumsq >= 10.0.3"
    ],
    packages=["oc_dms_mirror"])

