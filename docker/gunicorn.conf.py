"""gunicorn settings: the production web server that runs Django inside the web container."""

import os

bind = "0.0.0.0:8000"  # only reachable on the private Docker network, through Nginx
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
timeout = 30
accesslog = "-"        # log requests to the container output
errorlog = "-"
# Nginx is the only client, so trust the X-Forwarded-* headers it sends.
forwarded_allow_ips = "*"
