#!/usr/bin/env python3

import os
import tempfile
import json

import unittest
import unittest.mock
from ..dms_mirror import DmsMirror
from oc_cdtapi.DmsAPI import DmsAPI, DmsAPIv3
from string import Template
import re
from oc_checksumsq.checksums_interface import FileLocation

# disable extra logging
import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True

class DmsMirrorTestBase(unittest.TestCase):
    def setUp(self):
        self.env = {
                'AMQP_URL': 'amqp://amqp.example.com:5672',
                'AMQP_USER': 'test_amqp_user',
                'AMQP_PASSWORD': 'test_amqp_password',
                'MVN_URL': 'https://mvn.example.com/nexus',
                'MVN_USER': 'test_mvn_user',
                'MVN_PASSWORD': 'test_mvn_password',
                'MVN_UPLOAD_REPO': 'test_upload_repo',
                'MVN_DOWNLOAD_REPO': 'test_download_repo',
                'MVN_PREFIX': 'com.example',
                'DMS_CRS_URL': 'https://dms-crs.example.com',
                'DMS_URL': 'https://dms.example.com',
                'DMS_USER': 'test_dms_user',
                'DMS_PASSWORD': 'test_dms_password',
                'DMS_TOKEN': 'test_dms_token'}

        self.args = unittest.mock.MagicMock()
        self.args.amqp_url = self.env.get('AMQP_URL')
        self.args.amqp_username = self.env.get('AMQP_USER')
        self.args.amqp_password = self.env.get('AMQP_PASSWORD')
        self.args.config_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'resources', 'config.json')
        self.args.mvn_prefix = self.env.get('MVN_PREFIX')
        self.args.mvn_url = self.env.get('MVN_URL')
        self.args.mvn_user = self.env.get('MVN_USER')
        self.args.mvn_password = self.env.get('MVN_PASSWORD')
        self.args.mvn_upload_repo = self.env.get('MVN_UPLOAD_REPO')
        self.args.mvn_download_repo = self.env.get('MVN_DOWNLOAD_REPO')
        self.args.dms_url = self.env.get('DMS_URL')
        self.args.dms_user = self.env.get('DMS_USER')
        self.args.dms_password = self.env.get('DMS_PASSWORD')
        self.args.ci_type_documentation = 'DOCS'
        self.args.ci_type_release_notes = 'RELEASENOTES'
        self.dmsmirror = DmsMirror()
        self.dmsmirror._queue_client = unittest.mock.MagicMock()
        self.dmsmirror._mvn_client = unittest.mock.MagicMock()

class DmsMirrorInitTestSuite(DmsMirrorTestBase):
    def test_init(self):

        with unittest.mock.patch.dict(os.environ, self.env):
            _parser = self.dmsmirror.basic_args()

        _supposed_defaults = {
                'amqp_url': self.env.get('AMQP_URL'),
                'queue': '\x63dt.dlartifa\x63ts.input',
                'declare': 'no',
                'amqp_username': self.env.get('AMQP_USER'),
                'amqp_password': self.env.get('AMQP_PASSWORD'),
                'reconnect_tries': 0,
                'reconnect_delay': 0,
                'priority': 1,
                'queue_cnt': '\x63dt.dl\x63ontents.input',
                'log_level': 20,
                'config_file': os.path.join(os.getcwd(), 'config.json'),
                'retries_count': 5,
                'mvn_prefix': self.env.get('MVN_PREFIX'),
                'mvn_url': self.env.get('MVN_URL'),
                'mvn_user': self.env.get('MVN_USER'),
                'mvn_password': self.env.get('MVN_PASSWORD'),
                'mvn_upload_repo': self.env.get('MVN_UPLOAD_REPO'),
                'mvn_download_repo': self.env.get('MVN_DOWNLOAD_REPO'),
                'dms_api_version': 3,
                'dms_crs_url': self.env.get('DMS_CRS_URL'),
                'dms_token': self.env.get('DMS_TOKEN'),
                'dms_url': self.env.get('DMS_URL'),
                'dms_user': self.env.get('DMS_USER'),
                'dms_password': self.env.get('DMS_PASSWORD'),
                'ci_type_release_notes': 'RELEASENOTES',
                'ci_type_documentation': 'DOCS'}

        for _k, _v in _supposed_defaults.items():
            self.assertEqual(_parser.get_default(_k), _v)

class DmsMirrorV2TestSuite(DmsMirrorTestBase):
    def setUp(self):
        super().setUp()
        self.args.dms_api_version = 2
        self.args.dms_crs_url = self.env.get('DMS_CRS_URL')
        self.args.dms_token = self.env.get('DMS_TOKEN')

        with unittest.mock.patch.dict(os.environ, self.env):
            self.dmsmirror._dms_client = DmsAPI()

        self.dmsmirror.setup_from_args(self.args)

        with open(self.args.config_file, mode='rt') as _config:
            self.dmsmirror._components = json.load(_config)

    def test_process_component_ok(self):
        _component = list(self.dmsmirror._components.keys()).pop()
        _versions = ["1", "2", "3"]
        self.assertIsNotNone(_component)
        self.dmsmirror.process_version = unittest.mock.MagicMock(return_value=None)
        self.dmsmirror._dms_client.get_versions = unittest.mock.MagicMock(return_value=_versions)
        self.dmsmirror._dms_client.get_versions.__name__ = "get_versions"
        self.assertIsNone(self.dmsmirror.process_component(_component))
        self.assertEqual(self.dmsmirror.process_version.call_count, len(_versions))
        self.dmsmirror._dms_client.get_versions.assert_called_once_with(_component)

        for _version in _versions:
            self.dmsmirror.process_version.assert_any_call(_version, _component)

    def test_process_component_disabled(self):
        _component = list(self.dmsmirror._components.keys()).pop()
        _versions = ["1", "2", "3"]
        self.assertIsNotNone(_component)
        self.dmsmirror._components[_component]["enabled"] = False
        self.dmsmirror.process_version = unittest.mock.MagicMock(return_value=None)
        self.dmsmirror._dms_client.get_versions = unittest.mock.MagicMock(return_value=_versions)
        self.dmsmirror._dms_client.get_versions.__name__ = "get_versions"
        self.assertIsNone(self.dmsmirror.process_component(_component))
        self.dmsmirror._dms_client.get_versions.assert_not_called()
        self.dmsmirror.process_version.assert_not_called()

    def test_process_component__exception(self):
        _component = list(self.dmsmirror._components.keys()).pop()
        self.assertIsNotNone(_component)
        _exc = Exception("test")
        self.dmsmirror.process_version = unittest.mock.MagicMock(return_value=None)
        self.dmsmirror._dms_client.get_versions = unittest.mock.MagicMock(side_effect=_exc)
        self.dmsmirror._dms_client.get_versions.__name__ = "get_versions"
        self.assertIsInstance(self.dmsmirror.process_component(_component), type(_exc))
        self.dmsmirror.process_version.assert_not_called()
        self.dmsmirror._dms_client.get_versions.assert_called_once_with(_component)

    def test_process_version(self):
        _component = list(self.dmsmirror._components.keys()).pop()
        self.assertIsNotNone(_component)
        _artifacts = ["a1", "a2", "a3"]
        _version = "1"
        self.dmsmirror.process_artifact = unittest.mock.MagicMock(return_value=None)
        self.dmsmirror._dms_client.get_artifacts = unittest.mock.MagicMock(return_value=_artifacts)
        self.dmsmirror._dms_client.get_artifacts.__name__ = "get_artifacts"
        self.assertIsNone(self.dmsmirror.process_version(_version, _component))
        self.assertEqual(self.dmsmirror.process_artifact.call_count, len(_artifacts))
        self.dmsmirror._dms_client.get_artifacts.assert_called_once_with(_component, _version)

        for _artifact in _artifacts:
            self.dmsmirror.process_artifact.assert_any_call(_artifact, _component, _version)

    def _get_artifact_test_case(self, suffix):
        _config = self.dmsmirror._components

        for _component, _params in _config.items():
            if any(list(map(lambda _x: not _params.get(_x), ["tgtGavTemplate", "ci_type"]))):
                continue

            for _artifact_type, _tgtGavTemplate in _params.get("tgtGavTemplate").items():
                if suffix in _tgtGavTemplate:
                    return (_component,
                            self.dmsmirror._get_static_ci_type(_artifact_type) or _params["ci_type"],
                            _artifact_type)

    def _process_artifact_asserts(self, component, version, artifact, artifact_type,
                                  ci_type, substitutes, artifact_info=dict()):
        _tgt_gav = self.dmsmirror._components[component]["tgtGavTemplate"][artifact_type].replace("\\", "")
        _tgt_gav = Template(_tgt_gav).substitute(substitutes)
        _tgt_gav = re.sub('[^\w\-\.\:_]+', "_", _tgt_gav)

        # target artifacts does not exist
        self.dmsmirror._mvn_client.exists = unittest.mock.MagicMock(return_value=False)
        self.dmsmirror._copy_artifact = unittest.mock.MagicMock(return_value=None)
        self.dmsmirror._register_artifact = unittest.mock.MagicMock(return_value=None)

        if hasattr(self.dmsmirror._dms_client, "get_artifact_info"):
            self.dmsmirror._dms_client.get_artifact_info = unittest.mock.MagicMock(return_value=artifact_info)

        self.assertIsNone(self.dmsmirror.process_artifact(artifact, component, version))
        self.dmsmirror._mvn_client.exists.assert_called_once_with(_tgt_gav, repo=self.args.mvn_download_repo)
        self.dmsmirror._register_artifact.assert_called_once_with(_tgt_gav, ci_type)
        self.dmsmirror._copy_artifact.assert_called_once_with(component, version, artifact, _tgt_gav)

        if hasattr(self.dmsmirror._dms_client, "get_artifact_info"):
            self.dmsmirror._dms_client.get_artifact_info.assert_called_once_with(component, version, artifact["id"])

        # now case when target artifact exists
        self.dmsmirror._mvn_client.exists.reset_mock()
        self.dmsmirror._mvn_client.exists.return_value = True
        self.dmsmirror._copy_artifact.reset_mock()
        self.dmsmirror._register_artifact.reset_mock()

        if hasattr(self.dmsmirror._dms_client, "get_artifact_info"):
            self.dmsmirror._dms_client.get_artifact_info.reset_mock()

        self.assertIsNone(self.dmsmirror.process_artifact(artifact, component, version))
        self.dmsmirror._mvn_client.exists.assert_called_once_with(_tgt_gav, repo=self.args.mvn_download_repo)
        self.dmsmirror._register_artifact.assert_not_called()
        self.dmsmirror._copy_artifact.assert_not_called()

        if hasattr(self.dmsmirror._dms_client, "get_artifact_info"):
            self.dmsmirror._dms_client.get_artifact_info.assert_called_once_with(component, version, artifact["id"])

    def test_artifact_classifier_with_colon(self):
        self.assertEqual(self.args.dms_api_version, 2)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$c_colon")
        _version = "1"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "name": "a1",
                     "packaging": "pkg",
                     "classifier": "c1",
                     "id": 1}
        _substitutes = {
                "at": _artifact_type,
                "n": _artifact.get("name"),
                "v": _version,
                "p": _artifact.get("packaging"),
                "c_colon": f":{_artifact.get('classifier')}",
                "prefix": self.args.mvn_prefix}
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_classifier_wo_delimeter(self):
        self.assertEqual(self.args.dms_api_version, 2)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$cl")
        _version = "1"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "name": "a1",
                     "packaging": "pkg",
                     "classifier": "c1",
                     "id": 1}
        _substitutes = {
                "at": _artifact_type,
                "n": _artifact.get("name"),
                "v": _version,
                "p": _artifact.get("packaging"),
                "cl": _artifact.get('classifier'),
                "prefix": self.args.mvn_prefix}
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_classifier_with_hyphen(self):
        self.assertEqual(self.args.dms_api_version, 2)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$c_hyphen")
        _version = "1"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "name": "a1",
                     "packaging": "pkg",
                     "classifier": "c1"}
        _substitutes = {
                "at": _artifact_type,
                "n": _artifact.get("name"),
                "v": _version,
                "p": _artifact.get("packaging"),
                "c_hyphen": f"-{_artifact.get('classifier')}",
                "prefix": self.args.mvn_prefix}
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_empty_classifier_with_hyphen(self):
        self.assertEqual(self.args.dms_api_version, 2)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$c_hyphen")
        _version = "1"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "name": "a1",
                     "packaging": "pkg",
                     "classifier": None}
        _substitutes = {
                "at": _artifact_type,
                "n": _artifact.get("name"),
                "v": _version,
                "p": _artifact.get("packaging"),
                "c_hyphen": "",
                "prefix": self.args.mvn_prefix}
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_empty_classifier_with_colon(self):
        self.assertEqual(self.args.dms_api_version, 2)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$c_colon")
        _version = "1"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "name": "a1",
                     "packaging": "pkg",
                     "classifier": None}
        _substitutes = {
                "at": _artifact_type,
                "n": _artifact.get("name"),
                "v": _version,
                "p": _artifact.get("packaging"),
                "c_colon": "",
                "prefix": self.args.mvn_prefix}
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_empty_classifier_wo_delimiter(self):
        self.assertEqual(self.args.dms_api_version, 2)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$cl")
        _version = "1"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "name": "a1",
                     "packaging": "pkg",
                     "classifier": None}
        _substitutes = {
                "at": _artifact_type,
                "n": _artifact.get("name"),
                "v": _version,
                "p": _artifact.get("packaging"),
                "cl": "",
                "prefix": self.args.mvn_prefix}
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_copy_artifact(self):
        self.assertEqual(self.args.dms_api_version, 2)
        _component = "component"
        _artifact_type = "distribution"
        _artifact = {"type": _artifact_type,
                     "name": "a1",
                     "packaging": "pkg",
                     "classifier": "c1"}
        _version = "1"
        _tgt_gav = f"{self.args.mvn_prefix}.{_component}:{_component}:{_version}:pkg"
        _src_gav = f"{self.args.mvn_prefix}.{_component}:{_component}:{_version}:pkg:{_artifact_type}"

        #mock for v.2:
        self.assertTrue(hasattr(self.dmsmirror._dms_client, "get_gav"))
        self.assertFalse(hasattr(self.dmsmirror._dms_client, "download_component"))
        self.dmsmirror._dms_client.get_gav = unittest.mock.MagicMock(return_value=_src_gav)
        self.dmsmirror._dms_client.get_gav.__name__ = 'get_gav'
        self.dmsmirror._mvn_client.cat = unittest.mock.MagicMock(return_value="OK")
        self.dmsmirror._mvn_client.upload = unittest.mock.MagicMock(return_value="OK")

        self.dmsmirror._copy_artifact(_component, _version, _artifact, _tgt_gav)
        self.dmsmirror._dms_client.get_gav.assert_called_once_with(
                _component, _version, _artifact_type, _artifact.get("name"), _artifact.get("classifier"))
        self.dmsmirror._mvn_client.cat.assert_called_once_with(
                _src_gav, repo=self.args.mvn_download_repo, stream=True, binary=True, write_to=unittest.mock.ANY)
        self.dmsmirror._mvn_client.upload.assert_called_once_with(
                _tgt_gav, repo=self.args.mvn_upload_repo, data=unittest.mock.ANY, pom=True)

    def test_register_artifact(self):
        _tgt_gav = f"{self.args.mvn_prefix}.target:artifact:1:pkg"
        _ci_type = "CITYPE"

        self.dmsmirror._register_artifact(_tgt_gav, _ci_type)

        self.dmsmirror._queue_client.connect.assert_called_once()
        self.dmsmirror._queue_client.register_file.assert_called_once_with(
                FileLocation(_tgt_gav, "NXS", None), _ci_type, 0)
        self.dmsmirror._queue_client.disconnect.assert_called_once()

    def test_get_static_ci_type(self):
        self.assertEqual(self.dmsmirror._get_static_ci_type("documentation"), self.args.ci_type_documentation)
        self.assertEqual(self.dmsmirror._get_static_ci_type("notes"), self.args.ci_type_release_notes)
        self.assertEqual(self.dmsmirror._get_static_ci_type("report"), self.args.ci_type_release_notes)
        self.assertIsNone(self.dmsmirror._get_static_ci_type("distribution"))

class DmsMirrorV3TestSuite(DmsMirrorV2TestSuite):
    def setUp(self):
        super().setUp()
        self.args.dms_api_version = 3

        self.dmsmirror._dms_client = DmsAPIv3(
                root=self.args.dms_url,
                user=self.args.dms_user,
                auth=self.args.dms_password)
        self.dmsmirror.setup_from_args(self.args)

        with open(self.args.config_file, mode='rt') as _config:
            self.dmsmirror._components = json.load(_config)


    def test_artifact_classifier_with_colon(self):
        self.assertEqual(self.args.dms_api_version, 3)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$c_colon")
        _version = "1"
        _name = "name"
        _classifier = "cl"
        _packaging = "pkg"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "fileName": f"{_name}-{_version}-{_classifier}.{_packaging}",
                     "id": 1}
        _substitutes = {
                "at": _artifact_type,
                "n": _name,
                "v": _version,
                "p": _packaging,
                "c_colon": f":{_classifier}",
                "prefix": self.args.mvn_prefix}
        _artifact_info = {
                "id": _artifact["id"],
                "type": _artifact_type,
                "fileName": _artifact["fileName"],
                "gav": {
                    "groupId": "com.example.artifact",
                    "artifactId": _name,
                    "version": _version,
                    "packaging": _packaging,
                    "classifier": _classifier},
                "repositoryType":"MAVEN"}
        # with info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type,
                                       _ci_type, _substitutes, _artifact_info)
        # without info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_classifier_wo_delimeter(self):
        self.assertEqual(self.args.dms_api_version, 3)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$cl")
        _version="1"
        _name = "name"
        _classifier = "cl"
        _packaging = "pkg"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "fileName": f"{_name}-{_version}-{_classifier}.{_packaging}",
                     "id": 1}
        _substitutes = {
                "at": _artifact_type,
                "n": _name,
                "v": _version,
                "p": _packaging,
                "cl": _classifier,
                "prefix": self.args.mvn_prefix}
        _artifact_info = {
                "id": _artifact["id"],
                "type": _artifact_type,
                "fileName": _artifact["fileName"],
                "gav": {
                    "groupId": "com.example.artifact",
                    "artifactId": _name,
                    "version": _version,
                    "packaging": _packaging,
                    "classifier": _classifier},
                "repositoryType":"MAVEN"}
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type,
                                       _ci_type, _substitutes, _artifact_info)
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_classifier_with_hyphen(self):
        self.assertEqual(self.args.dms_api_version, 3)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$c_hyphen")
        _version="1"
        _name = "name"
        _classifier = "cl"
        _packaging = "pkg"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "fileName": f"{_name}-{_version}-{_classifier}.{_packaging}",
                     "id": 1}
        _substitutes = {
                "at": _artifact_type,
                "n": _name,
                "v": _version,
                "p": _packaging,
                "c_hyphen": f"-{_classifier}",
                "prefix": self.args.mvn_prefix}
        _artifact_info = {
                "id": _artifact["id"],
                "type": _artifact_type,
                "fileName": _artifact["fileName"],
                "gav": {
                    "groupId": "com.example.artifact",
                    "artifactId": _name,
                    "version": _version,
                    "packaging": _packaging,
                    "classifier": _classifier},
                "repositoryType":"MAVEN"}

        # with info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type,
                                       _ci_type, _substitutes, _artifact_info)
        # without info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_empty_classifier_with_hyphen(self):
        self.assertEqual(self.args.dms_api_version, 3)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$c_hyphen")
        _version="1"
        _name = "name"
        _packaging = "pkg"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "fileName": f"{_name}-{_version}.{_packaging}",
                     "id": 1}
        _substitutes = {
                "at": _artifact_type,
                "n": _name,
                "v": _version,
                "p": _packaging,
                "c_hyphen": "",
                "prefix": self.args.mvn_prefix}
        _artifact_info = {
                "id": _artifact["id"],
                "type": _artifact_type,
                "fileName": _artifact["fileName"],
                "gav": {
                    "groupId": "com.example.artifact",
                    "artifactId": _name,
                    "version": _version,
                    "packaging": _packaging},
                "repositoryType":"MAVEN"}

        # with info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type,
                                       _ci_type, _substitutes, _artifact_info)
        # without info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_empty_classifier_with_colon(self):
        self.assertEqual(self.args.dms_api_version, 3)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$c_colon")
        _version = "1"
        _name = "name"
        _packaging = "pkg"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "fileName": f"{_name}-{_version}.{_packaging}",
                     "id": 1}
        _substitutes = {
                "at": _artifact_type,
                "n": _name,
                "v": _version,
                "p": _packaging,
                "c_colon": "",
                "prefix": self.args.mvn_prefix}
        _artifact_info = {
                "id": _artifact["id"],
                "type": _artifact_type,
                "fileName": _artifact["fileName"],
                "gav": {
                    "groupId": "com.example.artifact",
                    "artifactId": _name,
                    "version": _version,
                    "packaging": _packaging},
                "repositoryType":"MAVEN"}

        # with info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type,
                                       _ci_type, _substitutes, _artifact_info)

        # without info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_artifact_empty_classifier_wo_delimiter(self):
        self.assertEqual(self.args.dms_api_version, 3)
        # see config.json for appropriate test case
        _component, _ci_type, _artifact_type = self._get_artifact_test_case("$cl")
        _version = "1"
        _name = "name"
        _packaging = "pkg"
        # should be created with target gav
        _artifact = {"type": _artifact_type,
                     "fileName": f"{_name}-{_version}.{_packaging}",
                     "id": 1}
        _substitutes = {
                "at": _artifact_type,
                "n": _name,
                "v": _version,
                "p": _packaging,
                "cl": "",
                "prefix": self.args.mvn_prefix}
        _artifact_info = {
                "id": _artifact["id"],
                "type": _artifact_type,
                "fileName": _artifact["fileName"],
                "gav": {
                    "groupId": "com.example.artifact",
                    "artifactId": _name,
                    "version": _version,
                    "packaging": _packaging},
                "repositoryType":"MAVEN"}

        # with info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type,
                                       _ci_type, _substitutes, _artifact_info)
        # without info
        self._process_artifact_asserts(_component, _version, _artifact, _artifact_type, _ci_type, _substitutes)

    def test_copy_artifact(self):
        self.assertEqual(self.args.dms_api_version, 3)
        _component = "component"
        _artifact_type = "distribution"
        _artifact = {"type": _artifact_type,
                     "id": 10}
        _version = "1"
        _tgt_gav = f"{self.args.mvn_prefix}.{_component}:{_component}:{_version}:pkg"

        #mock for v.3:
        self.assertFalse(hasattr(self.dmsmirror._dms_client, "get_gav"))
        self.assertTrue(hasattr(self.dmsmirror._dms_client, "download_component"))
        self.dmsmirror._dms_client.download_component = unittest.mock.MagicMock(return_value="OK")
        self.dmsmirror._dms_client.download_component.__name__ = 'download_component'
        self.dmsmirror._mvn_client.cat = unittest.mock.MagicMock(return_value="OK")
        self.dmsmirror._mvn_client.upload = unittest.mock.MagicMock(return_value="OK")

        self.dmsmirror._copy_artifact(_component, _version, _artifact, _tgt_gav)
        self.dmsmirror._dms_client.download_component.assert_called_once_with(
                _component, _version, _artifact.get('id'), write_to=unittest.mock.ANY)
        self.dmsmirror._mvn_client.cat.assert_not_called()
        self.dmsmirror._mvn_client.upload.assert_called_once_with(
                _tgt_gav, repo=self.args.mvn_upload_repo, data=unittest.mock.ANY, pom=True)
