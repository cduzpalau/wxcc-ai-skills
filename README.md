# Webex Contact Center AI Skills Toolchain

Welcome to the Webex Contact Center AI Skills repository! This is a collection of specialized "superpowers" for your favorite AI agents, designed to help you build, host, and deploy custom Agent Desktop widgets in seconds.

Check out more skills at [agentskills.io/home](https://agentskills.io/home).

---

## What are "AI Skills"? (For Dummies)

Imagine your AI agent (like Gemini, Claude, or Codex) is a super-smart intern. They know how to code, but they don't know the "secret handshake" for specific systems—like how to talk to the Webex API or how to set up a GitHub Pages site automatically.

AI Skills are like instruction manuals you give to your AI. Once "installed," the AI suddenly knows exactly:
1. What tools to use (like Python scripts or SDKs).
2. The "Best Practices" (so it doesn't make common mistakes).
3. The Workflow (the step-by-step process to get a job done).

With these skills, you don't have to explain how to build a widget; you just say "Build me a widget that shows agent stats," and the AI handles the rest!

---

## Included Skills

This project includes three powerful skills that work together:

1.  **Widget Coder (`wxcc-skill-coder`)**: Scaffolds and writes the code for your custom Webex widgets using the latest SDK standards.
2.  **GitHub Pages Publisher (`github-pages-publisher`)**: Takes your widget code, creates a GitHub repo, and hosts it online so Webex can see it.
3.  **Desktop Layout Manager (`desktop-layout-manager`)**: Automatically "plugs" your new widget into your Webex Agent Desktop layout.

---

## How to Install

Installing these skills is as easy as moving a folder. Most AI agents follow the SKILL.md standard.

### 1. The Easy Way (One Command)
If you have the skills utility installed, run:
```bash
npx skills add cpalau/wxcc-ai-skills
```

### 2. The Manual Way
Download this repository and move the folders inside /skills to the directory your agent watches:

| Agent | Global Folder (All Projects) | Local Folder (This Project) |
| :--- | :--- | :--- |
| **Gemini CLI** | `~/.gemini/skills/` | `.gemini/skills/` |
| **Claude Code** | `~/.claude/skills/` | `.claude/skills/` |
| **Antigravity CLI** | `~/.gemini/antigravity/skills/` | `.agents/skills/` |
| **Codex CLI** | `~/.codex/skills/` | `.codex/skills/` |

**Steps:**
1. Copy the skill folder (e.g., `wxcc-skill-coder`) into the appropriate path above.
2. Restart your AI CLI session.
3. Ask your agent: "What skills do you have?" to confirm!

---

## Prerequisites
To use these skills effectively, make sure you have your .env file configured with:
* GITHUB_TOKEN (for publishing)
* WXCC_ACCESS_TOKEN (for layout management)
* WXCC_ORG_ID

---

## Learn More
Visit **[AgentSkills.io](https://agentskills.io/home)** to discover more skills for your AI toolchain and join the community of developers building the future of autonomous work.
