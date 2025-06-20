import json
from flask import Response, request, current_app
from . import dms_mirror_bp
from oc_dms_mirror.dms_mirror import DmsMirror
import logging


def get_dms_mirror():
    _dmsMirror = DmsMirror()
    _dmsMirror.setup_from_args(current_app.args)
    _dmsMirror.load_config()
    return _dmsMirror


def response_json(code, data):
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


@dms_mirror_bp.route('/register-component-version-artifact', methods=['POST'])
def register_component_version_artifact():
    """
    Endpoint performing component/version sync with DMS on demand.
    """
    logging.info(f"POST {request.url_rule.rule} from [{request.remote_addr}] with payload: {request.get_json()}")
    try:
        get_dms_mirror().process_component_webhook(request.get_json())
    except Exception as _e:
        logging.exception(_e)
        return response_json(400, {"result": str(_e)})

    return response_json(200, {"result": "Success"})

@dms_mirror_bp.route('/get-gav', methods=['POST'])
def generate_gav():
    """
    Endpoint for getting or generating GAV Template.
    """
    logging.info(f"POST {request.url_rule.rule} from [{request.remote_addr}] with payload: {request.get_json()}")
    try:
        component = request.json.get('componentId')
        if not component:
            return response_json(400, {"result": "componentId cannot be blank"})

        gav_template = get_dms_mirror().get_component_config(component)
        if not gav_template:
            return response_json(404, {"result": f"gav template for component {component} not found"})
    except Exception as _e:
        logging.exception(_e)
        return response_json(400, {"result": str(_e)})

    return response_json(200, gav_template)
