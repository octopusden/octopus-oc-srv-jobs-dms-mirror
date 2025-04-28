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
        with unittest.mock.patch('oc_dms_mirror.rest_api.app.routes.get_dms_mirror') as _get_dms_mirror:
            _dmsMirror = unittest.mock.MagicMock()
            _dmsMirror.process_version = unittest.mock.MagicMock()
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

            _dmsMirror.process_version.assert_called_once_with("my_version", "my_component")

    def test_register_component_version_artifact_fail(self):
        with unittest.mock.patch('oc_dms_mirror.rest_api.app.routes.get_dms_mirror') as _get_dms_mirror:
            _dmsMirror = unittest.mock.MagicMock()
            _dmsMirror.process_version = unittest.mock.MagicMock(side_effect=Exception('processing failed'))
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

            _dmsMirror.process_version.assert_called_once_with("my_version", "my_component")
