import { Desktop } from "@wxcc-desktop/sdk";

class ContactEventsWidget extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.contacts = {};
  }

  connectedCallback() {
    this.render();
    this.initSDK();
  }

  disconnectedCallback() {
    Desktop.agentContact.removeAllEventListeners();
  }

  async initSDK() {
    try {
      await Desktop.config.init('contact-events-widget', 'magician');
      
      // Load current task map
      this.contacts = Desktop.agentContact.taskMap || {};
      this.updateUI();

      // Listen to new contact offer
      Desktop.agentContact.addEventListener("eAgentOfferContact", (event) => {
        console.log("Incoming call/contact offered:", event);
        this.contacts = Desktop.agentContact.taskMap || {};
        this.updateUI();
      });

      // Listen to contact assignment (accepted)
      Desktop.agentContact.addEventListener("eAgentContactAssigned", (event) => {
        console.log("Contact accepted and assigned:", event);
        this.contacts = Desktop.agentContact.taskMap || {};
        this.updateUI();
      });

      // Listen to wrap up/closure
      Desktop.agentContact.addEventListener("eAgentWrapup", (event) => {
        console.log("Contact entered wrap-up:", event);
        this.contacts = Desktop.agentContact.taskMap || {};
        this.updateUI();
      });

      // Listen to contact end / clean up
      Desktop.agentContact.addEventListener("eAgentContactWrappedUp", (event) => {
        console.log("Contact wrapped up/cleared:", event);
        this.contacts = Desktop.agentContact.taskMap || {};
        this.updateUI();
      });

    } catch (error) {
      this.showError(error.message);
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: sans-serif;
          background: #fafafa;
          color: #333;
        }
        .container {
          background: white;
          border-radius: 8px;
          padding: 16px;
          border: 1px solid #e0e0e0;
        }
        .contact-item {
          padding: 12px;
          margin-top: 12px;
          background: #f1f8ff;
          border-left: 4px solid #005a9c;
          border-radius: 4px;
        }
        .contact-item h4 {
          margin: 0 0 8px 0;
        }
        .badge {
          display: inline-block;
          font-size: 11px;
          padding: 2px 6px;
          border-radius: 3px;
          font-weight: bold;
          text-transform: uppercase;
        }
        .badge-offered { background: #ffeeba; color: #856404; }
        .badge-connected { background: #c3e6cb; color: #155724; }
        .badge-wrapup { background: #e2e3e5; color: #383d41; }
      </style>
      <div class="container">
        <h3>Live Call & Interaction Monitor</h3>
        <div id="contact-list">No active contacts or calls.</div>
      </div>
    `;
  }

  updateUI() {
    const listEl = this.shadowRoot.getElementById('contact-list');
    const taskIds = Object.keys(this.contacts);

    if (taskIds.length === 0) {
      listEl.innerHTML = `<p style="color: #666;">No active calls, chats, or tasks.</p>`;
      return;
    }

    listEl.innerHTML = "";
    taskIds.forEach(id => {
      const task = this.contacts[id];
      const interaction = task.interaction || {};
      const ani = interaction.ani || 'Unknown';
      const dnis = interaction.dnis || 'Unknown';
      const channel = interaction.mediaType || 'Voice';
      const status = task.status || 'Offered';

      const item = document.createElement('div');
      item.className = 'contact-item';
      item.innerHTML = `
        <h4>${channel.toUpperCase()} Interaction</h4>
        <div><strong>ANI (Caller):</strong> ${ani}</div>
        <div><strong>DNIS (Dialed):</strong> ${dnis}</div>
        <div><strong>Task ID:</strong> ${id.slice(0, 8)}...</div>
        <div style="margin-top: 6px;">
          <span class="badge badge-${status.toLowerCase()}">${status}</span>
        </div>
      `;
      listEl.appendChild(item);
    });
  }

  showError(msg) {
    const listEl = this.shadowRoot.getElementById('contact-list');
    listEl.innerHTML = `<span style="color:red;">❌ SDK Error: ${msg}</span>`;
  }
}

customElements.define('contact-events-widget', ContactEventsWidget);
