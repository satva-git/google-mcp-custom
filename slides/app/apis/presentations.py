from googleapiclient.discovery import Resource
from googleapiclient.http import MediaIoBaseDownload
from io import BytesIO
import base64
import uuid

from .helper import setup_logger

logger = setup_logger(__name__)


# Drive export MIME types supported by Slides
EXPORT_MIME_TYPES = {
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "odp": "application/vnd.oasis.opendocument.presentation",
}

# Predefined slide layouts. Custom layouts can be referenced via layoutId in batch_update.
PREDEFINED_LAYOUTS = {
    "BLANK",
    "CAPTION_ONLY",
    "TITLE",
    "TITLE_AND_BODY",
    "TITLE_AND_TWO_COLUMNS",
    "TITLE_ONLY",
    "SECTION_HEADER",
    "SECTION_TITLE_AND_DESCRIPTION",
    "ONE_COLUMN_TEXT",
    "MAIN_POINT",
    "BIG_NUMBER",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def list_presentations(
    drive_service: Resource,
    max_results: int = 20,
    page_token: str | None = None,
    file_name_contains: str | None = None,
) -> dict:
    """List Google Slides presentations via the Drive API."""
    params = {
        "q": "mimeType='application/vnd.google-apps.presentation'",
        "pageSize": max_results,
        "fields": "nextPageToken, files(id, name, modifiedTime, createdTime)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }

    if file_name_contains:
        escaped = file_name_contains.replace("'", "\\'")
        params["q"] += f" and name contains '{escaped}'"

    if page_token:
        params["pageToken"] = page_token

    response = drive_service.files().list(**params).execute()
    return {
        "files": response.get("files", []),
        "nextPageToken": response.get("nextPageToken"),
    }


def _slide_text(slide: dict) -> str:
    """Extract concatenated text from all shapes/tables on a slide."""
    parts: list[str] = []
    for element in slide.get("pageElements", []):
        shape = element.get("shape")
        if shape:
            text = shape.get("text", {})
            for te in text.get("textElements", []):
                run = te.get("textRun")
                if run and run.get("content"):
                    parts.append(run["content"])
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    for te in cell.get("text", {}).get("textElements", []):
                        run = te.get("textRun")
                        if run and run.get("content"):
                            parts.append(run["content"])
    return "".join(parts)


def get_presentation(service: Resource, presentation_id: str) -> dict:
    """Return presentation metadata + a compact per-slide summary."""
    pres = service.presentations().get(presentationId=presentation_id).execute()
    slides_summary = []
    for idx, slide in enumerate(pres.get("slides", []), start=1):
        slides_summary.append(
            {
                "index": idx,
                "object_id": slide.get("objectId"),
                "layout_object_id": slide.get("slideProperties", {}).get(
                    "layoutObjectId"
                ),
                "element_count": len(slide.get("pageElements", [])),
                "text_preview": _slide_text(slide).strip()[:200],
            }
        )
    return {
        "presentation_id": pres.get("presentationId"),
        "title": pres.get("title"),
        "revision_id": pres.get("revisionId"),
        "slide_count": len(pres.get("slides", [])),
        "page_size": pres.get("pageSize"),
        "slides": slides_summary,
    }


def get_presentation_text(service: Resource, presentation_id: str) -> dict:
    """Extract all text from a presentation as markdown, one section per slide."""
    pres = service.presentations().get(presentationId=presentation_id).execute()
    parts: list[str] = [f"# {pres.get('title', '')}\n"]
    for idx, slide in enumerate(pres.get("slides", []), start=1):
        parts.append(f"\n## Slide {idx} (id: {slide.get('objectId')})\n")
        text = _slide_text(slide).strip()
        if text:
            parts.append(text)
            parts.append("\n")
        else:
            parts.append("_(no text)_\n")
    return {
        "presentation_id": pres.get("presentationId"),
        "title": pres.get("title"),
        "markdown_content": "".join(parts).rstrip(),
        "slide_count": len(pres.get("slides", [])),
    }


def get_slide(service: Resource, presentation_id: str, slide_object_id: str) -> dict:
    """Return a single slide's full element list."""
    page = (
        service.presentations()
        .pages()
        .get(presentationId=presentation_id, pageObjectId=slide_object_id)
        .execute()
    )
    return {
        "presentation_id": presentation_id,
        "slide": page,
        "text": _slide_text(page).strip(),
    }


def create_presentation(
    service: Resource, title: str, initial_subtitle: str | None = None
) -> dict:
    """Create a new Google Slides presentation. The first slide is auto-created with the title."""
    pres = service.presentations().create(body={"title": title}).execute()
    pres_id = pres.get("presentationId")

    # Optionally drop subtitle text into the auto-created title slide.
    if initial_subtitle and pres.get("slides"):
        first_slide = pres["slides"][0]
        # Find the first body/subtitle placeholder
        for el in first_slide.get("pageElements", []):
            shape = el.get("shape", {})
            ph = shape.get("placeholder", {})
            if ph.get("type") in ("SUBTITLE", "BODY"):
                requests = [
                    {
                        "insertText": {
                            "objectId": el["objectId"],
                            "text": initial_subtitle,
                            "insertionIndex": 0,
                        }
                    }
                ]
                batch_update(service, pres_id, requests)
                break

    return {
        "presentation_id": pres_id,
        "title": pres.get("title"),
        "presentation_link": f"https://docs.google.com/presentation/d/{pres_id}/edit",
    }


def batch_update(service: Resource, presentation_id: str, requests: list[dict]) -> dict:
    """Execute a batch update on a presentation."""
    return (
        service.presentations()
        .batchUpdate(presentationId=presentation_id, body={"requests": requests})
        .execute()
    )


def create_slide(
    service: Resource,
    presentation_id: str,
    layout: str = "BLANK",
    insertion_index: int | None = None,
) -> dict:
    """Append (or insert) a new slide using a predefined layout."""
    layout = layout.upper()
    if layout not in PREDEFINED_LAYOUTS:
        raise ValueError(
            f"Unknown layout '{layout}'. Supported: {sorted(PREDEFINED_LAYOUTS)}"
        )

    new_slide_id = _new_id("slide")
    create_req: dict = {
        "createSlide": {
            "objectId": new_slide_id,
            "slideLayoutReference": {"predefinedLayout": layout},
        }
    }
    if insertion_index is not None:
        create_req["createSlide"]["insertionIndex"] = insertion_index

    result = batch_update(service, presentation_id, [create_req])
    return {
        "presentation_id": presentation_id,
        "slide_object_id": new_slide_id,
        "layout": layout,
        "insertion_index": insertion_index,
        "raw": result,
    }


def delete_slide(
    service: Resource, presentation_id: str, slide_object_id: str
) -> dict:
    """Delete a slide by object ID."""
    requests = [{"deleteObject": {"objectId": slide_object_id}}]
    return batch_update(service, presentation_id, requests)


def insert_text(
    service: Resource,
    presentation_id: str,
    object_id: str,
    text: str,
    insertion_index: int = 0,
) -> dict:
    """Insert text into a shape, placeholder, or table cell by objectId."""
    requests = [
        {
            "insertText": {
                "objectId": object_id,
                "text": text,
                "insertionIndex": insertion_index,
            }
        }
    ]
    return batch_update(service, presentation_id, requests)


def replace_all_text(
    service: Resource,
    presentation_id: str,
    find: str,
    replace: str,
    match_case: bool = True,
) -> dict:
    """Replace all occurrences of text in a presentation."""
    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": find, "matchCase": match_case},
                "replaceText": replace,
            }
        }
    ]
    result = batch_update(service, presentation_id, requests)
    replies = result.get("replies", [{}])
    occurrences = replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    return {"occurrences_changed": occurrences}


def insert_image(
    service: Resource,
    presentation_id: str,
    slide_object_id: str,
    image_url: str,
    width_pt: float = 400.0,
    height_pt: float = 300.0,
    translate_x_pt: float = 50.0,
    translate_y_pt: float = 50.0,
) -> dict:
    """Insert an image from a publicly-accessible URL onto a slide.

    Coordinates are in points (1 pt = 1/72 inch). Default position is roughly
    upper-left of a standard slide.
    """
    image_id = _new_id("image")
    requests = [
        {
            "createImage": {
                "objectId": image_id,
                "url": image_url,
                "elementProperties": {
                    "pageObjectId": slide_object_id,
                    "size": {
                        "width": {"magnitude": width_pt, "unit": "PT"},
                        "height": {"magnitude": height_pt, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": translate_x_pt,
                        "translateY": translate_y_pt,
                        "unit": "PT",
                    },
                },
            }
        }
    ]
    result = batch_update(service, presentation_id, requests)
    return {
        "presentation_id": presentation_id,
        "image_object_id": image_id,
        "raw": result,
    }


def export_presentation(
    drive_service: Resource, presentation_id: str, export_format: str = "pdf"
) -> dict:
    """Export a Google Slides presentation in a specified format using the Drive API.

    Returns:
        dict with presentation_id, file_name, mime_type, and content (str for
        text formats, base64 for binary formats).
    """
    export_format = export_format.lower()
    mime_type = EXPORT_MIME_TYPES.get(export_format)
    if not mime_type:
        supported = ", ".join(EXPORT_MIME_TYPES.keys())
        raise ValueError(
            f"Unsupported export format '{export_format}'. Supported: {supported}"
        )

    file_meta = (
        drive_service.files()
        .get(fileId=presentation_id, fields="name", supportsAllDrives=True)
        .execute()
    )
    file_name = file_meta.get("name", presentation_id)

    request = drive_service.files().export_media(
        fileId=presentation_id, mimeType=mime_type
    )
    buf = BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    raw_bytes = buf.getvalue()

    if export_format == "txt":
        content = raw_bytes.decode("utf-8")
    else:
        content = base64.b64encode(raw_bytes).decode("ascii")

    return {
        "presentation_id": presentation_id,
        "file_name": f"{file_name}.{export_format}",
        "mime_type": mime_type,
        "export_format": export_format,
        "content": content,
        "size_bytes": len(raw_bytes),
    }
