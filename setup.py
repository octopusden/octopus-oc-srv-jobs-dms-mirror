#!/usr/bin/env python3

from setuptools import setup

__version = "2.4.0"

setup(
    name="oc-dms-mirror",
    version=__version,
    description="Tool for mirroring DMS artifacts",
    long_description="Tool for mirroring DMS artifacts",
    long_description_content_type="text/plain",
    install_requires=[
        "oc-cdtapi >= 3.11.6",
        "oc-checksumsq >= 10.0.3",
        "flask",
        "gunicorn",
        "oc_logging"
    ],
    packages=[
        "oc_dms_mirror",
        "oc_dms_mirror.rest_api",
        "oc_dms_mirror.rest_api.app"
        ])

