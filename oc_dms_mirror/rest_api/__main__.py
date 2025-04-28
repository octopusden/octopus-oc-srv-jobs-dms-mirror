if __name__ == "__main__":
    import argparse
    import logging
    from ..dms_mirror import DmsMirror
    from .application import StandaloneApplication

    _parser = argparse.ArgumentParser(description="Mirror artifacts from DMS to MVN", conflict_handler='resolve')
    DmsMirror().basic_args(_parser)
    _parser.add_argument("--ws-bind", dest="ws_bind", type=str, help="<host:port> WS binding",
                         default='0.0.0.0:5400')
    _parser.add_argument("--ws-timeout", dest="ws_timeout", type=str, help="WS response timeout", default=300)
    _parser.add_argument("--ws-workers", dest="ws_workers", type=int, help="Amount of WS workers", default=10)
    _args = _parser.parse_args()

    if hasattr(_args, "log_level"):
        logging.basicConfig(
            format="%(pathname)s: %(asctime)-15s: %(levelname)s: %(funcName)s: %(lineno)d: %(message)s",
            level=_args.log_level)
        logging.info(f"Logging level is set to {_args.log_level}")

    _options = {
        "bind": _args.ws_bind,
        "timeout": _args.ws_timeout,
        "workers": _args.ws_workers
    }
    StandaloneApplication("app", _options, _args).run()
