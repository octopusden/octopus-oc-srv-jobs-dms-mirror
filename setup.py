#!/usr/bin/env python3

from setuptools import setup

__version = "3.1.2"

setup(
    name="oc-dms-mirror",
    version=__version,
    description="Tool for mirroring DMS artifacts",
    long_description="Tool for mirroring DMS artifacts",
    long_description_content_type="text/plain",
    install_requires=[
        "oc-cdtapi >= 3.29.1",
        "oc-checksumsq >= 10.0.3",
        "flask==2.2.5",
        "gunicorn==23.0.0",
        "oc_logging==1.1.7"
    ],
    packages=[
        "oc_dms_mirror",
        "oc_dms_mirror.rest_api",
        "oc_dms_mirror.rest_api.app"
        ])

