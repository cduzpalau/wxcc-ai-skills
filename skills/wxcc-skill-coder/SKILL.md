---
name: wxcc-skill-coder
description: Scaffold, author, bundle, and test custom Agent Desktop Web Components using the Webex Contact Center Desktop SDK.
---

# Webex Contact Center Widget Coder Skill

This skill allows AI agents to scaffold, develop, compile, and troubleshoot custom agent widgets for the Webex Contact Center (WxCC) Agent Desktop.

---

## 📂 Skill Folder Structure
```text
skills/wxcc-skill-coder/
├── SKILL.md                 # This instruction file
├── scripts/
│   └── generate_widget.py   # Scaffolding CLI tool
├── examples/
│   ├── agent-status-widget.js    # Example subscribing to agent state change info
│   └── contact-events-widget.js  # Example listening to active call/chat tasks
└── references/
    └── sdk-reference.md     # Quick reference sheet for SDK modules and event listeners
```

---

## 🛠️ Scaffolding a New Widget

Use the `generate_widget.py` script to generate a new standalone widget project containing the dependencies, development server, and compilation configuration:

```bash
python skills/wxcc-skill-coder/scripts/generate_widget.py <widget-name>
```

This creates a new project directory at `src/widgets/<widget-name>` containing:
* `src/index.js`: SDK-initialized blank custom element code.
* `package.json`: Configured scripts and SDK dependencies.
* `webpack.config.js`: Webpack bundle config targeting a single output file.

---

## 📐 Widget Component Rules

When coding custom widgets, all AI agents and developers **must** adhere to these strict rules:

### 1. Style & DOM Isolation (Shadow DOM)
Always use an open Shadow DOM (`mode: 'open'`) to isolate your widget's styles from the parent Webex Contact Center layout:
```javascript
this.attachShadow({ mode: 'open' });
```

### 2. Robust Lifecycle Cleanup
To avoid memory leaks and ghost process execution, always unsubscribe from SDK event listeners inside the `disconnectedCallback`:
```javascript
disconnectedCallback() {
  Desktop.agentContact.removeAllEventListeners();
  Desktop.agentStateInfo.removeAllEventListeners();
}
```

### 3. Error Boundaries & Proper Initialization
For SDK version **2.0.0+**, you MUST use the asynchronous `init` method with two mandatory parameters. Never use the legacy synchronous init without arguments. Wrap this in a try-catch to display user-friendly error banners:
```javascript
try {
  await Desktop.config.init('my-widget', 'my-provider');
} catch (error) {
  this.showErrorBanner(`SDK Init Failed: ${error.message}`);
}
```

### 4. Versioned Logging & UI
Always include a `VERSION` constant in your widget and prefix all console logs with a consistent tag (e.g., `[widgetname_v1.0.1]`). Additionally, display the version number subtly in the UI. This ensures you and the user can instantly verify if the latest code has been successfully deployed and loaded by the browser.

---

## ⚡ State Management Best Practices

When programmatically changing agent states, adhere to these tenant-compatible patterns:

### 1. The "Available" Transition
Many WxCC tenants require an explicit `auxCodeIdArray` parameter even when going to "Available". Omitting it can cause `400 Bad Request` or `Invalid Agent SubStatus` errors.
```javascript
await Desktop.agentStateInfo.stateChange({
  state: "Available",
  auxCodeIdArray: "0" // Mandatory for many environments to clear sub-status
});
```

### 2. State Guarding
Always check the current state via `Desktop.agentStateInfo.latestData.status` before calling `stateChange()`. Redundant calls to the same state are a common cause of generic backend errors.

### 3. Granular Error Inspection
SDK errors often wrap the real backend reason in a nested `data` object. Always log `error.data` when a state change fails.
```javascript
try {
  await Desktop.agentStateInfo.stateChange({ ... });
} catch (error) {
  const detail = error.data?.message || error.message;
  console.error("State change failed:", detail, error.data);
}
```

---

## 🎨 Design & Styling Guidelines

To provide a premium and modern user experience (wowing the user at first glance):
1. **Curated Themes**: Implement sleek dark mode defaults or premium matching theme colors (e.g. HSL tailored, slate/teal palettes). Avoid browser default colors and borders.
2. **Typography**: Load elegant sans-serif fonts (e.g. Google Fonts Inter, Outfit, or standard system fonts `-apple-system, BlinkMacSystemFont`).
3. **Glassmorphism / Micro-animations**: Use subtle box shadows, backdrop-filter gradients, and transition hover states (`transition: all 0.2s ease`).

---

## ⚙️ How to Build and Serve the Widget

Navigate to the generated widget folder and run:

### 1. Install dependencies
```bash
npm install
```

### 2. Start local sandboxed dev server
```bash
npm run serve
```
This spins up a local server at `http://localhost:5000/`. Note that the SDK will not fully initialize in a standalone local browser tab, as it requires parent Agent Desktop window contexts.

### 3. Compile to single bundle
```bash
npm run build
```
This produces a minified, self-contained single Javascript file at `dist/<widget-name>.js`.

---

## 📘 Desktop Layout Integration Reference

Once compiled and uploaded to a static web server/CDN, insert the widget component using the `desktop-layout-manager` skill:

```json
{
  "comp": "my-custom-widget",
  "script": "https://cdn.example.com/widgets/my-custom-widget.js",
  "wrapper": {
    "title": "My Premium Widget"
  }
}
```
For more SDK information, read the [SDK Reference](file:///Users/cpalau/wodev/AI/WxCCWM/skills/wxcc-skill-coder/references/sdk-reference.md).
