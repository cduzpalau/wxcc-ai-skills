import { Desktop } from "@wxcc-desktop/sdk";

class AgentStatusWidget extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.agentState = {};
    this.idleCodes = [];
  }

  connectedCallback() {
    this.render();
    this.initSDK();
  }

  disconnectedCallback() {
    Desktop.agentStateInfo.removeAllEventListeners();
  }

  async initSDK() {
    try {
      await Desktop.config.init('agent-status-widget', 'magician');
      
      // Get initial data
      this.agentState = Desktop.agentStateInfo.latestData || {};
      
      // Listen to channel state changes
      Desktop.agentStateInfo.addEventListener("eAgentChannelStateChanged", (event) => {
        console.log("State change event:", event);
        this.agentState = Desktop.agentStateInfo.latestData || {};
        this.updateUI();
      });

      // Fetch idle auxiliary codes
      try {
        const response = await Desktop.agentConfigJsApi.fetchPaginatedAuxCodes({
          workType: "IDLE_CODE",
          page: 0,
          pageSize: 50
        });
        this.idleCodes = response.data || [];
      } catch (err) {
        console.error("Failed to fetch idle codes", err);
      }

      this.updateUI();
    } catch (error) {
      this.showError(error.message);
    }
  }

  async changeState(newState, reasonCodeId = null) {
    try {
      const payload = { state: newState };
      if (reasonCodeId) {
        payload.idleReasonCodeId = reasonCodeId;
      }
      await Desktop.agentStateInfo.stateChange(payload);
    } catch (error) {
      console.error("Failed to change state:", error);
      alert("Error changing state: " + error.message);
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: #fafafa;
          color: #333;
          border-radius: 8px;
        }
        .card {
          background: white;
          border-radius: 8px;
          padding: 16px;
          box-shadow: 0 2px 4px rgba(0,0,0,0.05);
          border: 1px solid #e0e0e0;
        }
        .status-badge {
          display: inline-block;
          padding: 4px 12px;
          border-radius: 12px;
          font-weight: bold;
          font-size: 14px;
          text-transform: uppercase;
        }
        .status-Available { background: #d4edda; color: #155724; }
        .status-Idle { background: #fff3cd; color: #856404; }
        .status-LoggedOut { background: #f8d7da; color: #721c24; }
        
        .controls {
          margin-top: 16px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        button {
          padding: 8px 12px;
          border: none;
          border-radius: 4px;
          background: #0076b6;
          color: white;
          cursor: pointer;
          font-weight: 500;
        }
        button:hover { background: #005a8c; }
        select {
          padding: 8px;
          border-radius: 4px;
          border: 1px solid #ccc;
        }
      </style>
      <div class="card">
        <h3>Agent State monitor</h3>
        <div id="info">Initializing agent profile...</div>
        <div class="controls" id="actions" style="display:none;">
          <button id="btn-avail">Go Available</button>
          <hr />
          <label>Go Idle Reason:</label>
          <select id="select-idle-reason">
            <option value="">Select reason...</option>
          </select>
          <button id="btn-idle">Go Idle</button>
        </div>
      </div>
    `;

    // Hook listeners
    this.shadowRoot.getElementById('btn-avail').addEventListener('click', () => this.changeState('Available'));
    this.shadowRoot.getElementById('btn-idle').addEventListener('click', () => {
      const reasonId = this.shadowRoot.getElementById('select-idle-reason').value;
      this.changeState('Idle', reasonId || null);
    });
  }

  updateUI() {
    const infoEl = this.shadowRoot.getElementById('info');
    const actionsEl = this.shadowRoot.getElementById('actions');
    const selectEl = this.shadowRoot.getElementById('select-idle-reason');

    if (!this.agentState.agentName) {
      infoEl.textContent = "Agent info not available.";
      return;
    }

    const currentStatus = this.agentState.status || 'Unknown';

    infoEl.innerHTML = `
      <p><strong>Name:</strong> ${this.agentState.agentName}</p>
      <p><strong>Email:</strong> ${this.agentState.agentEmail || 'N/A'}</p>
      <p><strong>Current State:</strong> <span class="status-badge status-${currentStatus}">${currentStatus}</span></p>
    `;

    // Populate idle reasons
    selectEl.innerHTML = '<option value="">Select reason...</option>';
    this.idleCodes.forEach(code => {
      const opt = document.createElement('option');
      opt.value = code.id;
      opt.textContent = code.name;
      selectEl.appendChild(opt);
    });

    actionsEl.style.display = 'block';
  }

  showError(msg) {
    const infoEl = this.shadowRoot.getElementById('info');
    infoEl.innerHTML = `<span style="color:red;">❌ SDK Error: ${msg}</span>`;
  }
}

customElements.define('agent-status-widget', AgentStatusWidget);
