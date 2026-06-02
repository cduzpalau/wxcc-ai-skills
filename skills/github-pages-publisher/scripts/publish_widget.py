#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse
import urllib.request
import urllib.error

# Simple dotenv parser to load WXCC_ and GITHUB_ environment variables
def load_env(path='.env'):
    if os.path.exists(path):
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

def get_required_env(name):
    val = os.getenv(name)
    if not val:
        print(f"Error: Environment variable {name} is not set.")
        print(f"Please define it in your shell or in a .env file in the project root.")
        sys.exit(1)
    return val

def run_cmd(args, cwd=None):
    try:
        res = subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(args)}", file=sys.stderr)
        print(f"Exit code: {e.returncode}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)

def github_request(url, token, method='GET', data=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "WxCCWM-Publisher"
    }
    
    req_data = None
    if data is not None:
        req_data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        
    req = urllib.request.Request(url, method=method, headers=headers, data=req_data)
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode('utf-8')
            return res.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            return e.code, json.loads(error_body)
        except:
            return e.code, error_body
    except Exception as e:
        print(f"Connection Error: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    load_env()
    
    parser = argparse.ArgumentParser(description="Create a GitHub Repository, push your widget, and enable GitHub Pages.")
    parser.add_argument("widget_dir", help="Path to the custom widget directory (e.g. 'src/widgets/my-widget')")
    parser.add_argument("--repo-name", help="GitHub repository name (defaults to folder name)")
    parser.add_argument("--private", action="store_true", help="Create a private repository (Note: Pages requires GitHub Enterprise/Pro for private repos)")
    
    args = parser.parse_args()
    
    # 1. Load configuration
    token = get_required_env("GITHUB_TOKEN")
    username = get_required_env("GITHUB_USERNAME")
    
    widget_path = os.path.abspath(args.widget_dir)
    if not os.path.exists(widget_path):
        print(f"Error: Widget directory not found: {widget_path}", file=sys.stderr)
        sys.exit(1)
        
    folder_name = os.path.basename(widget_path.rstrip('/'))
    repo_name = args.repo_name or folder_name
    
    # 2. Bundle the widget first
    print("📦 Step 1: Building/bundling widget output...")
    if os.path.exists(os.path.join(widget_path, "package.json")):
        # If node_modules is missing, install dependencies
        if not os.path.exists(os.path.join(widget_path, "node_modules")):
            print("Installing dependencies...")
            run_cmd(["npm", "install"], cwd=widget_path)
            
        print("Compiling webpack production bundle...")
        run_cmd(["npm", "run", "build"], cwd=widget_path)
    else:
        print("Warning: No package.json found in widget directory. Skipping build step.")
        
    # Check if build output is present
    dist_path = os.path.join(widget_path, "dist")
    if not os.path.exists(dist_path) or not os.listdir(dist_path):
        print("Error: Compile failed or 'dist/' folder is empty. Cannot publish empty widget.")
        sys.exit(1)
        
    # Find built .js file name
    js_files = [f for f in os.listdir(dist_path) if f.endswith('.js') and not f.endswith('.map')]
    if not js_files:
        print("Error: No compiled bundle (.js) found in dist/ directory.")
        sys.exit(1)
    widget_bundle_filename = js_files[0]
    
    # 3. Create the GitHub Repository
    print(f"\n🖥️ Step 2: Creating GitHub repository '{repo_name}'...")
    create_url = "https://api.github.com/user/repos"
    payload = {
        "name": repo_name,
        "description": "WxCC Agent Desktop Custom Widget",
        "private": args.private,
        "has_issues": True,
        "has_projects": False,
        "has_wiki": False
    }
    
    status, repo_data = github_request(create_url, token, method='POST', data=payload)
    if status == 422 and "already exists" in str(repo_data):
        print(f"ℹ️ Repository '{repo_name}' already exists. Skipping creation...")
        # Fetch repo details to get the URL
        get_url = f"https://api.github.com/repos/{username}/{repo_name}"
        status, repo_data = github_request(get_url, token, method='GET')
    
    repo_url = repo_data.get("html_url")
    if not repo_url:
        print(f"Error: Could not retrieve repository URL. Status: {status}")
        print(f"Details: {repo_data}")
        sys.exit(1)
        
    print(f"✅ Repository ready: {repo_url}")
    
    # 4. Initialize Local Git & Push
    print("\n🚀 Step 3: Initializing Git and pushing widget files to GitHub...")
    # Clear existing git if any (or ask to overwrite)
    git_dir = os.path.join(widget_path, ".git")
    if os.path.exists(git_dir):
        print("Warning: Found existing .git folder. Re-initializing remote origin...")
        # Just remove and re-init to ensure a clean slate for this deployment flow
        import shutil
        shutil.rmtree(git_dir)
        
    # Create gitgnore if it does not exist
    gitignore_path = os.path.join(widget_path, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, 'w') as f:
            f.write("node_modules/\n.DS_Store\n*.log\n")
            
    run_cmd(["git", "init"], cwd=widget_path)
    run_cmd(["git", "checkout", "-b", "main"], cwd=widget_path)
    run_cmd(["git", "add", "."], cwd=widget_path)
    run_cmd(["git", "commit", "-m", "Deploy custom WxCC Widget to GitHub Pages"], cwd=widget_path)
    
    # Set remote URL containing token for authentication
    remote_url = f"https://{token}@github.com/{username}/{repo_name}.git"
    run_cmd(["git", "remote", "add", "origin", remote_url], cwd=widget_path)
    
    print("Pushing to remote 'main' branch...")
    run_cmd(["git", "push", "-u", "origin", "main", "--force"], cwd=widget_path)
    print("✅ Files pushed successfully!")
    
    # 5. Enable GitHub Pages
    print("\n🌐 Step 4: Enabling GitHub Pages hosting on repository...")
    pages_url = f"https://api.github.com/repos/{username}/{repo_name}/pages"
    pages_payload = {
        "source": {
            "branch": "main",
            "path": "/"
        }
    }
    
    status, pages_data = github_request(pages_url, token, method='POST', data=pages_payload)
    if status == 201:
        print(f"✅ GitHub Pages enabled!")
    elif status == 409:
        print(f"ℹ️ GitHub Pages already enabled.")
    else:
        print(f"⚠️ Warning: GitHub Pages enablement returned status {status}.")
        print(f"Details: {pages_data}")
        
    pages_html_url = f"https://{username}.github.io/{repo_name}/"
    widget_publish_url = f"{pages_html_url}dist/{widget_bundle_filename}"
    print(f"\n🎉 Widget published publicly on the internet!")
    print("-" * 80)
    print(f"🔗 Widget Script URL: {widget_publish_url}")
    print(f"🔗 Pages Site URL:    {pages_html_url}")
    print("-" * 80)
    print("\n💡 Copy this JSON snippet into your WxCC Desktop Layout:")
    layout_snippet = {
        "comp": folder_name,
        "script": widget_publish_url,
        "wrapper": {
            "title": folder_name.replace('-', ' ').title(),
            "maximizeAreaName": "app-maximize-area"
        }
    }
    print(json.dumps(layout_snippet, indent=2))

if __name__ == "__main__":
    main()
