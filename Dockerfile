ARG PYTHON_VERSION=3.7
FROM python:${PYTHON_VERSION}

USER root
RUN rm -rf /build
COPY --chown=root:root . /build
WORKDIR /build
RUN python -m pip install $(pwd) && python -m unittest discover -v && python setup.py bdist_wheel

ENTRYPOINT ["python", "-m", "oc_dms_mirror"]
