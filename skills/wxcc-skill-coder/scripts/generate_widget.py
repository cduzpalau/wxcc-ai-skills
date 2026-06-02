#!/usr/bin/env python3
import os
import sys
import re
import shutil
import argparse

def to_pascal_case(s):
    words = re.sub(r'[^a-zA-Z0-9]+', ' ', s).split()
    return ''.join(w.capitalize() for w in words)

def to_slug_case(s):
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s.strip().lower())
    return re.sub(r'-+', '-', s).strip('-')

def main():
    parser = argparse.ArgumentParser(description="Scaffold a new WxCC Agent Desktop Widget.")
    parser.add_argument("name", help="The name of the new widget (e.g. 'my-custom-widget')")
    parser.add_argument("--dest", help="Destination directory (default: 'src/widgets/<slug-name>')")
    
    args = parser.parse_args()
    
    slug_name = to_slug_case(args.name)
    pascal_name = to_pascal_case(args.name)
    
    # Define source template directory
    source_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "SampleCode", "wxcc-sdk-widget-fresh"))
    
    if not os.path.exists(source_dir):
        print(f"Error: Template directory not found at: {source_dir}", file=sys.stderr)
        sys.exit(1)
        
    # Define target directory
    if args.dest:
        target_dir = os.path.abspath(args.dest)
    else:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        target_dir = os.path.join(project_root, "src", "widgets", slug_name)
        
    if os.path.exists(target_dir):
        print(f"Error: Target directory already exists at: {target_dir}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Scaffolding new widget:")
    print(f"  Name:        {slug_name}")
    print(f"  Class:       {pascal_name}")
    print(f"  Tag:         <{slug_name}>")
    print(f"  Source:      {source_dir}")
    print(f"  Destination: {target_dir}")
    
    # Copy files
    os.makedirs(target_dir, exist_ok=True)
    
    # Copy file by file (ignoring git/dist metadata)
    ignore_patterns = shutil.ignore_patterns(".git", "dist", "node_modules", ".DS_Store", "package-lock.json")
    
    for item in os.listdir(source_dir):
        s = os.path.join(source_dir, item)
        d = os.path.join(target_dir, item)
        
        # Filter ignores manually
        if item in [".git", "dist", "node_modules", ".DS_Store", "package-lock.json"]:
            continue
            
        if os.path.isdir(s):
            shutil.copytree(s, d, ignore=ignore_patterns)
        else:
            shutil.copy2(s, d)
            
    # Perform placeholders replacement
    files_to_replace = [
        os.path.join(target_dir, "package.json"),
        os.path.join(target_dir, "webpack.config.js"),
        os.path.join(target_dir, "README.md"),
        os.path.join(target_dir, "src", "index.js")
    ]
    
    for filepath in files_to_replace:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Replace names
        content = content.replace("wxcc-sdk-widget-fresh", slug_name)
        content = content.replace("wxcc-widget-fresh", slug_name)
        content = content.replace("WxccWidgetFresh", pascal_name)
        content = content.replace("WxCC Widget Fresh", pascal_name)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
            
    print(f"\n✅ Widget successfully scaffolded in {target_dir}!")
    print(f"To get started:")
    print(f"  1. cd {os.path.relpath(target_dir)}")
    print(f"  2. npm install")
    print(f"  3. npm run build  (to create production bundle)")
    print(f"  4. npm run serve  (to start development server)")

if __name__ == "__main__":
    main()
