from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP
from pydantic import Field
from typing import Annotated
import os

from .apis.presentations import (
    list_presentations,
    get_presentation,
    get_presentation_text,
    get_slide,
    create_presentation,
    create_slide,
    delete_slide,
    insert_text,
    replace_all_text,
    insert_image,
    batch_update,
    export_presentation,
)
from fastmcp.server.dependencies import get_http_headers
from .apis.helper import get_client
from googleapiclient.errors import HttpError
from fastmcp.exceptions import ToolError


PORT = int(os.getenv("PORT", 9000))
MCP_PATH = os.getenv("MCP_PATH", "/mcp/google-slides")

mcp = FastMCP(
    name="GoogleSlidesMCPServer",
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


@mcp.tool(name="list_presentations", annotations={"readOnlyHint": True})
def list_presentations_tool(
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of presentations to return",
            ge=1, le=100, default=20,
        ),
    ] = 20,
    page_token: Annotated[
        str | None,
        Field(description="Token for pagination from a previous response."),
    ] = None,
    file_name_contains: Annotated[
        str | None,
        Field(description="Case-insensitive search string to filter presentations by name."),
    ] = None,
) -> dict:
    """List Google Slides presentations in the user's Drive."""
    try:
        token = _get_access_token()
        drive_client = get_client(token, service_name="drive", version="v3")
        return list_presentations(
            drive_client,
            max_results=max_results,
            page_token=page_token,
            file_name_contains=file_name_contains,
        )
    except HttpError as error:
        raise ToolError(f"Failed to list presentations, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="get_presentation", annotations={"readOnlyHint": True})
def get_presentation_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
) -> dict:
    """Get a presentation's metadata and a per-slide summary (objectId, element count, text preview)."""
    try:
        client = get_client(_get_access_token())
        return get_presentation(client, presentation_id)
    except HttpError as error:
        raise ToolError(f"Failed to get presentation, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="get_presentation_text", annotations={"readOnlyHint": True})
def get_presentation_text_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
) -> dict:
    """Extract all text from a presentation as markdown, one section per slide."""
    try:
        client = get_client(_get_access_token())
        return get_presentation_text(client, presentation_id)
    except HttpError as error:
        raise ToolError(f"Failed to get presentation text, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="get_slide", annotations={"readOnlyHint": True})
def get_slide_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
    slide_object_id: Annotated[
        str, Field(description="objectId of the slide (page) to retrieve")
    ],
) -> dict:
    """Get the full element list of a single slide, plus extracted text."""
    try:
        client = get_client(_get_access_token())
        return get_slide(client, presentation_id, slide_object_id)
    except HttpError as error:
        raise ToolError(f"Failed to get slide, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="create_presentation")
def create_presentation_tool(
    title: Annotated[str, Field(description="Title for the new presentation")],
    initial_subtitle: Annotated[
        str | None,
        Field(
            description="Optional subtitle/body text for the auto-created title slide."
        ),
    ] = None,
) -> dict:
    """Create a new Google Slides presentation. Returns the new ID and edit link."""
    try:
        client = get_client(_get_access_token())
        return create_presentation(client, title, initial_subtitle)
    except HttpError as error:
        raise ToolError(f"Failed to create presentation, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="create_slide")
def create_slide_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
    layout: Annotated[
        str,
        Field(
            description=(
                "Predefined layout: BLANK, CAPTION_ONLY, TITLE, TITLE_AND_BODY, "
                "TITLE_AND_TWO_COLUMNS, TITLE_ONLY, SECTION_HEADER, "
                "SECTION_TITLE_AND_DESCRIPTION, ONE_COLUMN_TEXT, MAIN_POINT, BIG_NUMBER."
            ),
            default="BLANK",
        ),
    ] = "BLANK",
    insertion_index: Annotated[
        int | None,
        Field(
            description="0-based index to insert the slide at. Omit to append at the end.",
            ge=0,
        ),
    ] = None,
) -> dict:
    """Add a new slide to a presentation using a predefined layout."""
    try:
        client = get_client(_get_access_token())
        return create_slide(client, presentation_id, layout=layout, insertion_index=insertion_index)
    except HttpError as error:
        raise ToolError(f"Failed to create slide, HttpError: {error}") from error
    except ValueError as error:
        raise ToolError(str(error)) from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="delete_slide")
def delete_slide_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
    slide_object_id: Annotated[
        str, Field(description="objectId of the slide to delete")
    ],
) -> dict:
    """Delete a slide by its objectId."""
    try:
        client = get_client(_get_access_token())
        return delete_slide(client, presentation_id, slide_object_id)
    except HttpError as error:
        raise ToolError(f"Failed to delete slide, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="insert_text")
def insert_text_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
    object_id: Annotated[
        str,
        Field(
            description="objectId of the target shape, placeholder, or table cell."
        ),
    ],
    text: Annotated[str, Field(description="Text to insert")],
    insertion_index: Annotated[
        int,
        Field(
            description="Character index to insert at. 0 = beginning.", ge=0, default=0
        ),
    ] = 0,
) -> dict:
    """Insert text into a shape/placeholder/table cell on a slide."""
    try:
        client = get_client(_get_access_token())
        return insert_text(client, presentation_id, object_id, text, insertion_index)
    except HttpError as error:
        raise ToolError(f"Failed to insert text, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="replace_text")
def replace_text_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
    find_text: Annotated[str, Field(description="Text to find")],
    replace_text: Annotated[str, Field(description="Text to replace with")],
    match_case: Annotated[
        bool, Field(description="Case-sensitive search", default=True)
    ] = True,
) -> dict:
    """Replace all occurrences of text across the entire presentation."""
    try:
        client = get_client(_get_access_token())
        return replace_all_text(
            client, presentation_id, find_text, replace_text, match_case
        )
    except HttpError as error:
        raise ToolError(f"Failed to replace text, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="insert_image")
def insert_image_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
    slide_object_id: Annotated[
        str, Field(description="objectId of the target slide")
    ],
    image_url: Annotated[
        str,
        Field(
            description=(
                "Public HTTPS URL to the image. Must be reachable by Google's "
                "servers; max ~50 MB; PNG/JPEG/GIF."
            )
        ),
    ],
    width_pt: Annotated[
        float, Field(description="Image width in points", gt=0, default=400.0)
    ] = 400.0,
    height_pt: Annotated[
        float, Field(description="Image height in points", gt=0, default=300.0)
    ] = 300.0,
    translate_x_pt: Annotated[
        float, Field(description="X offset from slide origin in points", default=50.0)
    ] = 50.0,
    translate_y_pt: Annotated[
        float, Field(description="Y offset from slide origin in points", default=50.0)
    ] = 50.0,
) -> dict:
    """Insert an image from a public URL onto a slide."""
    try:
        client = get_client(_get_access_token())
        return insert_image(
            client,
            presentation_id,
            slide_object_id,
            image_url,
            width_pt=width_pt,
            height_pt=height_pt,
            translate_x_pt=translate_x_pt,
            translate_y_pt=translate_y_pt,
        )
    except HttpError as error:
        raise ToolError(f"Failed to insert image, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="batch_update_presentation")
def batch_update_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation")
    ],
    requests: Annotated[
        list[dict],
        Field(
            description=(
                "Raw Google Slides API request objects. See "
                "https://developers.google.com/slides/api/reference/rest/v1/presentations/request"
            )
        ),
    ],
) -> dict:
    """Execute a batch update with raw Slides API requests. Use for advanced operations not covered by other tools."""
    try:
        client = get_client(_get_access_token())
        return batch_update(client, presentation_id, requests)
    except HttpError as error:
        raise ToolError(f"Failed to batch update presentation, HttpError: {error}") from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


@mcp.tool(name="export_presentation", annotations={"readOnlyHint": True})
def export_presentation_tool(
    presentation_id: Annotated[
        str, Field(description="ID of the Google Slides presentation to export")
    ],
    export_format: Annotated[
        str,
        Field(
            description="Export format: 'pdf', 'pptx', 'txt', or 'odp'. Defaults to 'pdf'.",
            default="pdf",
        ),
    ] = "pdf",
) -> dict:
    """Export a Google Slides presentation in a specified format via the Drive API.

    Binary formats (pdf/pptx/odp) are returned as base64; txt is returned as plain text.
    """
    try:
        token = _get_access_token()
        drive_client = get_client(token, service_name="drive", version="v3")
        return export_presentation(drive_client, presentation_id, export_format)
    except HttpError as error:
        raise ToolError(f"Failed to export presentation, HttpError: {error}") from error
    except ValueError as error:
        raise ToolError(str(error)) from error
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}") from error


def streamable_http_server():
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=PORT,
        path=MCP_PATH,
    )


def stdio_server():
    mcp.run()


if __name__ == "__main__":
    streamable_http_server()
