from flask import Flask, Blueprint

dms_mirror_bp = Blueprint("dms_mirror_bp", __name__)
from .routes import *


def create_app(config_class, args):
    app = Flask(__name__)
    app.args = args
    app.config.from_object(config_class)
    app.register_blueprint(dms_mirror_bp)
    return app
