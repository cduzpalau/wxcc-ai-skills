# Webex Contact Center Desktop Layout API Reference

This file outlines the configuration API endpoints for listing, fetching, creating, and updating Webex CC Desktop Layouts.

---

## 🔑 Authentication
All requests require the following headers:
- `Authorization: Bearer <WXCC_ACCESS_TOKEN>`
- `Accept: application/json`

If creating/updating resources:
- `Content-Type: application/json`

The OAuth scopes required are typically:
- `cjp:config` or `cjp:config_write`

---

## 📡 Endpoints

### 1. List Desktop Layouts (v2)
Retrieve a summary list of layouts.
* **Method**: `GET`
* **URL**: `{WXCC_API_BASE_URL}/organization/{WXCC_ORG_ID}/v2/desktop-layout`
* **Notes**: The `jsonFileContent` field is omitted from the list view. To get the layout JSON, you must fetch by ID.

### 2. Get Specific Desktop Layout by ID (v1)
Retrieve full details of a layout including the raw JSON layout string.
* **Method**: `GET`
* **URL**: `{WXCC_API_BASE_URL}/organization/{WXCC_ORG_ID}/desktop-layout/{layout_id}`
* **Response Property**: `jsonFileContent` (Stringified JSON representation of the layout)

### 3. Create a Desktop Layout (v1)
Create a new custom layout.
* **Method**: `POST`
* **URL**: `{WXCC_API_BASE_URL}/organization/{WXCC_ORG_ID}/desktop-layout`
* **Payload (JSON DTO)**:
  ```json
  {
    "name": "My New Layout",
    "description": "Layout Description",
    "jsonFileName": "Desktop Layout.json",
    "jsonFileContent": "{\"agent\":...}",
    "global": false,
    "status": true,
    "teamIds": ["team-uuid-1"]
  }
  ```

### 4. Update an Existing Desktop Layout (v1)
Update an existing layout configuration.
* **Method**: `PUT`
* **URL**: `{WXCC_API_BASE_URL}/organization/{WXCC_ORG_ID}/desktop-layout/{layout_id}`
* **Payload**: Complete `DesktopLayoutDTO` object retrieved via GET, with modified `jsonFileContent` and matching `id` and `version` fields.
