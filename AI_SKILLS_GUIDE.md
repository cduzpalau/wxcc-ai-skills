# Webex Contact Center AI Toolchain Guide

This workspace is equipped with a specialized toolchain consisting of three distinct AI skills. Together, they enable autonomous, end-to-end development, hosting, and deployment of Webex Contact Center (WxCC) Agent Desktop custom widgets.

---

## 1. Widget Coder (`wxcc-skill-coder`)
**Purpose**: Scaffolds, authors, bundles, and tests custom Agent Desktop Web Components using the Webex Contact Center Desktop SDK.

**How to Use**: 
Copy SampleWidgetCode folder from the repo to the root of your project folder
Instruct the AI to "Create a WxCC widget named [name]". It will use the `generate_widget.py` script to scaffold the boilerplate, then write standard Web Components (`mode: 'open'` Shadow DOM).

**Critical Best Practices Learned**:
* **SDK Initialization**: Must use the async `Desktop.config.init('widget-name', 'provider')` pattern for SDK v2.0+ wrapped in a try/catch.
* **Agent State Management**: When programmatically transitioning an agent to the `Available` state, you must pass `auxCodeIdArray: "0"` in the payload to properly clear any existing sub-statuses (e.g., `await Desktop.agentStateInfo.stateChange({ state: "Available", auxCodeIdArray: "0" })`).
* **Versioned Logging & UI**: All widgets must declare a `VERSION` constant. This version should be visibly rendered in the UI (e.g., bottom right) and prefixed to all `console.log` statements for easy deployment tracking.

---

## 2. GitHub Pages Publisher (`github-pages-publisher`)
**Purpose**: Automatically creates a GitHub repository, pushes the compiled widget code, and enables GitHub Pages to host the widget script publicly.

**How to Use**:
Instruct the AI to "Publish the widget to a GitHub repo named [repo-name]". It relies on the `publish_widget.py` script and requires `GITHUB_USERNAME` and a `GITHUB_TOKEN` (with `repo` scope) in your `.env` file.

**Critical Best Practices Learned**:
* **Idempotency**: The skill is designed to gracefully handle scenarios where the repository or GitHub Pages configuration already exists, allowing the AI to safely push incremental updates without crashing.
* **Build First**: The AI must run `npm run build` using Webpack *before* triggering this skill, as it expects a compiled `.js` bundle in the `dist/` directory.

---

## 3. Desktop Layout Manager (`desktop-layout-manager`)
**Purpose**: Fetches, modifies, and uploads WxCC Agent Desktop JSON layout configurations via the Cisco Webex Configuration API.

**How to Use**:
Instruct the AI to "Inject the widget into the desktop layout [Layout ID]". It uses the `update_layout.py` script to fetch the active JSON, patch the widget into the navigation or right panel, and `PUT` it back. It requires `WXCC_ORG_ID`, `WXCC_ACCESS_TOKEN`, and `WXCC_API_BASE_URL` in your `.env` file.

**Critical Best Practices Learned**:
* **The "Manual Unlock" Rule**: If a layout has never been edited in the WxCC Management Portal, the API will return `200 OK` but silently discard JSON changes. A human must manually edit the layout description in the Portal and click "Save" once to unlock API persistence.
* **Navigation Bar Configuration**: When adding a widget to the side navigation bar (`navigation` array), **avoid using `useFlexLayout: true`** on the page definition, as it requires highly specific widget width/height properties and often causes "responsive layout failed" errors. Instead, use standard Grid Layouts:
  ```json
  "layout": { "areas": [["comp1"]], "size": { "cols": [1], "rows": [1] } }
  ```
* **Role Sync**: Desktop Layouts have separate sections for `agent`, `supervisor`, and `supervisorAgent`. The skill ensures that widget injection spans all applicable roles so users aren't left out based on their permissions.

---

## Example: The "One-Shot" AI Prompt

To trigger this entire pipeline smoothly, you can provide an AI agent with a comprehensive prompt like this:

> *"Create a new WxCC widget named 'button-available-widget'. It needs a button that sets the agent state to 'Available'.*
