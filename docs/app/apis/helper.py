import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from fastmcp.exceptions import ToolError
import logging


def setup_logger(name, tool_name: str = "Google Docs MCP Server"):
    """Setup a logger that writes to sys.stderr. Avoid adding duplicate handlers.

    Args:
        name (str): The name of the logger.

    Returns:
        logging.Logger: The logger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        stderr_handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            f"[{tool_name} Debugging Log]: %(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)

    return logger


logger = setup_logger(__name__)


def get_client(cred_token: str, service_name: str = "docs", version: str = "v1"):
    creds = Credentials(token=cred_token)
    try:
        service = build(serviceName=service_name, version=version, credentials=creds)
        return service
    except HttpError as err:
        raise ToolError(f"HttpError retrieving google {service_name} client: {err}")
