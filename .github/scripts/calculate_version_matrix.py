# Copyright 2026 The MathWorks, Inc.
"""
Calculate the MATLAB version matrix for the build pipeline.

Reads INPUT_STR (optional comma-separated list) and TARGET_DIR (release folder
root) from the environment. If INPUT_STR is set, validates each listed version
has a matching folder under TARGET_DIR. Otherwise, auto-detects all R20XX[ab]
folders and returns the latest 5.

Writes a JSON array as `matrix=<json>` to GITHUB_OUTPUT.
"""
import os
import json
import re


def main():
    input_str = os.environ.get('INPUT_STR', '').strip()
    target_dir = os.environ.get('TARGET_DIR', './releases')

    if not os.path.exists(target_dir):
        print(f"::error::Directory {target_dir} not found. Cannot validate versions.")
        exit(1)

    if input_str:
        versions = []
        for v in (s.strip() for s in input_str.split(',') if s.strip()):
            v_path = os.path.join(target_dir, v)
            if os.path.isdir(v_path):
                versions.append(v)
            else:
                print(f"::error::Version '{v}' not found in {target_dir}")
                exit(1)
    else:
        pattern = re.compile(r'^R20\d{2}[ab]$')
        found = [
            item for item in os.listdir(target_dir)
            if pattern.match(item) and os.path.isdir(os.path.join(target_dir, item))
        ]
        found.sort(reverse=True)
        versions = found[:5]

    print(f"Selected versions: {versions}")

    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write(f"matrix={json.dumps(versions)}\n")


if __name__ == "__main__":
    main()
