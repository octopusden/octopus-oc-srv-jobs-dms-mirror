from flask import Flask, Blueprint

from .routes import *

def register_blueprint_controller(app):
    dms_mirror_bluprint = DmsMirrorBlueprint()
    app.register_blueprint(dms_mirror_bluprint.get_blueprint())

def create_app(config_class, args):
    app = Flask(__name__)
    app.args = args
    app.config.from_object(config_class)
    register_blueprint_controller(app)
    return app
