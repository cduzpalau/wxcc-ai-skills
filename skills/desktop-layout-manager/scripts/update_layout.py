#!/usr/bin/env python3
import os
import sys
import json
import argparse
import urllib.request
import urllib.error

# Simple dotenv parser to load WXCC_ environment variables
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

def make_request(url, method='GET', headers=None, data=None):
    req_headers = headers or {}
    req_data = None
    if data is not None:
        if isinstance(data, (dict, list)):
            req_data = json.dumps(data).encode('utf-8')
            req_headers['Content-Type'] = 'application/json'
        else:
            req_data = data
            
    req = urllib.request.Request(url, method=method, headers=req_headers, data=req_data)
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode('utf-8')
            return res.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        print(f"Details: {error_body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error making request: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_list(args):
    org_id = get_required_env("WXCC_ORG_ID")
    token = get_required_env("WXCC_ACCESS_TOKEN")
    base_url = os.getenv("WXCC_API_BASE_URL", "https://api.wxcc-us1.cisco.com").rstrip('/')
    
    url = f"{base_url}/organization/{org_id}/v2/desktop-layout"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    print(f"Fetching desktop layouts from {url}...")
    status, response = make_request(url, method='GET', headers=headers)
    
    # Check structure
    layouts = []
    if isinstance(response, list):
        layouts = response
    elif isinstance(response, dict) and "data" in response:
        layouts = response["data"]
    
    if not layouts:
        print("No desktop layouts found.")
        return
        
    print(f"\nFound {len(layouts)} desktop layout(s):")
    print(f"{'ID':<38} | {'Name':<25} | {'Description'}")
    print("-" * 80)
    for layout in layouts:
        lid = layout.get("id", "N/A")
        name = layout.get("name", "N/A")
        desc = layout.get("description", "") or "No description"
        print(f"{lid:<38} | {name:<25} | {desc}")

def cmd_get(args):
    org_id = get_required_env("WXCC_ORG_ID")
    token = get_required_env("WXCC_ACCESS_TOKEN")
    base_url = os.getenv("WXCC_API_BASE_URL", "https://api.wxcc-us1.cisco.com").rstrip('/')
    
    url = f"{base_url}/organization/{org_id}/desktop-layout/{args.layout_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    print(f"Fetching layout {args.layout_id}...")
    status, response = make_request(url, method='GET', headers=headers)
    
    if not response or "jsonFileContent" not in response:
        print("Error: Could not retrieve layout content. Check the Layout ID.")
        sys.exit(1)
        
    layout_content_str = response["jsonFileContent"]
    try:
        layout_json = json.loads(layout_content_str)
    except json.JSONDecodeError:
        print("Warning: The layout JSON content in WxCC is not valid JSON. Saving raw string.")
        layout_json = layout_content_str
        
    with open(args.output_path, 'w') as f:
        json.dump(layout_json, f, indent=2)
        
    print(f"Successfully saved layout structure to {args.output_path}")

def cmd_insert(args):
    if not os.path.exists(args.layout_path):
        print(f"Error: Layout file not found at {args.layout_path}")
        sys.exit(1)
    if not os.path.exists(args.snippet_path):
        print(f"Error: Widget snippet file not found at {args.snippet_path}")
        sys.exit(1)
        
    with open(args.layout_path, 'r') as f:
        layout = json.load(f)
        
    with open(args.snippet_path, 'r') as f:
        snippet = json.load(f)
        
    # Standard navigation is agent -> area -> panel
    try:
        panel = layout["agent"]["area"]["panel"]
        if panel.get("comp") == "md-tabs" and "children" in panel:
            children = panel["children"]
        else:
            print("Error: Could not find 'md-tabs' component with 'children' in layout['agent']['area']['panel'].")
            sys.exit(1)
    except KeyError as e:
        print(f"Error: Layout structure is missing expected path: {e}")
        sys.exit(1)
        
    # Insert snippet
    if isinstance(snippet, list):
        children.extend(snippet)
        inserted_count = len(snippet)
    else:
        children.append(snippet)
        inserted_count = 1
        
    with open(args.layout_path, 'w') as f:
        json.dump(layout, f, indent=2)
        
    print(f"Successfully inserted {inserted_count} component(s) into {args.layout_path}")

def cmd_update(args):
    org_id = get_required_env("WXCC_ORG_ID")
    token = get_required_env("WXCC_ACCESS_TOKEN")
    base_url = os.getenv("WXCC_API_BASE_URL", "https://api.wxcc-us1.cisco.com").rstrip('/')
    
    if not os.path.exists(args.layout_path):
        print(f"Error: Local layout file not found at {args.layout_path}")
        sys.exit(1)
        
    with open(args.layout_path, 'r') as f:
        local_layout = json.load(f)
        
    # Get current layout payload first to extract version and metadata
    get_url = f"{base_url}/organization/{org_id}/desktop-layout/{args.layout_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    print(f"Retrieving current layout metadata from {get_url}...")
    status, current_layout_dto = make_request(get_url, method='GET', headers=headers)
    
    # Prepare DTO for update
    current_layout_dto["jsonFileContent"] = json.dumps(local_layout)
    current_layout_dto["description"] = "Cisco Test desktop layout - Updated May 31 2026 06:22"
    # The API expects PUT to update. WxCC typically requires version consistency.
    
    put_url = f"{base_url}/organization/{org_id}/desktop-layout/{args.layout_id}"
    print(f"Uploading updated layout to {put_url}...")
    
    status, response = make_request(put_url, method='PUT', headers=headers, data=current_layout_dto)
    
    print(f"Successfully updated desktop layout (Status Code: {status})")
    print(f"Response Body: {json.dumps(response, indent=2)}")

def main():
    load_env()
    
    parser = argparse.ArgumentParser(description="Webex CC Desktop Layout Management Helper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # List command
    subparsers.add_parser("list", help="List all desktop layouts")
    
    # Get command
    get_parser = subparsers.add_parser("get", help="Fetch specific desktop layout and save JSON to file")
    get_parser.add_argument("layout_id", help="UUID of the layout on Webex CC")
    get_parser.add_argument("output_path", help="Local file path to save the layout JSON (e.g. layout.json)")
    
    # Insert command
    insert_parser = subparsers.add_parser("insert", help="Insert a widget JSON snippet into a local layout JSON file")
    insert_parser.add_argument("layout_path", help="Local path to layout.json file")
    insert_parser.add_argument("snippet_path", help="Local path to widget snippet JSON file")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Update a desktop layout on Webex CC with local JSON content")
    update_parser.add_argument("layout_id", help="UUID of the layout to update")
    update_parser.add_argument("layout_path", help="Local path to modified layout.json file")
    
    args = parser.parse_args()
    
    if args.command == "list":
        cmd_list(args)
    elif args.command == "get":
        cmd_get(args)
    elif args.command == "insert":
        cmd_insert(args)
    elif args.command == "update":
        cmd_update(args)

if __name__ == "__main__":
    main()
