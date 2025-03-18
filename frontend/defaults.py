import logging
import os

import frontend.custom.implementation as implementation

logger = logging.getLogger("gunicorn.error")

# Get environment variables and ensure required ones are set.
SOLR_HOST = os.getenv("SOLR_HOST")
if not SOLR_HOST:
    raise EnvironmentError("ERROR: SOLR_HOST environment variable not set")
SOLR_PORT = os.getenv("SOLR_PORT")
if not SOLR_PORT:
    raise EnvironmentError("ERROR: SOLR_PORT environment variable not set")

SOLR_URL = f"http://{SOLR_HOST}:{SOLR_PORT}"

INTERNAL_ERROR_STATUS_CODE = 500

try:
    from frontend.custom.implementation import DEFAULT_ROWS
    DEFAULT_ROWS = implementation.DEFAULT_ROWS
except ImportError:
    DEFAULT_ROWS = 20
