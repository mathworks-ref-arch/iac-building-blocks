# Copyright 2026 The MathWorks, Inc.
"""Entry point for the process-release-files action.

Orchestrates generation of the released repository layout: renders the
top-level files (README, permissions, LICENSE) via ``toplevel``, renders the
per-release files (README + CloudFormation template) via ``release``, then
writes the resulting virtual filesystem to the output directory.
"""
import os
import argparse
import jinja2
import toplevel
import release
import utils
import sys

def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target-versions',    required=True,  help='JSON string of versions')
    parser.add_argument('--source-path',        required=True,  help='Path to source templates')
    parser.add_argument('--artifact-path',      required=True,  help='Path to artifacts')
    parser.add_argument('--s3-bucket-url',      required=True,  help='S3 Bucket URL')
    parser.add_argument('--dual-repo-url',      required=True,  help='Dual Repo URL')
    parser.add_argument('--output-path',        required=False, help='Destination path for generated files', default='.')

    return parser.parse_args()

def main():
    # Capture inputs
    args = setup_args()

    # Deserialize target-versions input
    target_versions = utils.deserialize_target_versions(
        target_versions_string=args.target_versions
    )

    # Define variables
    SRC_DIR         = args.source_path
    PERMISSIONS_DIR = os.path.join(SRC_DIR, 'internal', 'permissions')
    ARTIFACT_DIR    = args.artifact_path
    OUTPUT_DIR      = os.path.abspath(args.output_path)

    print(f"Source Directory: {SRC_DIR}")
    print(f"Output Directory: {OUTPUT_DIR}")

    # Initialize jinja2
    template_loader = jinja2.FileSystemLoader(searchpath=SRC_DIR)
    template_env    = jinja2.Environment(loader=template_loader)

    # Process top-level files
    try:
        toplevel_readme, toplevel_permissions, toplevel_license = toplevel.process_files(
            template_env            = template_env,
            target_releases         = target_versions,
            dual_repo_url           = args.dual_repo_url,
            permission_files_path   = PERMISSIONS_DIR,
            readme_path             = os.path.join('toplevel', 'README.md'),
            permissions_readme_path = os.path.join('toplevel', 'permission.md'),
            license_readme_path     = os.path.join('toplevel', 'LICENSE.md')
        )
    except Exception as e:
        print(f"Error processing top-level files: {e}")
        sys.exit(1)

    # Process release-specific files 
    try:
        release_data = release.process_files(
            template_env                    = template_env,
            target_versions                 = target_versions,
            artifact_dir                    = ARTIFACT_DIR,
            s3_bucket_url                   = args.s3_bucket_url,
            release_readme_template_path    = "README.md" 
        )
    except Exception as e:
        print(f"Error processing release files: {e}")
        sys.exit(1)

    # Define required file/folder structure
    repository_structure = {
        "README.md"         : toplevel_readme,
        "permission.md"    : toplevel_permissions,
        "LICENSE.md"        : toplevel_license,
        "releases"          : {}
    }

    for r in release_data:
        ver = r['version']
        # Note: The logic in release.py reads the raw content of the artifact
        # We need to decide what the output filename should be. 
        # Based on existing logic it seems it wants to output 'aws-matlab-template.json'
        repository_structure['releases'][ver] = {
            "README.md": r['readme_content'],
            "aws-matlab-template.json": r['cf_template_content']
        }

    utils.write_to_disk(OUTPUT_DIR, repository_structure)    
    print("Processing complete.")

if __name__ == "__main__":
    main()