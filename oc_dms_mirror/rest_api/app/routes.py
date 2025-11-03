import json

import structlog
from flask import Response, request, current_app, Blueprint
from oc_logging import setup_json_logging

from oc_dms_mirror.dms_mirror import DmsMirror

class DmsMirrorBlueprint:
    def __init__(self, name='dms_mirror'):
        self.bp = Blueprint(name, __name__)
        self._register_routes()

        setup_json_logging()
        self.logger = structlog.get_logger()

        self._dms_mirror = None

    def _register_routes(self):
        self.bp.route('/register-component-version-artifact', methods=['POST'])(self.register_component_version_artifact)
        self.bp.route('/get-gav', methods=['POST'])(self.generate_gav)
        self.bp.route('/healthcheck', methods=['GET'])(self.healthcheck)

    @property
    def dms_mirror(self):
        if not self._dms_mirror:
            self._dms_mirror = self.get_dms_mirror()

        return self._dms_mirror

    def get_dms_mirror(self):
        dms_mirror = DmsMirror()
        dms_mirror.setup_from_args(current_app.args)
        dms_mirror.load_config()
        return dms_mirror

    def response_json(self, code, data):
        """
        Return JSON data response
        :param int code: HTTP response code
        :param data: dict or list to send as response content
        """
        if not isinstance(data, str):
            data = json.dumps(data)

        return Response(
            status=code,
            mimetype='application/json',
            content_type='application/json',
            response=data)

    def register_component_version_artifact(self):
        """
        Endpoint performing component/version sync with DMS on demand.
        """
        self.logger.info(f"POST {request.url_rule.rule} from [{request.remote_addr}] with payload: {request.get_json()}")
        try:
            self.dms_mirror.process_component_webhook(request.get_json())
        except Exception as _e:
            self.logger.error(str(_e))
            return self.response_json(400, {"result": str(_e)})

        return self.response_json(200, {"result": "Success"})

    def generate_gav(self):
        """
        Endpoint for getting or generating GAV Template.
        """
        self.logger.info(f"POST {request.url_rule.rule} from [{request.remote_addr}] with payload: {request.get_json()}")
        try:
            component = request.json.get('componentId')
            if not component:
                return self.response_json(400, {"result": "componentId cannot be blank"})

            gav_template = self.dms_mirror.get_component_config(component)
            if not gav_template:
                return self.response_json(404, {"result": f"gav template for component {component} not found"})
        except Exception as _e:
            self.logger.error(str(_e))
            return self.response_json(400, {"result": str(_e)})

        return self.response_json(200, gav_template)

    def healthcheck(self):
        """
        Simple healthcheck endpoint.
        """
        self.logger.debug(f"GET {request.url_rule.rule} - OK")
        return self.response_json(200, {"status": "ok"})

    def get_blueprint(self):
        return self.bp