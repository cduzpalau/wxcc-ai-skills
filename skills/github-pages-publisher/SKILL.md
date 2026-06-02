---
name: github-pages-publisher
description: Automatically create a GitHub repository, push compiled widget code, and enable GitHub Pages to publish widgets publicly on the internet.
---

# Webex Contact Center Widget GitHub Pages Publisher Skill

This skill allows AI agents to automatically push built custom Webex Contact Center widgets to a newly created GitHub repository and publish them to the internet using GitHub Pages.

---

## 📂 Skill Folder Structure
```text
skills/github-pages-publisher/
├── SKILL.md                 # This instruction file
├── scripts/
│   └── publish_widget.py    # Python deployment automation script
├── examples/
│   └── workflow-sample.yml  # Example GitHub Action CI/CD workflow
└── references/
    └── api-specs.md         # List of GitHub REST API endpoints used
```

---

## ⚙️ Environment Setup

Create or append to the `.env` file in the root of the project:

```env
GITHUB_USERNAME=your-github-username
GITHUB_TOKEN=your-github-personal-access-token
```

> [!IMPORTANT]
> The GitHub Personal Access Token (PAT) must have the **`repo`** scope (or read/write permissions for repository actions and Pages settings) to create repositories and enable Pages hosting.

---

## 🚀 How to Publish a Widget

To compile, create a repository, push files, and enable GitHub Pages, run the python script:

```bash
python skills/github-pages-publisher/scripts/publish_widget.py <widget_directory>
```

### Options:
* `--repo-name <name>`: Define a custom name for the new repository (defaults to the widget's folder name).
* `--private`: Creates a private repository instead of a public one (Note: GitHub Pages requires a GitHub Pro or Enterprise account for private repository hosting).

### Example:
```bash
python skills/github-pages-publisher/scripts/publish_widget.py src/widgets/my-widget --repo-name custom-wxcc-widget
```

---

## 🔗 Resulting Output

Once completed, the script output prints:
1. The public script URL (e.g. `https://<username>.github.io/<repo-name>/dist/<widget_name>.js`) to be used in WxCC Agent Desktop layouts.
2. The homepage layout URL.
3. A JSON layout injection snippet ready to be pushed using the `desktop-layout-manager` skill.

---

## ⚠️ Troubleshooting & Limits

1. **Pages Site Returns 404**:
   GitHub Pages builds can take 1–2 minutes to finish processing the initial push. If the URL returns a 404, wait a moment and try fetching again.
2. **Repository Already Exists**:
   If the script detects that a repository or local `.git` repository already exists, it resets and forces pushes the current workspace files to ensure deployment success. Ensure you do not accidentally overwrite an active, unrelated repository.
