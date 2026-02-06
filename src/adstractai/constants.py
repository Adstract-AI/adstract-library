"""Constants for the Adstract AI SDK."""

import os

# BASE_URL = os.getenv("ADSTRACT_DEBUG_URL", "https://api.adstract.ai")
BASE_URL = os.getenv("ADSTRACT_DEBUG_URL", "http://127.0.0.1:8000")
AD_INJECTION_ENDPOINT = "/api/ad-injection/start/"

DEFAULT_TIMOUT_SECONDS = 10

DEFAULT_RETRIES = 0
MAX_RETRIES = 3

ENV_API_KEY_NAME = "ADSTRACT_API_KEY"

SDK_HEADER_NAME = "X-Adstract-SDK"
SDK_VERSION_HEADER_NAME = "X-Adstract-SDK-Version"
API_KEY_HEADER_NAME = "X-Adstract-API-Key"

SDK_NAME = "adstractai-python"
SDK_VERSION = "0.1.0"
