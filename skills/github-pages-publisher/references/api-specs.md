# GitHub Pages Publisher API Reference

This reference lists the GitHub REST API v3 endpoints used to programmatically manage repositories and enable GitHub Pages hosting.

---

## 🔑 Authentication

All requests to the GitHub REST API require a Personal Access Token (PAT) with at least the `repo` scope, passed in the `Authorization` header:

```http
Authorization: Bearer <github_token>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```

---

## 📂 REST Endpoints

### 1. Create a Repository (for authenticated user)
Creates a new repository in the authenticated user's account.

* **Method**: `POST`
* **URL**: `https://api.github.com/user/repos`
* **Payload**:
  ```json
  {
    "name": "my-wxcc-widget",
    "description": "Custom agent desktop widget for Webex Contact Center",
    "private": false,
    "has_issues": true,
    "has_projects": false,
    "has_wiki": false
  }
  ```
* **Response (201 Created)**: Returns repository details, including `html_url`, `clone_url`, etc.

---

### 2. Enable GitHub Pages
Enables GitHub Pages hosting on an existing repository. A branch (e.g. `main`) must be pushed prior to calling this endpoint.

* **Method**: `POST`
* **URL**: `https://api.github.com/repos/{owner}/{repo}/pages`
* **Payload**:
  ```json
  {
    "source": {
      "branch": "main",
      "path": "/"
    }
  }
  ```
* **Response (201 Created)**: Returns details about the Pages site, including the public `html_url` hosting endpoint:
  ```json
  {
    "url": "https://api.github.com/repos/octocat/hello-world/pages",
    "status": "built",
    "html_url": "https://octocat.github.io/hello-world/"
  }
  ```

---

### 3. Check Pages Build Status
Retrieve the status of the Pages deployment builder.

* **Method**: `GET`
* **URL**: `https://api.github.com/repos/{owner}/{repo}/pages`
* **Response (200 OK)**: Returns the status (e.g. `building`, `built`, or `errored`).
