# Copyright 2026 The MathWorks, Inc.
"""
Calculate the MATLAB version matrix for the build pipeline.

Reads INPUT_STR (optional comma-separated list) and TARGET_DIR from the
environment. TARGET_DIR holds either Packer release configs
(<version>.pkrvars.hcl) or release folders (<version>/). If INPUT_STR is set,
validates each listed version against TARGET_DIR. Otherwise, auto-detects all
R20XX[ab] versions and returns the latest 5.

Writes a JSON array as `matrix=<json>` to GITHUB_OUTPUT.
"""
import os
import json
import re

VERSION = re.compile(r'^R20\d{2}[ab]$')
RELEASE_CONFIG = re.compile(r'^(R20\d{2}[ab])\.pkrvars\.hcl$')


def available_versions(target_dir):
    """Versions with a release config file or a release folder in target_dir."""
    versions = set()
    for item in os.listdir(target_dir):
        path = os.path.join(target_dir, item)
        config = RELEASE_CONFIG.match(item)
        if config and os.path.isfile(path):
            versions.add(config.group(1))
        elif VERSION.match(item) and os.path.isdir(path):
            versions.add(item)
    return versions


def main():
    input_str = os.environ.get('INPUT_STR', '').strip()
    target_dir = os.environ.get('TARGET_DIR', './packer/v1/release-config')

    if not os.path.exists(target_dir):
        print(f"::error::Directory {target_dir} not found. Cannot validate versions.")
        exit(1)

    available = available_versions(target_dir)

    if input_str:
        versions = []
        for v in (s.strip() for s in input_str.split(',') if s.strip()):
            if not VERSION.match(v):
                print(f"::error::'{v}' is not a MATLAB version such as R2026a")
                exit(1)
            if v not in available:
                print(f"::error::Version '{v}' not found in {target_dir}")
                exit(1)
            if v not in versions:
                versions.append(v)
    else:
        versions = sorted(available, reverse=True)[:5]

    print(f"Selected versions: {versions}")

    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write(f"matrix={json.dumps(versions)}\n")


if __name__ == "__main__":
    main()
