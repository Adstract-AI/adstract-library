"""Constants for the Adstract AI SDK."""

import os

BASE_URL = os.getenv("ADSTRACT_DEBUG_URL", "https://api.adstract.ai")
AD_INJECTION_ENDPOINT = "/api/ad-injection/start/"
AD_ACK_ENDPOINT = "/api/ad-ack/ad-ack/create/"

DEFAULT_TIMEOUT_SECONDS = 100

DEFAULT_RETRIES = 0
MAX_RETRIES = 1

# Ad analysis constants
DEFAULT_MAX_ADS = 1
DEFAULT_MAX_LATENCY = 1.0  # seconds
DEFAULT_ERROR_CODE = "06102025"

# Analytics constants
XML_TAG = "ADS"
PLAIN_TAG = "˼"
OVERLOADED_VALUE = 0.8

BOTTOM_PLACMENT_PERCENTAGE = 0.25
MIDDLE_PLACMENT_PERCENTAGE = 0.75

ENV_API_KEY_NAME = "ADSTRACT_API_KEY"

SDK_HEADER_NAME = "X-Adstract-SDK"
SDK_VERSION_HEADER_NAME = "X-Adstract-SDK-Version"
API_KEY_HEADER_NAME = "X-Adstract-API-Key"

SDK_NAME = "adstractai-python"
SDK_VERSION = "0.0.12"
SDK_TYPE = "web"

# Defaults
DEFAULT_NOT_IMPLEMENTED_VALUE = -1
DEFAULT_TRUE_VALUE = True
DEFAULT_FALSE_VALUE = False
