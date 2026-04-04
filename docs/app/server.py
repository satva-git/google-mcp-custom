from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP
from pydantic import Field
from typing import Annotated
import os

from .apis.documents import (
    get_document_as_markdown,
    create_document,
    insert_text,
    append_text,
    replace_all_text,
    delete_content_range,
    update_text_style,
    update_paragraph_style,
    insert_table,
    list_documents,
    batch_update,
    export_document,
)
from fastmcp.server.dependencies import get_http_headers
from .apis.helper import get_client
from googleapiclient.errors import HttpError
from fastmcp.exceptions import ToolError


# Configure server-specific settings
PORT = int(os.getenv("PORT", 9000))
MCP_PATH = os.getenv("MCP_PATH", "/mcp/google-docs")

mcp = FastMCP(
    name="GoogleDocsMCPServer",
    on_duplicate_tools="error",
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request):
    return JSONResponse({"status": "healthy"})


def _get_access_token() -> str:
    headers = get_http_headers()
    access_token = headers.get("x-forwarded-access-token", None)
    if not access_token:
        raise ToolError("No access token found in headers")
    return access_token


@mcp.tool(
    name="list_documents",
    annotations={
        "readOnlyHint": True,
    },
)
def list_documents_tool(
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of documents to return",
            ge=1,
            le=100,
            default=20,
        ),
    ] = 20,
    page_token: Annotated[
        str | None,
        Field(
            description="Token for pagination, pass the nextPageToken from the previous response to get the next page."
        ),
    ] = None,
    file_name_contains: Annotated[
        str | None,
        Field(
            description="Case-insensitive search string to filter documents by name."
        ),
    ] = None,
) -> dict:
    """
    List Google Docs documents in the user's Google Drive. Returns a list of documents and a nextPageToken for pagination.
    """
    try:
        token = _get_access_token()
        drive_client = get_client(token, service_name="drive", version="v3")
        result = list_documents(
            drive_client,
            max_results=max_results,
            page_token=page_token,
            file_name_contains=file_name_contains,
        )
        return result
    except HttpError as error:
        raise ToolError(f"Failed to list documents, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="get_document",
    annotations={
        "readOnlyHint": True,
    },
)
def get_document_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document to retrieve")
    ],
) -> dict:
    """
    Get a Google Docs document and return its content as markdown. Returns the document title, markdown content, and revision ID.
    """
    try:
        client = get_client(_get_access_token())
        result = get_document_as_markdown(client, document_id)
        return result
    except HttpError as error:
        raise ToolError(f"Failed to get document, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="create_document",
)
def create_document_tool(
    title: Annotated[str, Field(description="Title for the new document")],
    initial_content: Annotated[
        str | None,
        Field(
            description="Optional initial text content to insert into the document."
        ),
    ] = None,
) -> dict:
    """
    Create a new Google Docs document. Optionally insert initial text content.
    """
    try:
        client = get_client(_get_access_token())
        result = create_document(client, title)
        if initial_content:
            insert_text(client, result["document_id"], initial_content, 1)
        return result
    except HttpError as error:
        raise ToolError(f"Failed to create document, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="insert_text",
)
def insert_text_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document")
    ],
    text: Annotated[str, Field(description="Text to insert")],
    index: Annotated[
        int,
        Field(
            description="The character index to insert text at. Index 1 is the beginning of the document body.",
            ge=1,
        ),
    ],
) -> dict:
    """
    Insert text at a specific position in a Google Docs document.
    """
    try:
        client = get_client(_get_access_token())
        result = insert_text(client, document_id, text, index)
        return result
    except HttpError as error:
        raise ToolError(f"Failed to insert text, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="append_text",
)
def append_text_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document")
    ],
    text: Annotated[str, Field(description="Text to append to the end of the document")],
) -> dict:
    """
    Append text to the end of a Google Docs document.
    """
    try:
        client = get_client(_get_access_token())
        result = append_text(client, document_id, text)
        return result
    except HttpError as error:
        raise ToolError(f"Failed to append text, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="replace_text",
)
def replace_text_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document")
    ],
    find_text: Annotated[str, Field(description="Text to find in the document")],
    replace_text: Annotated[str, Field(description="Text to replace with")],
    match_case: Annotated[
        bool,
        Field(description="Whether the search is case-sensitive", default=True),
    ] = True,
) -> dict:
    """
    Replace all occurrences of a text string in a Google Docs document.
    """
    try:
        client = get_client(_get_access_token())
        result = replace_all_text(
            client, document_id, find_text, replace_text, match_case
        )
        return result
    except HttpError as error:
        raise ToolError(f"Failed to replace text, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="delete_content",
)
def delete_content_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document")
    ],
    start_index: Annotated[
        int, Field(description="Start index of the content range to delete", ge=1)
    ],
    end_index: Annotated[
        int, Field(description="End index of the content range to delete", ge=2)
    ],
) -> dict:
    """
    Delete content within a range in a Google Docs document.
    """
    try:
        client = get_client(_get_access_token())
        result = delete_content_range(client, document_id, start_index, end_index)
        return result
    except HttpError as error:
        raise ToolError(f"Failed to delete content, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="format_text",
)
def format_text_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document")
    ],
    start_index: Annotated[
        int, Field(description="Start index of the text range to format", ge=1)
    ],
    end_index: Annotated[
        int, Field(description="End index of the text range to format", ge=2)
    ],
    bold: Annotated[
        bool | None, Field(description="Set bold formatting")
    ] = None,
    italic: Annotated[
        bool | None, Field(description="Set italic formatting")
    ] = None,
    underline: Annotated[
        bool | None, Field(description="Set underline formatting")
    ] = None,
    strikethrough: Annotated[
        bool | None, Field(description="Set strikethrough formatting")
    ] = None,
    font_size: Annotated[
        float | None, Field(description="Font size in points", gt=0)
    ] = None,
    font_family: Annotated[
        str | None,
        Field(description="Font family name (e.g., 'Arial', 'Times New Roman')"),
    ] = None,
) -> dict:
    """
    Format text in a Google Docs document. Specify only the formatting properties you want to change.
    """
    try:
        client = get_client(_get_access_token())
        result = update_text_style(
            client,
            document_id,
            start_index,
            end_index,
            bold=bold,
            italic=italic,
            underline=underline,
            strikethrough=strikethrough,
            font_size=font_size,
            font_family=font_family,
        )
        return result
    except HttpError as error:
        raise ToolError(f"Failed to format text, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="set_paragraph_style",
)
def set_paragraph_style_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document")
    ],
    start_index: Annotated[
        int, Field(description="Start index of the paragraph range", ge=1)
    ],
    end_index: Annotated[
        int, Field(description="End index of the paragraph range", ge=2)
    ],
    named_style_type: Annotated[
        str | None,
        Field(
            description="Named style type (e.g., 'HEADING_1', 'HEADING_2', 'NORMAL_TEXT', 'SUBTITLE', 'TITLE')"
        ),
    ] = None,
    alignment: Annotated[
        str | None,
        Field(
            description="Paragraph alignment (e.g., 'START', 'CENTER', 'END', 'JUSTIFIED')"
        ),
    ] = None,
) -> dict:
    """
    Set paragraph style in a Google Docs document. Specify a named style type and/or alignment.
    """
    try:
        client = get_client(_get_access_token())
        result = update_paragraph_style(
            client,
            document_id,
            start_index,
            end_index,
            named_style_type=named_style_type,
            alignment=alignment,
        )
        return result
    except HttpError as error:
        raise ToolError(f"Failed to set paragraph style, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="insert_table",
)
def insert_table_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document")
    ],
    rows: Annotated[
        int, Field(description="Number of rows in the table", ge=1, le=100)
    ],
    columns: Annotated[
        int, Field(description="Number of columns in the table", ge=1, le=20)
    ],
    index: Annotated[
        int,
        Field(
            description="The character index to insert the table at. Index 1 is the beginning of the document body.",
            ge=1,
        ),
    ],
) -> dict:
    """
    Insert a table at a specific position in a Google Docs document.
    """
    try:
        client = get_client(_get_access_token())
        result = insert_table(client, document_id, rows, columns, index)
        return result
    except HttpError as error:
        raise ToolError(f"Failed to insert table, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="batch_update_document",
)
def batch_update_document_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document")
    ],
    requests: Annotated[
        list[dict],
        Field(
            description="List of Google Docs API request objects. See https://developers.google.com/docs/api/reference/rest/v1/documents/batchUpdate for request format."
        ),
    ],
) -> dict:
    """
    Execute a batch update on a Google Docs document with raw API requests. Use this for advanced operations not covered by other tools.
    """
    try:
        client = get_client(_get_access_token())
        result = batch_update(client, document_id, requests)
        return result
    except HttpError as error:
        raise ToolError(f"Failed to batch update document, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(
    name="export_document",
    annotations={
        "readOnlyHint": True,
    },
)
def export_document_tool(
    document_id: Annotated[
        str, Field(description="ID of the Google Docs document to export")
    ],
    export_format: Annotated[
        str,
        Field(
            description="Export format: 'html' (includes images as base64), 'pdf', 'docx', 'txt', 'rtf', or 'epub'. Defaults to 'html'.",
            default="html",
        ),
    ] = "html",
) -> dict:
    """
    Export a Google Docs document in a specified format using the Drive API.
    Exporting as HTML preserves embedded images as base64 data URIs, making the
    output self-contained. This is useful for downloading document content with
    all images intact.
    """
    try:
        token = _get_access_token()
        drive_client = get_client(token, service_name="drive", version="v3")
        result = export_document(drive_client, document_id, export_format)
        return result
    except HttpError as error:
        raise ToolError(f"Failed to export document, HttpError: {error}") from error
    except ValueError as error:
        raise ToolError(str(error)) from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


def streamable_http_server():
    """Main entry point for the Google Docs MCP server."""
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=PORT,
        path=MCP_PATH,
    )


def stdio_server():
    """Main entry point for the Google Docs MCP server."""
    mcp.run()


if __name__ == "__main__":
    streamable_http_server()
