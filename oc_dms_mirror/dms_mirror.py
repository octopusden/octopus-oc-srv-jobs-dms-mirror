#!/usr/bin/env python3

import argparse
import logging
import os
import time
import json
import tempfile
import multiprocessing
import posixpath
import re

from oc_checksumsq.checksums_interface import ChecksumsQueueClient
from oc_checksumsq.checksums_interface import FileLocation
from string import Template

from oc_cdtapi import NexusAPI, DmsAPI

from oc_cdtapi.API import HttpAPIError
from requests.exceptions import ConnectionError

class DmsMirror:
    """
    A class for artifacts mirroring from Dms API
    """
    def __init__(self):
        """
        Basic initialization
        """
        self.__errors = (ConnectionError, HttpAPIError, KeyError)
        self._dms_client = None
        self._mvn_client = None
        self._queue_client = None
        self.__process_name = "?"

    def __log_msg(self, message):
        """
        Log a message for multiprocessing: append process name
        """
        return ': '.join([f"[{self.__process_name}]", message])

    @property
    def queue_client(self):
        if not self._queue_client:
            self._queue_client = self._get_queue_client()

        return self._queue_client

    @property
    def mvn_client(self):
        if not self._mvn_client:
            self._mvn_client = self._get_mvn_client()

        return self._mvn_client

    @property
    def dms_client(self):
        if not self._dms_client:
            self._dms_client = self._get_dms_client()

        return self._dms_client

    def _get_dms_client(self):
        """
        Return DmsAPI instance basing on version specified
        :return DmsAPI.DmsAPI:
        """

        if self._args.dms_api_version == 3:
            return DmsAPI.DmsAPIv3(root=self._args.dms_url,
                                   user=self._args.dms_user,
                                   auth=self._args.dms_password)


        if self._args.dms_crs_url:
            os.environ["DMS_CRS_URL"] = self._args.dms_crs_url

        if self._args.dms_token:
            os.environ["DMS_TOKEN"] = self._args.dms_token

        _dms_client = DmsAPI.DmsAPI(
                root=self._args.dms_url,
                user=self._args.dms_user,
                auth=self._args.dms_password)

        logging.debug(self.__log_msg(f"DMS_CRS_URL: [{_dms_client.crs_root}]"))
        # do not log headers since token may be displayed there!

        return _dms_client

    def _get_mvn_client(self):
        """
        Return NexusAPI instance
        """
        return NexusAPI.NexusAPI(root=self._args.mvn_url, user=self._args.mvn_user, auth=self._args.mvn_password,
                                 readonly=False, anonymous=False, upload_repo=self._args.mvn_upload_repo,
                                 download_repo=self._args.mvn_download_repo)

    def _get_queue_client(self):
        _q = ChecksumsQueueClient()
        _q.setup_from_args(self._args)
        _q.connect()
        _q.ping()
        _q.disconnect()
        return _q

    def process_component(self, component):
        """
        Process component
        To be called in separate process
        :param str component: DMS component ID
        :return: 'None' on success, raised exception on failure
        """
        self.__process_name = component

        if not self._components[component].get('enabled', True):
            logging.info(self.__log_msg(f"Skipping: [{component}]. Disabled in the configuration"))
            return None

        logging.info(self.__log_msg(f"Processing component {component} in separate thread"))

        if any(list(map(lambda x: self._components[component].get(x), ["componentId", "artifactType"]))):
            logging.warning(self.__log_msg(
                "'componentId' and 'artifactType' parameters are deprecated and may be safely removed"))

        try:
            versions = self._make_dms_api_call_with_retries(self.dms_client.get_versions, component) or list()
            logging.info(self.__log_msg(f"[{component}]: versions to process: [{len(versions)}]"))

            for version in versions:
                self.process_version(version, component)
        except Exception as _e:
            # this makes multiprocessing to stuck:
            # extending exception message to show the subprocess (i.e. component) where it has been raised
            # necessary to log all exceptions at the end
            # _e.args = (self.__log_msg(""), *_e.args)
            # DO NOT DO THAT!
            # the second bad idea is to return exception as a result in mulitprocessing stack
            # this makes stuck too unfortunately
            # transfer a human-readable string to log it at the end
            _error_message = self.__log_msg(repr(_e))
            logging.error(_error_message, exc_info=True)
            return _error_message

        return None

    def process_version(self, version, component):
        """
        Process versions of component
        :param str version: component version
        :param str component: DmsComponentID
        """
        artifacts = self._make_dms_api_call_with_retries(self.dms_client.get_artifacts, component, version) or list()
        logging.info(self.__log_msg(f"[{component}:{version}]: artifacts to process: [{len(artifacts)}]"))

        for artifact in artifacts:
            self.process_artifact(artifact, component, version)

    def _get_static_ci_type(self, artifact_type):
        """
        Return a type basing on dms_type
        :param str artifact_type: DMS artifact type
        :param dict params:
        :return str:
        """

        if artifact_type == "documentation":
            return self._args.ci_type_documentation

        if artifact_type in ["notes", "report"]:
            return self._args.ci_type_release_notes

        return None

    def _make_gav_substitute(self, component, version, artifact):
        """
        Return a dictionary for GAV substitutes
        :param str component:
        :param str version:
        :param dict artifact: artifact params from DMS
        :return dict:
        """
        _result = {
                "at": artifact["type"],
                "n": artifact.get("name") or "", # not returned by v3
                "v": version,
                "p": artifact.get("packaging") or "", # not returned by v3
                "c": artifact.get("classifier") or "", # not returned by v3
                "prefix": self._args.mvn_prefix}

        # try to update missing components using DMS API v3 detailed call
        if any(list(map(lambda _x: not _result.get(_x), ["n", "p"]))) and hasattr(self.dms_client, "get_artifact_info"):
            logging.log(5, self.__log_msg(
                "Try to update missing components using DMS API v3 detailed call"))

            # we have to raise an exception if "id" is not present - it is a crime!
            _info = self._make_dms_api_call_with_retries(self.dms_client.get_artifact_info, component, version, artifact["id"])
            _result.update({
                "n": _result.get("n") or _info.get("gav", dict()).get("artifactId") or "",
                "p": _result.get("p") or _info.get("gav", dict()).get("packaging") or "",
                "c": _result.get("c") or _info.get("gav", dict()).get("classifier") or ""})

        if any(list(map(lambda _x: not _result.get(_x), ["n", "p"]))):
            logging.log(5, self.__log_msg(
                f"Using DMS API v[{self._args.dms_api_version}], parsing filename [{artifact['fileName']}]."))
            _fn, _p = posixpath.splitext(artifact['fileName'])
            _p = _p.strip('.') or 'bin'
            _n = list(_fn.split(version))
            _c = ""

            if len(_n) > 1:
                _c = re.sub("^[\-_\.\s]+", "", _n.pop())
                _c = re.sub("[\-_\.\s]+$", "", _c)

            _n = re.sub("^[\-_\.\s]+", "", _n.pop(0))
            _n = re.sub("[\-_\.\s]+$", "", _n)
            _result.update({
                "n": _result.get("n") or _n,
                "p": _result.get("p") or _p,
                "c": _result.get("c") or _c})

        _result["cl"] = _result["c"]
        _result["c_hyphen"] = f"-{_result['c']}" if _result["c"] else ""
        _result["c_colon"] = f":{_result['c']}" if _result["c"] else ""
        logging.log(5, self.__log_msg(f"Returning subst: [{_result}]"))
        return _result

    def process_artifact(self, artifact, component, version):
        """
        Process artifacts
        :param dict artifact: artifact properties from Dms
        :param str version: component version
        :param str component: DmsComponentID
        :param dict params: configuration params
        """
        logging.log(5, self.__log_msg(f"Artifact: {artifact}"))

        # we need to raise an exception, so do not use 'get'
        # all these keys must exist
        _artifact_type = artifact['type']
        logging.info(self.__log_msg(
            f"Processing component:artifact_type:version = [{component}:{_artifact_type}:{version}]"))

        _params = self._components[component]
        logging.log(5, self.__log_msg(f"Params: {_params}"))
        _gav_template = _params.get("tgtGavTemplate")

        if _gav_template:
            _gav_template = _gav_template.get(_artifact_type)

        if not _gav_template:
            logging.warning(self.__log_msg(
                f"Component [{component}] has no GAV settings for artifact_type [{_artifact_type}], skipping"))
            return

        _gav_template = _gav_template.replace("\\", "")
        logging.debug(self.__log_msg(f"GAV template for [{component}:{_artifact_type}:{version}]: [{_gav_template}]"))
        _tgt_gav = Template(_gav_template).substitute(self._make_gav_substitute(component, version, artifact))
        _tgt_gav = re.sub('[^\w\-\.\:_]+', "_", _tgt_gav)
        logging.info(self.__log_msg(f"Target GAV: [{component}:{_artifact_type}:{version}] ==> [{_tgt_gav}]"))

        if self.mvn_client.exists(_tgt_gav, repo=self._args.mvn_download_repo):
            logging.info(self.__log_msg(
                f"Already exists, skipping: [{component}:{_artifact_type}:{version}] ==> [{_tgt_gav}]"))
            return

        _ci_type = self._get_static_ci_type(_artifact_type) or _params["ci_type"]
        logging.debug(self.__log_msg(f"ci_type: [{component}:{_artifact_type}:{version}] ==> [{_ci_type}]"))

        logging.info(self.__log_msg(f"Copying: [{component}:{_artifact_type}:{version}] ==> [{_tgt_gav}]"))
        self._copy_artifact(component, version, artifact, _tgt_gav)
        logging.info(self.__log_msg(f"Registering: [{_tgt_gav}] with ci_type [{_ci_type}]"))
        self._register_artifact(_tgt_gav, _ci_type)

    def _register_artifact(self, tgt_gav, ci_type):
        """
        Send a queue registration request
        :param str tgt_gav: target gav
        :param str ci_type: ci_type
        """
        self.queue_client.connect()
        _location = FileLocation(tgt_gav, "NXS", None)
        resp = self.queue_client.register_file(_location, ci_type, 0)
        logging.debug(self.__log_msg(f"Register response: [{resp}]"))
        self.queue_client.disconnect()

    def _copy_artifact(self, component, version, artifact, tgt_gav):
        """
        Make an artifact copy
        :param str component:
        :param str version:
        :param dict artifact: artifact properties from DMS
        :param str tgt_gav: target GAV
        """

        _tgt_file = tempfile.TemporaryFile(mode='w+b')
        if hasattr(self.dms_client, "download_component"):
            logging.info(self.__log_msg(f"Downloading component: [{component}:{version}:{artifact['type']}]"))
            self._make_dms_api_call_with_retries(self.dms_client.download_component, component, version, artifact["id"], write_to=_tgt_file)
        elif hasattr(self.dms_client, "get_gav"):
            logging.debug(self.__log_msg(f"Getting GAV from DMS: [{component}:{version}:{artifact['type']}]"))
            _src_gav = self._make_dms_api_call_with_retries(
                    self.dms_client.get_gav, component, version,
                    artifact["type"], artifact["name"], artifact["classifier"])
            logging.info(self.__log_msg(f"Downloading source GAV: [{_src_gav}]"))
            self.mvn_client.cat(_src_gav, repo=self._args.mvn_download_repo,
                                stream=True, binary=True, write_to=_tgt_file)

        _tgt_file.seek(0, os.SEEK_SET)
        logging.info(self.__log_msg(
            f"Putting to [{self._args.mvn_upload_repo}]: [{component}:{version}:{artifact['type']}] ==> [{tgt_gav}]"))
        self.mvn_client.upload(tgt_gav, repo=self._args.mvn_upload_repo, data=_tgt_file, pom=True)
        _tgt_file.close()
        logging.debug(self.__log_msg(f"Uploaded: [{component}:{version}:{artifact['type']}] ==> [{tgt_gav}]"))

    def _make_dms_api_call_with_retries(self, method, *args, **kwargs):
        """
        Make DMS API call with set amount of retries on error
        :param method: method reference
        :return: result of the method call
        """
        _attempt = 0
        while True:
            _attempt += 1
            if hasattr(method, '__name__'):
                _method_name = method.__name__
            elif hasattr(method, '__func__'):
                _method_name = method.__func__.__name__
            else:
                _method_name = 'Unknown method'
            logging.debug(self.__log_msg(f"{_method_name}: attempt [{_attempt}]"))
            try:
                return method(*args, **kwargs)
            except self.__errors as _err:
                if _attempt >= self._args.retries_count:
                    raise

                logging.debug(self.__log_msg(repr(_err)), exc_info=True)
                time.sleep(30)

    def prepare_parser(self):
        """
        Return basic parser object with correct description
        :return argparse.ArgumentParser:
        """
        return argparse.ArgumentParser(description="Mirror artifacts from DMS to MVN", conflict_handler='resolve')

    def basic_args(self, parser=None):
        """
        Fill the parser with arguments
        """
        if not parser:
            parser = self.prepare_parser()

        _q = ChecksumsQueueClient()
        _q.basic_args(parser)
        del _q

        parser.add_argument("--log-level", dest="log_level", type=int, default=20, help="Logging level")
        parser.add_argument("--config-file", dest="config_file", type=str, help="Path to configuration file",
                            default=os.path.join(os.getcwd(), "config.json"))
        parser.add_argument("--retries-count", dest="retries_count", type=int,
                            help='Retries count for DMS connection failures', default=5)

        # MVN arguments
        parser.add_argument("--mvn-prefix", dest="mvn_prefix", type=str, help="MVN GroupId prefix for destination",
                            default=os.getenv("MVN_PREFIX") or "com.example")
        parser.add_argument("--mvn-url", dest="mvn_url", help="MVN URL",
                            default=os.getenv("MVN_URL"))
        parser.add_argument("--mvn-user", dest="mvn_user", help="MVN user",
                            default=os.getenv("MVN_USER"))
        parser.add_argument("--mvn-password", dest="mvn_password", help="MVN password",
                            default=os.getenv("MVN_PASSWORD"))
        parser.add_argument("--mvn-upload-repo", dest="mvn_upload_repo", help="MVN repository to upload to",
                            default=os.getenv("MVN_UPLOAD_REPO") or "\x63\x64\x74.wa\x79\x34")
        parser.add_argument("--mvn-download-repo", dest="mvn_download_repo", help="MVN repository to download from",
                            default=os.getenv("MVN_DOWNLOAD_REPO") or "maven-virtual")

        # DMS arguments
        parser.add_argument("--dms-api-version", dest="dms_api_version", type=int,
                            help="DMS REST API version to use", default=3, choices=[2,3])
        parser.add_argument("--dms-crs-url", dest="dms_crs_url", type=str,
                            help="DMS Component Registry URL (necessary for DMS API v2)",
                            default=os.getenv("DMS_CRS_URL"))
        parser.add_argument("--dms-token", dest="dms_token", type=str, help="DMS authorization token",
                            default=os.getenv("DMS_TOKEN"))
        parser.add_argument("--dms-url", dest="dms_url", help="DMS URL",
                            default=os.getenv("DMS_URL"))
        parser.add_argument("--dms-user", dest="dms_user", help="DMS user",
                            default=os.getenv("DMS_USER"))
        parser.add_argument("--dms-password", dest="dms_password", help="DMS password",
                            default=os.getenv("DMS_PASSWORD"))
        parser.add_argument("--dms-processes", dest="dms_processes", 
                            help="Processes (threads) to run in parallel",
                            type=int, default=3)

        # CITYPE properties
        parser.add_argument("--ci-type-release-notes", dest="ci_type_release_notes",
                            help="CI Type for Release Notes artifacts", default="RELEASENOTES")
        parser.add_argument("--ci-type-documentation", dest="ci_type_documentation",
                            help="CI Type for Documentation artifacts", default="DOCS")

        return parser

    def setup_from_args(self, args):
        """
        Do self initialization with arguments parsed
        :param argpares.namespace args: parsed arguments
        """
        self._args = args

        # adjust file paths to absolute
        self._args.config_file = os.path.abspath(self._args.config_file)

        # just log the arguments
        for _k, _v in self._args.__dict__.items():
            _display_value = _v

            if _v and any([_k.endswith('password'), _k.endswith('token')]):
                _display_value = '*'*len(_v)

            logging.info(self.__log_msg(f"{_k.upper()}:\t[{_display_value}]"))


    def load_config(self):
        with open(self._args.config_file, mode='rt') as _config:
            self._components = json.load(_config)


    def run(self):
        """
        Do the main process
        """
        logging.info(self.__log_msg(f"Reading components configuration: [{self._args.config_file}]"))

        self.load_config()

        logging.info(self.__log_msg(f"Components to process: {len(self._components)}"))

        with multiprocessing.Pool(processes=self._args.dms_processes) as pool:
            _exceptions = pool.map(self.process_component, self._components)

        _components_count = len(_exceptions)
        _exceptions = list(filter(lambda x: bool(x), _exceptions))

        logging.info(self.__log_msg(f"All [{_components_count}] components processed. Errors: [{len(_exceptions)}]"))
        return _exceptions

    def main(self):
        _parser = self.basic_args()
        _args = _parser.parse_args()

        if hasattr(_args, "log_level"):
            logging.basicConfig(
                    format="%(pathname)s: %(asctime)-15s: %(levelname)s: %(funcName)s: %(lineno)d: %(message)s",
                    level=_args.log_level)
            logging.info(self.__log_msg(f"Logging level is set to {_args.log_level}"))

        self.setup_from_args(_args)

        __start_time = time.time()

        _exceptions = self.run()

        __elapsed = time.time() - __start_time
        logging.info(self.__log_msg(f"Finished. Elapsed time: {__elapsed}"))

        if _exceptions:
            # log ALL exceptions
            # NOTE: 'labmda' and 'generator' expressions do not work here
            # because of standard output
            for _e in _exceptions:
                # NOTE: we do not need to modify log message here because process name
                # is inside the exception, see 'process_component' method
                logging.error(_e)

            # raise first one to return non-zero code
            raise Exception(_exceptions.pop(0))

if __name__ == '__main__':
    DmsMirror().main()
