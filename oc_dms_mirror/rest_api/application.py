from gunicorn.app.wsgiapp import WSGIApplication
from .app import create_app
from .config import Config

class StandaloneApplication(WSGIApplication):
    def __init__(self, app_uri, options=None, args={}):
        self.options = options or {}
        self.app_uri = app_uri
        self.args = args
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load_wsgiapp(self):
        return create_app(Config, self.args)
