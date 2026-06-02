# Webex Contact Center Agent Desktop SDK Reference

This reference documents the modules, event listeners, methods, and patterns of the Webex Contact Center JavaScript SDK (`@wxcc-desktop/sdk`).

---

## 🚀 SDK Initialization

For version **2.0.0 or above**, you must initialize the SDK with two mandatory parameters: `widgetName` and `widgetProvider`.

```javascript
import { Desktop } from "@wxcc-desktop/sdk";

class MyCustomWidget extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.desktop = null;
  }

  connectedCallback() {
    this.render();
    this.initSDK();
  }

  async initSDK() {
    try {
      // SDK initialization (Mandatory for v2.0+)
      await Desktop.config.init('my-awesome-widget', 'my-provider');
      this.desktop = Desktop;
      
      // Expose to window for debugging
      window.Desktop = Desktop;
      
      console.log('✅ WxCC SDK Initialized successfully');
    } catch (error) {
      console.error('❌ SDK Initialization Failed:', error);
    }
  }
}
```

---

## 📂 SDK Sub-Modules

The `Desktop` object contains the following sub-modules:

| Sub-Module | Purpose | Examples |
| :--- | :--- | :--- |
| `Desktop.config` | Desktop environment configuration | `clientLocale` |
| `Desktop.agentStateInfo` | Listen and modify agent channel/sub-states | `latestData`, `stateChange()`, `addEventListener('updated')` |
| `Desktop.agentContact` | Listen to live calls, chats, emails, and tasks | `taskMap`, `addEventListener('eAgentContact')` |
| `Desktop.actions` | Retrieve tokens, fire notifications, execute actions | `getToken()`, `getTaskMap()`, `fireGeneralSilentNotification()` |
| `Desktop.i18n` | Desktop internationalization system | `createInstance()`, `createMixin()` |
| `Desktop.dialer` | Place outbound/campaign calls | `dial()` |
| `Desktop.screenpop` | Handle incoming CRM/URL pops | Screen pop events |

---

## ⚡ Asynchronous Events (Event Listeners)

Webex Desktop SDK fires events that can be listened to by subscribing on the respective sub-module. Always clean up listeners in the `disconnectedCallback` using `removeAllEventListeners()`.

### 1. Agent State Events (`Desktop.agentStateInfo`)

* **`updated`**: Emitted when any agent state information (e.g. idle codes, profile) is fetched or updated.
* **`eAgentChannelStateChanged`**: Emitted when the agent's channel state (Voice, Chat, Email) changes (e.g. Available, Idle).

```javascript
// Register listener
Desktop.agentStateInfo.addEventListener("eAgentChannelStateChanged", (eventData) => {
  console.log("Agent channel state changed:", eventData);
});

// Disconnect listener (cleanup)
disconnectedCallback() {
  Desktop.agentStateInfo.removeAllEventListeners();
}
```

### 2. Interaction & Call Events (`Desktop.agentContact`)

Subscribe to `Desktop.agentContact` to manage active contacts and calls:

* **`eAgentContact`**: Emitted when task metadata changes (hold, resume, wrap up).
* **`eAgentContactAssigned`**: Emitted when a task is accepted/assigned to the agent.
* **`eAgentOfferContact`**: Emitted when an incoming task is offered (ringing/incoming request).
* **`eAgentWrapup`**: Emitted when the task enters the wrap-up state.
* **`eAgentContactHeld`** / **`eAgentContactUnHeld`**: Emitted when call hold/resume occurs.
* **`eAgentConsultCreated`** / **`eAgentConsulting`** / **`eAgentConsultEnded`**: Consult state updates.

```javascript
Desktop.agentContact.addEventListener("eAgentContactAssigned", (event) => {
  console.log("New contact assigned:", event.data);
});
```

---

## ⚙️ Key Methods and Actions

### 1. Retrieve SSO Access Token
Retrieves the authentication token for SSO API calls.
```javascript
const accessToken = await Desktop.actions.getToken();
```

### 2. Retrieve Agent Profile / Configuration
```javascript
const latestData = Desktop.agentStateInfo.latestData;
// Returns details such as agent ID, name, email, dial number (dn), etc.
```

### 3. Change Agent State Programmatically
```javascript
// Transition agent state (e.g. to Idle with a specific reason code ID)
await Desktop.agentStateInfo.stateChange({
  state: "Idle",
  idleReasonCodeId: "your-idle-reason-code-id"
});
```

### 4. Fetch Wrap-up / Idle Codes
Use the API client to fetch paginated codes:
```javascript
const idleCodes = await Desktop.agentConfigJsApi.fetchPaginatedAuxCodes({
  workType: "IDLE_CODE",
  page: 0,
  pageSize: 100
});
```

### 5. Update Desktop Layout Panel Title
To change the title of the widget dynamically inside the desktop panel:
```javascript
const event = new CustomEvent("unique-id-to-update-title", {
  bubbles: true,
  detail: { title: "New Dynamic Title" }
});
window.dispatchEvent(event);
```
