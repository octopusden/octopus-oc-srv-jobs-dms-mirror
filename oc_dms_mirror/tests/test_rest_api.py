import json

from ..rest_api.app import create_app
from .config import TestConfig
import unittest

# disable extra logging output
import logging
logging.getLogger().propagate = False
logging.getLogger().disabled = True


class RestApiTestSuite(unittest.TestCase):

    def create_app(self):
        app = create_app(TestConfig, {})
        app.config['TESTING'] = True
        app.config['DEBUG'] = False
        with app.app_context():
            self.test_client = app.test_client()

    def test_register_component_version_artifact_ok(self):
        with unittest.mock.patch('oc_dms_mirror.rest_api.app.routes.DmsMirrorBlueprint.get_dms_mirror') as _get_dms_mirror:
            _dmsMirror = unittest.mock.MagicMock()
            _dmsMirror.process_component_webhook = unittest.mock.MagicMock()
            _get_dms_mirror.return_value = _dmsMirror
            self.create_app()

            data = {
                "type": "register-component-version-artifact",
                "component": "my_component",
                "version": "my_version",
                "artifact": {}
            }
            response = self.test_client.post("/register-component-version-artifact", json=data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json.get('result'), 'Success')

            _dmsMirror.process_component_webhook.assert_called_once_with(data)

    def test_register_component_version_artifact_fail(self):
        with unittest.mock.patch('oc_dms_mirror.rest_api.app.routes.DmsMirrorBlueprint.get_dms_mirror') as _get_dms_mirror:
            _dmsMirror = unittest.mock.MagicMock()
            _dmsMirror.process_component_webhook = unittest.mock.MagicMock(side_effect=Exception('processing failed'))
            _get_dms_mirror.return_value = _dmsMirror
            self.create_app()

            data = {
                "type": "register-component-version-artifact",
                "component": "my_component",
                "version": "my_version",
                "artifact": {}
            }
            response = self.test_client.post("/register-component-version-artifact", json=data)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json.get('result'), 'processing failed')

            _dmsMirror.process_component_webhook.assert_called_once_with(data)

    def test_get_gav_ok(self):
        with unittest.mock.patch('oc_dms_mirror.rest_api.app.routes.DmsMirrorBlueprint.get_dms_mirror') as _get_dms_mirror:
            _dmsMirror = unittest.mock.MagicMock()
            _dmsMirror.get_dms_mirror = unittest.mock.MagicMock()

            mock_gav = {
                "test-component": {
                    "ci_type": "test-component",
                    "tgtGavTemplate": {
                        "notes": "\\$prefix.release_notes:test-component\\$c_hyphen:\\$v:\\$p",
                        "distribution": "\\$prefix.test-client.test-component:\\$n:\\$v:\\$p\\$c_colon",
                        "report": "\\$prefix.release_notes:test-component:\\$v:\\$p:\\$cl",
                        "documentation": "\\$prefix.documentation:test-component:$v:\\$p"
                    }
                }
            }
            _get_dms_mirror.return_value = _dmsMirror
            _dmsMirror.get_component_config.return_value = mock_gav

            self.create_app()

            data = {
                "componentId": "test-component",
                "clientCode": "test-client"
            }
            response = self.test_client.post("/get-gav", json=data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.data), mock_gav)

            _dmsMirror.get_component_config.assert_called_once_with("test-component")

    def test_generate_gav_without_component(self):
        with unittest.mock.patch('oc_dms_mirror.rest_api.app.routes.DmsMirrorBlueprint.get_dms_mirror') as _get_dms_mirror:
            _dmsMirror = unittest.mock.MagicMock()
            _dmsMirror.get_dms_mirror = unittest.mock.MagicMock()

            mock_gav = {
                "test-component": {
                    "ci_type": "test-component",
                    "tgtGavTemplate": {
                        "notes": "\\$prefix.release_notes:test-component\\$c_hyphen:\\$v:\\$p",
                        "distribution": "\\$prefix.test-component:\\$n:\\$v:\\$p\\$c_colon",
                        "report": "\\$prefix.release_notes:test-component:\\$v:\\$p:\\$cl",
                        "documentation": "\\$prefix.documentation:test-component:$v:\\$p"
                    }
                }
            }
            _get_dms_mirror.return_value = _dmsMirror
            _dmsMirror.get_dms_mirror.return_value = mock_gav

            self.create_app()

            data = {
                "clientCode": "test-component"
            }
            response = self.test_client.post("/get-gav", json=data)
            self.assertEqual(response.status_code, 400)