# Google Slides MCP Server

An MCP (Model Context Protocol) server for interacting with Google Slides. Provides tools for creating, reading, and editing Google Slides presentations.

## Features

- **List Presentations** — List Google Slides in the user's Drive with filtering and pagination
- **Get Presentation** — Retrieve presentation metadata and slide structure as a compact summary
- **Get Presentation Text** — Extract all text from a presentation, slide by slide, as markdown
- **Get Slide** — Retrieve a single slide's elements and text
- **Create Presentation** — Create new presentations with optional initial title slide content
- **Create Slide** — Append a new slide with a chosen layout (BLANK, TITLE, TITLE_AND_BODY, etc.)
- **Delete Slide** — Remove a slide by object ID
- **Insert Text** — Insert text into a shape or placeholder on a slide
- **Replace Text** — Find and replace text across the entire presentation
- **Insert Image** — Insert an image from a public URL onto a slide
- **Batch Update** — Execute raw Google Slides API batch update requests
- **Export Presentation** — Export as PDF, PPTX, TXT, or ODP via the Drive API

## API Scopes Required

- `https://www.googleapis.com/auth/presentations` — Full access to Google Slides
- `https://www.googleapis.com/auth/drive` — Listing & exporting via Drive

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `9000` | Server port |
| `MCP_PATH` | `/mcp/google-slides` | MCP endpoint path |
