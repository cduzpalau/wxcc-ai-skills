---
name: desktop-layout-manager
description: Manage and update the Webex Contact Center Agent Desktop Layout configuration and integrate custom widgets.
---

# Webex Contact Center Desktop Layout Manager Skill

This skill allows AI agents to get, update, and validate Webex Contact Center (WxCC) Agent Desktop layouts, specifically to insert custom widgets into the right panel tabs of the desktop interface.

---

## 📂 Skill Folder Structure
```text
skills/desktop-layout-manager/
├── SKILL.md                 # This instruction file
├── scripts/
│   └── update_layout.py     # Python script to list, fetch, insert, and push layouts
├── examples/
│   ├── tab-injection.json   # JSON snippet containing tab and tab-panel definitions
│   └── layout-sample.json   # A sample WxCC layout configuration
└── references/
    └── api-specs.md         # Reference list of layout API endpoints
```

---

## 🧭 Webex CC Layout Insertion Mechanics

To insert a custom widget in the **right panel tab layout**, you must inject two objects into the `"children"` array of the `"md-tabs"` component located under `"agent" -> "area" -> "panel"`.

### 1. The Tab Element (`md-tab`)
This defines the tab handle and title. It should be added to the children array:
```json
{
  "comp": "md-tab",
  "attributes": {
    "slot": "tab",
    "class": "widget-pane-tab"
  },
  "children": [
    {
      "comp": "span",
      "textContent": "My Widget"
    }
  ]
}
```

### 2. The Tab Panel Element (`md-tab-panel`)
This defines the tab body containing the web component widget. It must be added to the children array immediately following or corresponding to the `md-tab`:
```json
{
  "comp": "md-tab-panel",
  "attributes": {
    "slot": "panel",
    "class": "widget-pane"
  },
  "children": [
    {
      "comp": "my-custom-widget",
      "script": "https://cdn.example.com/widgets/my-custom-widget.js",
      "wrapper": {
        "title": "My Widget Title",
        "maximizeAreaName": "app-maximize-area"
      },
      "attributes": {
        "darkmode": "$STORE.app.darkMode"
      }
    }
  ]
}
```

---

## ⚙️ How to use the Python Script (`update_layout.py`)

The skill includes a standalone python script `update_layout.py` that interacts with the Webex Contact Center configuration API.

### Environment Setup
Create a `.env` file in the root of the project containing:
```env
WXCC_ORG_ID=your-tenant-org-id
WXCC_ACCESS_TOKEN=your-access-token
WXCC_API_BASE_URL=https://api.wxcc-us1.cisco.com
```

### Script Commands

#### 1. List Desktop Layouts
List all layouts configured in the WxCC tenant to obtain the target Layout ID:
```bash
python skills/desktop-layout-manager/scripts/update_layout.py list
```

#### 2. Download Layout JSON
Fetch a specific layout by ID and save its internal JSON structure to a local file:
```bash
python skills/desktop-layout-manager/scripts/update_layout.py get <layout_id> <output_file_path>
```

#### 3. Inject Widget JSON Programmatically
Inject a widget (tab and tab-panel) JSON snippet into a local layout JSON file:
```bash
python skills/desktop-layout-manager/scripts/update_layout.py insert <local_layout_path> <widget_snippet_path>
```

#### 4. Upload Layout JSON
Update the layout on Webex Contact Center by uploading the modified local JSON file:
```bash
python skills/desktop-layout-manager/scripts/update_layout.py update <layout_id> <local_layout_path>
```
This command automatically fetches the latest metadata (e.g., version, current headers) from WxCC to perform a safe `PUT` update.

---

## ⚠️ Troubleshooting & Best Practices

### 1. Manual Activation Requirement
In some tenants, the Desktop Layout API might return `200 OK` but **silently fail to persist** `jsonFileContent` changes if the layout has never been manually updated via the Management Portal.
*   **Symptom**: API update returns success, but a subsequent `GET` shows the old JSON content.
*   **Fix**: Log into the WxCC Management Portal, edit the layout description manually once, and click "Save". This "unlocks" the layout for API-driven content updates.

### 2. Side Navigation (Navigation Bar) Persistence
Updates to the `navigation` array (Side Nav) are extremely sensitive to structure.
*   **Avoid `useFlexLayout: true`**: This often causes "Update nav for responsive layout failed" errors in the Agent Desktop if `width` and `height` aren't perfectly specified for every child.
*   **Prefer Grid Layout**: For maximum compatibility, use the standard `layout` object with `areas` and `size`.
    ```json
    "page": {
      "id": "my-page",
      "widgets": { "comp1": { ... } },
      "layout": { "areas": [["comp1"]], "size": { "cols": [1], "rows": [1] } }
    }
    ```

### 3. Role Synchronization
A Desktop Layout contains separate sections for `agent`, `supervisor`, and `supervisorAgent`. Ensure you update all relevant sections if the widget should be visible to all users.

### 4. Verification Step
Always run a `GET` request or use the `list` command (checking the `lastUpdatedTime` or `description`) after an update to ensure the server actually persisted the changes.
