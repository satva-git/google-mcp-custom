from starlette.requests import Request
from starlette.responses import JSONResponse
from .apis.shared_drives import list_drives
from .apis.files import list_files
from fastmcp import FastMCP
from pydantic import Field
from typing import Annotated, Literal
import base64
import mimetypes
import os
from urllib.parse import unquote, urlparse

import httpx


# Import all the command functions
from .apis.files import (
    copy_file,
    create_file,
    get_file,
    update_file,
    delete_file,
    create_folder,
    download_file,
    upload_file,
)
from .apis.permissions import (
    list_permissions,
    get_permission,
    create_permission,
    update_permission,
    delete_permission,
    transfer_ownership,
)
from .apis.shared_drives import create_drive, update_drive, delete_drive
from fastmcp.server.dependencies import get_http_headers
from markitdown import MarkItDown, StreamInfo, DocumentConverterResult
from io import BytesIO
from .apis.helper import get_client
from googleapiclient.errors import HttpError
from fastmcp.exceptions import ToolError


# Configure server-specific settings
PORT = int(os.getenv("PORT", 9000))
MCP_PATH = os.getenv("MCP_PATH", "/mcp/google-drive")
GOOGLE_OAUTH_TOKEN = os.getenv("GOOGLE_OAUTH_TOKEN")

mcp = FastMCP(
    name="GoogleDriveMCPServer",
    on_duplicate_tools="error",  # Handle duplicate registrations
    on_duplicate_resources="warn",
    on_duplicate_prompts="replace",
    instructions="""Google Drive MCP server for file/folder management, sharing, and content reading.

## Uploading new files
Two upload tools are available to create a NEW Drive file from bytes:
  - `upload_file_from_b64(name, content_b64, content_type, parent_id?, description?)`
    — for content already in base64 (e.g. produced by another tool).
  - `upload_file_from_url(url, name?, content_type?, parent_id?, description?)`
    — fetches the URL and uploads in one step.
Both use resumable uploads and return `{file_id, web_view_link, web_content_link}`.

To then share the uploaded file via link, call:
    create_permission(file_id=<id>, role="reader", type="anyone")

Other file operations:
  - Create empty FOLDERS via `create_folder`.
  - Copy existing Drive files via `copy_file`.
  - Update metadata (name, parent) of existing files via `update_file`.
  - Read/export existing file contents via `read_file` / `export_file`.

## Sharing a file as a link (so a recipient can view it)
Once a file exists in Drive, make it shareable:
  1. Call `create_permission(file_id=<id>, role="reader", type="anyone")` for anyone-with-link access.
     Use `role="writer"` / `"commenter"` for stronger access; use `type="user"` + `email_address`
     to share with a specific person.
  2. Use `get_file(file_id)` to retrieve the `webViewLink` (or construct
     `https://drive.google.com/file/d/<file_id>/view`) and paste it into your email/message body.

This Drive-link flow is the supported way to "attach" a file to a Gmail send_email or
to a Basecamp message body when you want the recipient to view content rather than
embed it inline.
""",
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
    name="list_files",
    annotations={
        "readOnlyHint": True,
    },
)
def list_files_tool(
    drive_id: Annotated[
        str | None,
        Field(
            description="ID of the Google Drive to list files from. If unset, default to the user's personal drive."
        ),
    ] = None,
    parent_id: Annotated[
        str | None,
        Field(
            description="ID of the parent folder to list files from. If unset, default to the root folder of user's personal drive."
        ),
    ] = None,
    mime_type: Annotated[
        str | None,
        Field(
            description="Filter files by MIME type (e.g., 'application/pdf' for PDFs, 'image/jpeg' for JPEG images, 'application/vnd.google-apps.folder' for folders). If unset, returns all file types."
        ),
    ] = None,
    file_name_contains: Annotated[
        str | None,
        Field(
            description="Case-insensitive search string to filter files by name. Returns files containing this string in their name."
        ),
    ] = None,
    modified_time_after: Annotated[
        str | None,
        Field(
            description="Return only files modified after this timestamp (RFC 3339 format: YYYY-MM-DDTHH:MM:SSZ, e.g., '2024-03-20T10:00:00Z')."
        ),
    ] = None,
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of files to return", ge=1, le=1000, default=50
        ),
    ] = 50,
) -> list[dict]:
    """
    List or search for files in the user's Google Drive. Returns up to 50 files by default, sorted by last modified date.
    """
    try:
        client = get_client(_get_access_token())
        files = list_files(
            client,
            drive_id=drive_id,
            parent_id=parent_id,
            mime_type=mime_type,
            file_name_contains=file_name_contains,
            modified_time_after=modified_time_after,
            max_results=max_results,
            trashed=False,
        )

        return files
    except HttpError as error:
        raise ToolError(f"Failed to list files, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="copy_file",
)
def copy_file_tool(
    file_id: Annotated[str, Field(description="ID of the file to copy")],
    new_name: Annotated[
        str | None,
        Field(
            description='New name for the copied file. If not provided, the copied file will be named "Copy of [original name]".'
        ),
    ] = None,
    new_parent_id: Annotated[
        str | None,
        Field(
            description="New parent folder ID for the copied file. Provide this if you want to have the copied file in a different folder."
        ),
    ] = None,
) -> dict:
    """
    Create a copy of a Google Drive file.
    """
    try:
        client = get_client(_get_access_token())
        file = copy_file(
            client, file_id=file_id, new_name=new_name, parent_id=new_parent_id
        )
        return file
    except HttpError as error:
        raise ToolError(f"Failed to copy file, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="get_file",
    annotations={
        "readOnlyHint": True,
    },
)
def get_file_tool(
    file_id: Annotated[str, Field(description="ID of the file to get")],
) -> dict:
    """
    Get a Google Drive file from user's Google Drive
    """
    try:
        client = get_client(_get_access_token())
        file = get_file(client, file_id)
        return file
    except HttpError as error:
        raise ToolError(f"Failed to get file, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="update_file",
)
def update_file_tool(
    file_id: Annotated[str, Field(description="ID of the file or folder to update")],
    new_name: Annotated[
        str | None, Field(description="New name for the file or folder")
    ] = None,
    new_parent_id: Annotated[
        str | None,
        Field(
            description="New parent folder ID. Provide this if you want to move the item to a different folder, use `root` to move to the root folder."
        ),
    ] = None,
    # new_workspace_file_path: Annotated[str, Field(description="Path to the new content of the file (not applicable for folders)")] = None,
) -> dict:
    """
    Update an existing file or folder in user's Google Drive. Can rename and/or move to a different location.
    """
    try:
        client = get_client(_get_access_token())

        mime_type = None
        new_content = None

        file = update_file(
            client,
            file_id=file_id,
            new_name=new_name,
            new_content=new_content,
            mime_type=mime_type,
            new_parent_id=new_parent_id,
        )
        return file
    except HttpError as error:
        raise ToolError(f"Failed to update file, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="create_folder",
)
def create_folder_tool(
    folder_name: Annotated[str, Field(description="Name of the new folder")],
    parent_id: Annotated[
        str | None,
        Field(
            description="ID of the parent folder for the new folder. If not provided, the folder will be created in the root folder."
        ),
    ] = None,
) -> dict:
    """
    Create a new folder in user's Google Drive.
    """
    try:
        client = get_client(_get_access_token())
        folder = create_folder(client, name=folder_name, parent_id=parent_id)
        return folder
    except HttpError as error:
        raise ToolError(f"Failed to create folder, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="delete_file",
)
def delete_file_tool(
    file_id: Annotated[str, Field(description="ID of the file or folder to delete")],
) -> str:
    """
    Delete an existing file or folder from user's Google Drive
    ALWAYS ask for user's confirmation before proceeding this tool.
    """
    try:
        client = get_client(_get_access_token())
        success = delete_file(client, file_id)
        if success:
            return f"Successfully deleted file: {file_id}"
        else:
            return f"Failed to delete file: {file_id}"
    except HttpError as error:
        raise ToolError(f"Failed to delete file, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="transfer_ownership",
)
def transfer_ownership_tool(
    file_id: Annotated[
        str, Field(description="ID of the file to transfer ownership of")
    ],
    new_owner_email: Annotated[
        str, Field(description="Email address of the new owner")
    ],
) -> dict:
    """
    Transfer ownership of a Google Drive file to another user. Can only transfer ownership to a user in the same domain.
    """
    try:
        client = get_client(_get_access_token())
        permission = transfer_ownership(client, file_id, new_owner_email)
        return permission
    except HttpError as error:
        raise ToolError(f"Failed to transfer ownership, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="list_permissions",
    annotations={
        "readOnlyHint": True,
    },
)
def list_permissions_tool(
    file_id: Annotated[
        str,
        Field(
            description="ID of the file, folder, or shared drive to list permissions for"
        ),
    ],
) -> list[dict]:
    """
    List all permissions for a Google Drive file, folder, or shared drive.
    """
    try:
        client = get_client(_get_access_token())
        permissions = list_permissions(client, file_id)
        return permissions
    except HttpError as error:
        raise ToolError(f"Failed to list permissions, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="get_permission",
    annotations={
        "readOnlyHint": True,
    },
)
def get_permission_tool(
    file_id: Annotated[
        str,
        Field(
            description="ID of the file, folder, or shared drive to get permission for"
        ),
    ],
    permission_id: Annotated[str, Field(description="ID of the permission to get")],
) -> dict:
    """
    Get a specific permission for a Google Drive file, folder, or shared drive.
    """
    try:
        client = get_client(_get_access_token())
        permission = get_permission(client, file_id, permission_id)
        return permission
    except HttpError as error:
        raise ToolError(f"Failed to get permission, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="create_permission",
)
def create_permission_tool(
    file_id: Annotated[
        str,
        Field(
            description="ID of the file, folder, or shared drive to create permission for"
        ),
    ],
    role: Annotated[
        Literal["owner", "organizer", "fileOrganizer", "writer", "commenter", "reader"],
        Field(
            description="Role for the new permission, must be one of [owner(for My Drive), organizer(for shared drive), fileOrganizer(for shared drive), writer, commenter, reader]"
        ),
    ],
    type: Annotated[
        Literal["user", "group", "domain", "anyone"],
        Field(
            description="Type of the new permission, must be one of [user, group, domain, anyone]"
        ),
    ],
    email_address: Annotated[
        str | None,
        Field(
            description="Email address for user/group permission, required if type is user or group"
        ),
    ] = None,
    domain: Annotated[
        str | None,
        Field(description="Domain for domain permission, required if type is domain"),
    ] = None,
) -> dict:
    """
    Create a new permission for a Google Drive file, folder, or shared drive.

    Common patterns:
      - Anyone-with-link can view: role="reader", type="anyone".
      - Anyone-with-link can edit: role="writer", type="anyone".
      - Share with one person: role="reader"|"writer"|"commenter", type="user", email_address="...".
      - Share with a Google Group: type="group", email_address="group@domain".
      - Share with a domain: type="domain", domain="example.com".

    To share a Drive file in a Gmail message or Basecamp post, call this with
    type="anyone" + role="reader" first, then paste the file's webViewLink
    (from get_file) into the message body.
    """
    try:
        client = get_client(_get_access_token())

        if type in ["user", "group"] and not email_address:
            raise ToolError("EMAIL_ADDRESS is required for user/group permission")
        if type == "domain" and not domain:
            raise ToolError("DOMAIN is required for domain permission")

        permission = create_permission(
            client,
            file_id=file_id,
            role=role,
            type=type,
            email_address=email_address,
            domain=domain,
        )
        return permission
    except HttpError as error:
        raise ToolError(f"Failed to create permission, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="update_permission",
)
def update_permission_tool(
    file_id: Annotated[
        str,
        Field(
            description="ID of the file, folder, or shared drive to update permission for"
        ),
    ],
    permission_id: Annotated[str, Field(description="ID of the permission to update")],
    role: Annotated[
        str,
        Field(
            description="New role for the permission, must be one of [owner(for My Drive), organizer(for shared drive), fileOrganizer(for shared drive), writer, commenter, reader]"
        ),
    ],
) -> dict:
    """
    Update an existing permission for a Google Drive file, folder, or shared drive.
    """
    try:
        client = get_client(_get_access_token())
        permission = update_permission(client, file_id, permission_id, role)
        return permission
    except HttpError as error:
        raise ToolError(f"Failed to update permission, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="delete_permission",
)
def delete_permission_tool(
    file_id: Annotated[
        str,
        Field(
            description="ID of the file, folder, or shared drive to delete permission from"
        ),
    ],
    permission_id: Annotated[str, Field(description="ID of the permission to delete")],
) -> dict:
    """
    Delete an existing permission for a Google Drive file, folder, or shared drive.
    ALWAYS ask for user's confirmation before proceeding this tool.
    """
    try:
        client = get_client(_get_access_token())
        success = delete_permission(client, file_id, permission_id)
        if success:
            return {"result": f"Successfully deleted permission: {permission_id}"}
        else:
            return {"result": f"Failed to delete permission: {permission_id}"}
    except HttpError as error:
        raise ToolError(f"Failed to delete permission, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="list_shared_drives",
    annotations={
        "readOnlyHint": True,
    },
)
def list_shared_drives() -> list[dict]:
    """
    List all shared Google Drives for the user.
    """

    client = get_client(_get_access_token())
    drives = list_drives(client)
    return drives


@mcp.tool(
    name="create_shared_drive",
)
def create_shared_drive_tool(
    drive_name: Annotated[str, Field(description="Name of the new shared drive")],
) -> dict:
    """
    Create a new shared Google Drive for the user
    """
    try:
        client = get_client(_get_access_token())
        drive = create_drive(client, drive_name)
        return drive
    except HttpError as error:
        raise ToolError(f"Failed to create shared drive, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="delete_shared_drive",
)
def delete_shared_drive_tool(
    drive_id: Annotated[str, Field(description="ID of the shared drive to delete")],
) -> dict:
    """
    Delete an existing shared Google Drive.
    ALWAYS ask for user's confirmation before proceeding this tool.
    """
    try:
        client = get_client(_get_access_token())
        delete_drive(client, drive_id)
        return {
            "success": True,
            "message": f"Successfully deleted shared drive: {drive_id}",
        }
    except HttpError as error:
        raise ToolError(f"Failed to delete shared drive, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="rename_shared_drive",
)
def update_shared_drive_tool(
    drive_id: Annotated[str, Field(description="ID of the shared drive to rename")],
    drive_name: Annotated[str, Field(description="New name for the shared drive")],
) -> dict:
    """
    Rename an existing shared Google Drive
    """
    try:
        client = get_client(_get_access_token())
        drive = update_drive(client, drive_id, drive_name)
        return drive
    except HttpError as error:
        raise ToolError(f"Failed to update shared drive, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="export_file",
    annotations={
        "readOnlyHint": True,
    },
)
def export_file_tool(
    file_id: Annotated[str, Field(description="ID of the Google Workspace file to export")],
    export_format: Annotated[
        str,
        Field(
            description="Export format. For Google Docs: 'html' (preserves images as base64), 'pdf', 'docx', 'txt', 'rtf', 'epub'. For Sheets: 'xlsx', 'pdf', 'csv'. For Slides: 'pdf', 'pptx'. Defaults to 'html'.",
            default="html",
        ),
    ] = "html",
) -> dict:
    """
    Export a Google Workspace file (Docs, Sheets, Slides) in a specified format.
    Exporting Google Docs as HTML preserves embedded images as base64 data URIs.
    This is useful for downloading documents with all images intact.
    """
    try:
        client = get_client(_get_access_token())
        content_bytes, file_name = download_file(client, file_id, export_format=export_format)

        # Text-based formats returned as string content
        text_formats = {"html", "txt", "rtf", "csv"}
        fmt = export_format.lower()
        if fmt in text_formats:
            content = content_bytes.decode("utf-8")
        else:
            import base64
            content = base64.b64encode(content_bytes).decode("ascii")

        return {
            "file_id": file_id,
            "file_name": file_name,
            "export_format": fmt,
            "content": content,
            "size_bytes": len(content_bytes),
        }
    except HttpError as error:
        raise ToolError(f"Failed to export file, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="read_file",
)
def read_file_tool(
    file_id: Annotated[str, Field(description="ID of the file to read")],
) -> DocumentConverterResult:
    """Read the content of a file in Google Drive. Files larger than 100MB will not be read."""
    try:
        client = get_client(_get_access_token())
        content, file_name = download_file(client, file_id)

        # Extract file extension, handling files without extensions
        if "." in file_name and not file_name.startswith("."):
            file_extension = file_name.split(".")[-1]
        else:
            file_extension = None
        md = MarkItDown(enable_plugins=False)
        if file_extension:
            return md.convert(
                BytesIO(content), stream_info=StreamInfo(extension=file_extension)
            )
        else:
            return md.convert(BytesIO(content))
    except HttpError as error:
        raise ToolError(f"Failed to read file, HttpError: {error}")
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


def _upload_response(file_obj: dict) -> dict:
    """Normalize Drive create() response to the documented shape."""
    return {
        "file_id": file_obj.get("id"),
        "name": file_obj.get("name"),
        "mime_type": file_obj.get("mimeType"),
        "parents": file_obj.get("parents", []),
        "size": file_obj.get("size"),
        "web_view_link": file_obj.get("webViewLink"),
        "web_content_link": file_obj.get("webContentLink"),
    }


@mcp.tool(
    name="upload_file_from_b64",
)
def upload_file_from_b64_tool(
    name: Annotated[
        str,
        Field(description="Filename for the new Drive file (e.g. 'report.pdf')."),
    ],
    content_b64: Annotated[
        str,
        Field(description="File bytes, encoded as standard base64."),
    ],
    content_type: Annotated[
        str,
        Field(
            description=(
                "MIME type of the file (e.g. 'application/pdf', 'image/png'). "
                "If you want to convert into a Google Doc, pass "
                "'application/vnd.google-apps.document' — Drive will convert."
            ),
        ),
    ],
    parent_id: Annotated[
        str | None,
        Field(
            description=(
                "Optional ID of the parent folder. Defaults to the root of the "
                "user's My Drive."
            ),
            default=None,
        ),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="Optional description stored on the Drive file.", default=None),
    ] = None,
) -> dict:
    """
    Upload bytes (provided as base64) to create a new file in the user's Google Drive.
    Uses a resumable upload, suitable for files larger than 5 MB.

    Returns: `{file_id, name, mime_type, parents, size, web_view_link, web_content_link}`.

    To then share this file via link, call
    `create_permission(file_id=<file_id>, role="reader", type="anyone")`.
    """
    try:
        try:
            file_bytes = base64.b64decode(content_b64)
        except Exception:
            file_bytes = base64.urlsafe_b64decode(content_b64)
        client = get_client(_get_access_token())
        result = upload_file(
            client,
            name=name,
            file_content=file_bytes,
            mime_type=content_type,
            parent_id=parent_id,
            description=description,
        )
        return _upload_response(result or {})
    except HttpError as error:
        raise ToolError(f"Failed to upload file, HttpError: {error}")
    except ToolError:
        raise
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


@mcp.tool(
    name="upload_file_from_url",
)
async def upload_file_from_url_tool(
    url: Annotated[
        str,
        Field(description="HTTP(S) URL of the file to fetch. Redirects are followed."),
    ],
    name: Annotated[
        str | None,
        Field(
            description=(
                "Filename to use in Drive. If not provided, derived from the URL "
                "path basename (URL-decoded)."
            ),
            default=None,
        ),
    ] = None,
    content_type: Annotated[
        str | None,
        Field(
            description=(
                "MIME type override. If not provided, taken from the response "
                "Content-Type header, falling back to a guess from filename."
            ),
            default=None,
        ),
    ] = None,
    parent_id: Annotated[
        str | None,
        Field(
            description="Optional ID of the parent folder.",
            default=None,
        ),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="Optional description stored on the Drive file.", default=None),
    ] = None,
) -> dict:
    """
    Fetch a file from a URL and upload it as a new file in the user's Google Drive.
    Uses a resumable upload.

    Returns: `{file_id, name, mime_type, parents, size, web_view_link, web_content_link}`.

    To then share this file via link, call
    `create_permission(file_id=<file_id>, role="reader", type="anyone")`.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as http_client:
            resp = await http_client.get(url)
            resp.raise_for_status()
            data = resp.content
            resp_ct = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip()
    except httpx.HTTPError as e:
        raise ToolError(f"Failed to fetch URL '{url}': {e}")

    final_name = name
    if not final_name:
        path = urlparse(url).path or ""
        base = unquote(path.rsplit("/", 1)[-1]) if path else ""
        final_name = base or "uploaded_file"

    final_ct = content_type or resp_ct or ""
    if not final_ct:
        guessed, _ = mimetypes.guess_type(final_name)
        final_ct = guessed or "application/octet-stream"

    try:
        client = get_client(_get_access_token())
        result = upload_file(
            client,
            name=final_name,
            file_content=data,
            mime_type=final_ct,
            parent_id=parent_id,
            description=description,
        )
        return _upload_response(result or {})
    except HttpError as error:
        raise ToolError(f"Failed to upload file, HttpError: {error}")
    except ToolError:
        raise
    except Exception as error:
        raise ToolError(f"Unexpected ToolError: {error}")


def streamable_http_server():
    """Main entry point for the Gmail MCP server."""
    mcp.run(
        transport="streamable-http",  # fixed to streamable-http
        host="0.0.0.0",
        port=PORT,
        path=MCP_PATH,
    )


def stdio_server():
    """Main entry point for the Gmail MCP server."""
    mcp.run()


if __name__ == "__main__":
    streamable_http_server()
