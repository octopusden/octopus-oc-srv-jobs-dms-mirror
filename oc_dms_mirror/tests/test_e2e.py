#!/usr/bin/env python3
"""
End-to-end tests of both entry points with config files on disk.

The webhook runs through the Flask route, the cronjob through the same steps as run():
component list from DMS, config.json as the mapping, process_component() per component.
Only the external systems are replaced, by in-memory fakes that record what reaches them
(Nexus uploads, register_file messages, citypedms registrations).
"""

import copy
import json
import os
import tempfile
import unittest
import unittest.mock
from types import SimpleNamespace

from oc_cdtapi.API import HttpAPIError

from ..dms_mirror import DmsMirror
from ..rest_api.app import create_app
from .config import TestConfig

# disable extra logging
import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True

MVN_PREFIX = "com.example"
UPLOAD_REPO = "test_upload_repo"

# a config.json entry with its own GAV and ci_type, and the generic gav_template_config.json
CONFIG = {
    "legacy-comp": {
        "ci_type": "LEGACYDSTR",
        "tgtGavTemplate": {
            "notes": "\\$prefix.ext.release_notes:legacy-comp\\$c_hyphen:\\$v:\\$p",
            "distribution": "\\$prefix.dist.legacy:\\$n\\$c_hyphen:\\$v:\\$p",
            "report": "\\$prefix.ext.release_notes:legacy-comp\\$c_hyphen:\\$v:\\$p",
            "documentation": "\\$prefix.ext.documentation:legacy-comp\\$c_hyphen:\\$v:\\$p"}},
    # archived in DMS, but nobody removed it from config.json
    "archived-comp": {
        "ci_type": "ARCHDSTR",
        "tgtGavTemplate": {"distribution": "\\$prefix.dist.archived:\\$n\\$c_hyphen:\\$v:\\$p"}}
}

GAV_TEMPLATE_CONFIG = {
    "ci_type": "$component",
    "tgtGavTemplate": {
        "notes": "$prefix.ext.release_notes:$component\\$c_hyphen:\\$v:\\$p",
        "distribution": "$prefix.dist.$client.$component:\\$n\\$c_hyphen:\\$v:\\$p",
        "report": "$prefix.ext.release_notes:$component\\$c_hyphen:\\$v:\\$p",
        "documentation": "$prefix.ext.documentation:$component\\$c_hyphen:\\$v:\\$p"
    }
}

LEGACY_DIST_GAV = f"{MVN_PREFIX}.dist.legacy:legacy-comp:4.3.10:zip"
LEGACY_NOTES_GAV = f"{MVN_PREFIX}.ext.release_notes:legacy-comp:4.3.10:pdf"
NEW_COMP_DIST_GAV = f"{MVN_PREFIX}.dist.CLIENT_A.new-comp:new-comp:1.0.0:zip"


def _artifact(artifact_id, artifact_type, file_name, name, packaging):
    return {
        "id": artifact_id,
        "type": artifact_type,
        "fileName": file_name,
        "repositoryType": "MAVEN",
        "gav": {"groupId": "com.example.dms", "artifactId": name, "packaging": packaging}}


def _component(component_id, client_code=None, labels=None, versions=None):
    return {
        "id": component_id,
        "name": component_id,
        "clientCode": client_code,
        "parentComponent": None,
        "solution": False,
        "labels": labels or [],
        "versions": versions or {}}


# DMS content shared by every case, versions newest first as DMS returns them
# legacy-comp 4.3.9 is already mirrored, 4.3.10 and new-comp 1.0.0 are not
DMS_COMPONENTS = {
    "legacy-comp": _component("legacy-comp", versions={
        "4.3.10": [_artifact(3, "distribution", "legacy-comp-4.3.10.zip", "legacy-comp", "zip"),
                   _artifact(4, "notes", "legacy-comp-4.3.10.pdf", "legacy-comp", "pdf")],
        "4.3.9": [_artifact(1, "distribution", "legacy-comp-4.3.9.zip", "legacy-comp", "zip"),
                  _artifact(2, "notes", "legacy-comp-4.3.9.pdf", "legacy-comp", "pdf")]}),
    "new-comp": _component("new-comp", client_code="CLIENT_A", versions={
        "1.0.0": [_artifact(5, "distribution", "new-comp-1.0.0.zip", "new-comp", "zip")]}),
    "sandbox": _component("sandbox", labels=["test-component"], versions={
        "0.1": [_artifact(6, "distribution", "sandbox-0.1.zip", "sandbox", "zip")]}),
}

CITYPEDMS = {"legacy-comp": {"dms_id": "legacy-comp", "ci_type_id": "LEGACYDSTR"}}

NEXUS_GAVS = [f"{MVN_PREFIX}.dist.legacy:legacy-comp:4.3.9:zip",
              f"{MVN_PREFIX}.ext.release_notes:legacy-comp:4.3.9:pdf"]


class FakeDms:
    """DMS API v3 subset used by DmsMirror"""
    def __init__(self, components):
        self.components = components
        self.missing_files = set()
        # DMS answers 500 for these downloads and for the version lists of these components
        self.failing_files = set()
        self.failing_versions = set()

    def get_components(self):
        # archived components are not returned by DMS
        return [{_k: _v for _k, _v in _c.items() if _k != "versions"} for _c in self.components.values()]

    def get_versions(self, component):
        if component not in self.components:
            raise HttpAPIError(code=404, url=f"components/{component}/versions")
        if component in self.failing_versions:
            raise HttpAPIError(code=500, url=f"components/{component}/versions")
        return list(self.components[component]["versions"])

    def get_artifacts(self, component, version):
        # the list call returns neither name nor packaging nor classifier
        return [{_k: _v for _k, _v in _a.items() if _k != "gav"}
                for _a in self.components[component]["versions"][version]]

    def get_artifact_info(self, component, version, artifact_id):
        return self._find(component, version, artifact_id)

    def download_component(self, component, version, artifact_id, write_to):
        self._find(component, version, artifact_id)
        if artifact_id in self.missing_files:
            # listed in DMS, but the file was never published to its repositories
            raise HttpAPIError(code=400, url=f"components/{component}/versions/{version}/artifacts/{artifact_id}/download",
                               resp=SimpleNamespace(json=lambda: {
                                   "code": "DMS-40006",
                                   "message": f"Artifact [{artifact_id}] was not found in any of the repositories"}))
        if artifact_id in self.failing_files:
            raise HttpAPIError(code=500, url=f"components/{component}/versions/{version}/artifacts/{artifact_id}/download",
                               resp=SimpleNamespace(json=lambda: {"message": "Internal Server Error"}))
        write_to.write(f"{component}:{version}:{artifact_id}".encode())

    def _find(self, component, version, artifact_id):
        for _a in self.components[component]["versions"][version]:
            if _a["id"] == artifact_id:
                return _a
        raise HttpAPIError(code=404, url=f"components/{component}/versions/{version}/artifacts/{artifact_id}")


class FakeNexus:
    def __init__(self, gavs):
        self.gavs = set(gavs)
        self.uploaded = list()

    def exists(self, gav, repo=None):
        return gav in self.gavs

    def upload(self, gav, repo=None, data=None, pom=False):
        self.gavs.add(gav)
        self.uploaded.append((gav, repo, data.read()))


class FakeRegistry:
    """Postgres API subset: citypedms and citypeincs"""
    def __init__(self, citypedms):
        self.citypedms = citypedms
        self.registered = list()

    def get_citypedms_by_dms_id(self, dms_id):
        if dms_id not in self.citypedms:
            raise HttpAPIError(code=404, url=f"citypedms/{dms_id}")
        return self.citypedms[dms_id]

    def get_citypeincs_by_citype_id(self, citype_id):
        raise HttpAPIError(code=404, url=f"citypeincs/{citype_id}")

    def post_new_component(self, payload):
        self.registered.append(payload)
        self.citypedms[payload["dms_id"]] = {"dms_id": payload["dms_id"], "ci_type_id": payload["ci_type_id"]}
        return SimpleNamespace(status_code=201)


class FakeQueue:
    def __init__(self):
        self.enqueued = list()

    def connect(self):
        pass

    def disconnect(self):
        pass

    def register_file(self, location, ci_type, depth):
        self.enqueued.append((location.path, ci_type))


class DmsMirrorE2ETestSuite(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dms = FakeDms(copy.deepcopy(DMS_COMPONENTS))
        self.nexus = FakeNexus(NEXUS_GAVS)
        self.registry = FakeRegistry(copy.deepcopy(CITYPEDMS))
        self.queue = FakeQueue()

    def _make_mirror(self):
        _mirror = DmsMirror()
        _mirror._dms_client = self.dms
        _mirror._mvn_client = self.nexus
        _mirror._pg_client = self.registry
        _mirror._queue_client = self.queue
        return _mirror

    def _parse_args(self, *extra):
        _config_file = os.path.join(self._tmp.name, "config.json")
        _gav_template_file = os.path.join(self._tmp.name, "gav_template_config.json")

        with open(_config_file, mode="wt") as _f:
            json.dump(CONFIG, _f)

        with open(_gav_template_file, mode="wt") as _f:
            json.dump(GAV_TEMPLATE_CONFIG, _f)

        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            _parser = DmsMirror().basic_args()

        return _parser.parse_args([
            "--config-file", _config_file,
            "--gav-template-config-file", _gav_template_file,
            "--mvn-prefix", MVN_PREFIX,
            "--mvn-upload-repo", UPLOAD_REPO,
            "--mvn-download-repo", "test_download_repo",
            "--msg-target", "amqp",
            "--retries-count", "1",
            "--auto-register-component", "true",
            *extra])

    def _run_webhook(self, component, version):
        """POST a PUBLISH_COMPONENT_VERSION event to the webhook service"""
        _payload = {
            "type": "PUBLISH_COMPONENT_VERSION",
            "componentVersion": {
                "component": component,
                "version": version,
                "displayName": component,
                "labels": [],
                "clientCode": DMS_COMPONENTS[component]["clientCode"]},
            "artifacts": self.dms.get_artifacts(component, version)}

        with unittest.mock.patch("oc_dms_mirror.rest_api.app.routes.DmsMirror", side_effect=self._make_mirror):
            _app = create_app(TestConfig, self._parse_args())
            _response = _app.test_client().post("/register-component-version-artifact", json=_payload)

        return _response.status_code, _response.json.get("result")

    def _run_cron(self, *extra):
        """One cronjob run: the steps of run(), without the multiprocessing.Pool"""
        _mirror = self._make_mirror()
        _mirror.setup_from_args(self._parse_args(*extra))
        _mirror.logger = unittest.mock.MagicMock()
        _mirror.load_components()
        _mirror.load_config()
        _mirror.warn_unknown_config_components()
        # pool workers would record into their own copies of the fakes
        _errors = list(filter(bool, map(_mirror.process_component, _mirror._components)))
        _warnings = [_call[0][0] for _call in _mirror.logger.warning.call_args_list]
        return _errors, _warnings

    def _uploaded(self):
        return [_gav for _gav, _repo, _data in self.nexus.uploaded]

    def test_webhook__new_component_registered_and_mirrored(self):
        self.assertEqual(self._run_webhook("new-comp", "1.0.0"), (200, "Success"))
        self.assertEqual(len(self.registry.registered), 1)
        self.assertEqual(self.registry.registered[0]["ci_type_id"], "new-comp")
        self.assertEqual(self.registry.registered[0]["is_standard"], "N")
        self.assertEqual(self.nexus.uploaded, [(NEW_COMP_DIST_GAV, UPLOAD_REPO, b"new-comp:1.0.0:5")])
        self.assertEqual(self.queue.enqueued, [(NEW_COMP_DIST_GAV, "new-comp")])

    def test_webhook__legacy_component_uses_config(self):
        self.assertEqual(self._run_webhook("legacy-comp", "4.3.10"), (200, "Success"))
        self.assertEqual(self.registry.registered, [])
        self.assertEqual(self.nexus.uploaded, [
            (LEGACY_DIST_GAV, UPLOAD_REPO, b"legacy-comp:4.3.10:3"),
            (LEGACY_NOTES_GAV, UPLOAD_REPO, b"legacy-comp:4.3.10:4")])
        self.assertEqual(self.queue.enqueued, [
            (LEGACY_DIST_GAV, "LEGACYDSTR"),
            (LEGACY_NOTES_GAV, "RELEASENOTES")])

    def test_cron__legacy_component_uses_config(self):
        _errors, _warnings = self._run_cron()
        self.assertEqual(_errors, [])
        self.assertIn(LEGACY_DIST_GAV, self._uploaded())
        self.assertIn(LEGACY_NOTES_GAV, self._uploaded())
        self.assertIn((LEGACY_DIST_GAV, "LEGACYDSTR"), self.queue.enqueued)
        self.assertIn((LEGACY_NOTES_GAV, "RELEASENOTES"), self.queue.enqueued)

    def test_cron__registered_component_mirror_recovered(self):
        # the webhook registered new-comp, but the upload failed
        self.registry.citypedms["new-comp"] = {"dms_id": "new-comp", "ci_type_id": "new-comp"}
        _errors, _warnings = self._run_cron()
        self.assertEqual(_errors, [])
        self.assertIn(NEW_COMP_DIST_GAV, self._uploaded())
        self.assertIn((NEW_COMP_DIST_GAV, "new-comp"), self.queue.enqueued)

    def test_cron__unregistered_component_waits_for_next_release(self):
        # the webhook was missed: the cron doesn't register, the next release's webhook does
        _errors, _warnings = self._run_cron()
        self.assertEqual(_errors, [])
        self.assertEqual(self.registry.registered, [])
        self.assertNotIn(NEW_COMP_DIST_GAV, self._uploaded())

    def test_cron__archived_config_component_only_warns(self):
        _errors, _warnings = self._run_cron()
        self.assertEqual(_errors, [])
        self.assertEqual(len([_w for _w in _warnings if "[archived-comp] is in config.json but not in DMS" in _w]), 1)
        self.assertFalse([_gav for _gav in self._uploaded() if "archived" in _gav])

    def test_cron__test_component_skipped(self):
        # registered, so only the label keeps it from being mirrored
        self.registry.citypedms["sandbox"] = {"dms_id": "sandbox", "ci_type_id": "sandbox"}
        _errors, _warnings = self._run_cron()
        self.assertEqual(_errors, [])
        self.assertFalse([_gav for _gav in self._uploaded() if "sandbox" in _gav])

    def test_cron__versions_limit(self):
        # with a limit of 1 only the newest version is processed, 4.3.9 is never looked at
        self.nexus.gavs = set()
        _errors, _warnings = self._run_cron("--versions-limit", "1")
        self.assertEqual(_errors, [])
        self.assertIn(LEGACY_DIST_GAV, self._uploaded())
        self.assertFalse([_gav for _gav in self._uploaded() if ":4.3.9:" in _gav])

    def test_cron__missing_artifact_skipped(self):
        # legacy-comp 4.3.10 notes are listed in DMS but their file is not in storage
        self.dms.missing_files.add(4)
        _errors, _warnings = self._run_cron()
        self.assertEqual(_errors, [])
        self.assertIn(LEGACY_DIST_GAV, self._uploaded())
        self.assertNotIn(LEGACY_NOTES_GAV, self._uploaded())
        self.assertIn((LEGACY_DIST_GAV, "LEGACYDSTR"), self.queue.enqueued)
        self.assertNotIn(LEGACY_NOTES_GAV, [_gav for _gav, _ci_type in self.queue.enqueued])
        self.assertEqual(len([_w for _w in _warnings if "Artifact not found in DMS storage, skipping" in _w
                              and "[4] was not found in any of the repositories" in _w]), 1)

    def test_webhook__missing_artifact_skipped(self):
        self.dms.missing_files.add(4)
        self.assertEqual(self._run_webhook("legacy-comp", "4.3.10"), (200, "Success"))
        self.assertEqual(self.nexus.uploaded, [(LEGACY_DIST_GAV, UPLOAD_REPO, b"legacy-comp:4.3.10:3")])
        self.assertEqual(self.queue.enqueued, [(LEGACY_DIST_GAV, "LEGACYDSTR")])

    def test_cron__dms_server_error_on_download_skipped(self):
        # DMS answers 500 for the legacy-comp 4.3.10 notes download
        self.dms.failing_files.add(4)
        _errors, _warnings = self._run_cron()
        self.assertEqual(_errors, [])
        self.assertIn(LEGACY_DIST_GAV, self._uploaded())
        self.assertNotIn(LEGACY_NOTES_GAV, self._uploaded())
        self.assertNotIn(LEGACY_NOTES_GAV, [_gav for _gav, _ci_type in self.queue.enqueued])
        self.assertEqual(len([_w for _w in _warnings if "DMS failed to download [legacy-comp:notes:4.3.10] with [500]" in _w]), 1)

    def test_cron__dms_server_error_on_versions_skipped(self):
        # new-comp is registered, but DMS answers 500 for its version list
        self.registry.citypedms["new-comp"] = {"dms_id": "new-comp", "ci_type_id": "new-comp"}
        self.dms.failing_versions.add("new-comp")
        _errors, _warnings = self._run_cron()
        self.assertEqual(_errors, [])
        self.assertNotIn(NEW_COMP_DIST_GAV, self._uploaded())
        self.assertIn(LEGACY_DIST_GAV, self._uploaded())
        self.assertEqual(len([_w for _w in _warnings if "DMS failed to list the versions of [new-comp] with [500]" in _w]), 1)

    def test_webhook__dms_server_error_on_download_skipped(self):
        self.dms.failing_files.add(4)
        self.assertEqual(self._run_webhook("legacy-comp", "4.3.10"), (200, "Success"))
        self.assertEqual(self.queue.enqueued, [(LEGACY_DIST_GAV, "LEGACYDSTR")])
