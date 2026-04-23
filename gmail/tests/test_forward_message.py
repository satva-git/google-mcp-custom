import base64
from email import message_from_bytes
from unittest.mock import MagicMock

import pytest

from obot_gmail_mcp.apis.messages import build_forward_message


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")


def _make_service(source_message, attachment_data_by_id=None):
    """Build a mock Gmail service whose messages().get() returns `source_message`
    and attachments().get() returns the given id -> base64url dict."""
    attachment_data_by_id = attachment_data_by_id or {}
    service = MagicMock()

    get_exec = MagicMock()
    get_exec.execute.return_value = source_message
    service.users.return_value.messages.return_value.get.return_value = get_exec

    def attachments_get(userId, messageId, id):
        mock = MagicMock()
        mock.execute.return_value = {"data": attachment_data_by_id.get(id, "")}
        return mock

    service.users.return_value.messages.return_value.attachments.return_value.get.side_effect = attachments_get
    return service


def _decode_raw(body):
    raw_b = base64.urlsafe_b64decode(body["raw"].encode("utf-8"))
    return message_from_bytes(raw_b)


BASIC_SOURCE = {
    "id": "src1",
    "threadId": "thread1",
    "payload": {
        "headers": [
            {"name": "From", "value": "vendor@example.com"},
            {"name": "Date", "value": "Mon, 1 Jan 2024 10:00:00 -0500"},
            {"name": "Subject", "value": "Receipt #123"},
            {"name": "To", "value": "me@example.com"},
            {"name": "Message-ID", "value": "<abc@example.com>"},
        ],
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64url("<p>Thanks for your order</p>")}},
            {
                "mimeType": "application/pdf",
                "filename": "receipt.pdf",
                "body": {"attachmentId": "att1", "size": 10},
            },
        ],
    },
}


def test_forward_prefixes_subject_with_fwd():
    service = _make_service(BASIC_SOURCE, {"att1": _b64url("pdf-bytes")})
    body = build_forward_message(service, "src1", to="boss@example.com")
    msg = _decode_raw(body)
    assert msg["Subject"].startswith("Fwd:")
    assert "Receipt #123" in msg["Subject"]


def test_forward_preserves_attachments_when_enabled():
    service = _make_service(BASIC_SOURCE, {"att1": _b64url("pdf-bytes")})
    body = build_forward_message(service, "src1", to="boss@example.com", include_attachments=True)
    msg = _decode_raw(body)
    filenames = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert "receipt.pdf" in filenames


def test_forward_drops_attachments_when_disabled():
    service = _make_service(BASIC_SOURCE, {"att1": _b64url("pdf-bytes")})
    body = build_forward_message(service, "src1", to="boss@example.com", include_attachments=False)
    msg = _decode_raw(body)
    filenames = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert filenames == []


def test_forward_quotes_original_headers():
    service = _make_service(BASIC_SOURCE, {"att1": _b64url("pdf-bytes")})
    body = build_forward_message(service, "src1", to="boss@example.com")
    msg = _decode_raw(body)
    html = "".join(p.get_payload(decode=True).decode("utf-8", "ignore") for p in msg.walk() if p.get_content_type() == "text/html")
    assert "vendor@example.com" in html
    assert "Receipt #123" in html
    assert "Forwarded message" in html


def test_forward_prepends_additional_message():
    service = _make_service(BASIC_SOURCE, {"att1": _b64url("pdf-bytes")})
    body = build_forward_message(
        service, "src1", to="boss@example.com", additional_message="FYI — please file this."
    )
    msg = _decode_raw(body)
    html = "".join(p.get_payload(decode=True).decode("utf-8", "ignore") for p in msg.walk() if p.get_content_type() == "text/html")
    # The note must appear before the forwarded-message marker.
    note_pos = html.find("FYI")
    fwd_pos = html.find("Forwarded message")
    assert note_pos != -1 and fwd_pos != -1
    assert note_pos < fwd_pos


def test_forward_preserves_thread_id():
    service = _make_service(BASIC_SOURCE, {"att1": _b64url("pdf-bytes")})
    body = build_forward_message(service, "src1", to="boss@example.com")
    assert body.get("threadId") == "thread1"


def test_forward_cc_bcc_applied():
    service = _make_service(BASIC_SOURCE, {"att1": _b64url("pdf-bytes")})
    body = build_forward_message(
        service, "src1", to="boss@example.com", cc="cc@example.com", bcc="bcc@example.com"
    )
    msg = _decode_raw(body)
    assert msg["to"] == "boss@example.com"
    assert msg["cc"] == "cc@example.com"
    assert msg["bcc"] == "bcc@example.com"
