# Copyright 2026 The MathWorks, Inc.
"""Render the per-release files for the released repository.

For each target version, locates the built CloudFormation template and renders
the release README from the Jinja2 template with the same data refarch-utils
passes. Returns the rendered README plus the raw template content for each
release so the caller can lay them out on disk.
"""
import json
import os

COPY_AMI_SOURCE_REGION = "us-east-1"
COPY_AMI_LAMBDA_VERSION = "v1/0/0"

def readme_data(template, version, template_url):
    """
    The values the release README template renders with: launch regions,
    parameter table, template URL and the copy-AMI link.
    """
    region_map = template.get("Mappings", {}).get("RegionMap", {})
    # Regions without a prebuilt AMI hold a placeholder for custom AMIs.
    regions = [region for region, entry in region_map.items() if str(entry.get("AMI", "")).startswith("ami-")]

    copy_source_ami = region_map.get(COPY_AMI_SOURCE_REGION, {}).get("AMI", "")
    if not copy_source_ami.startswith("ami-"):
        raise ValueError(f"No {COPY_AMI_SOURCE_REGION} AMI in the {version} release template; the copy-AMI link needs one")

    parameter_labels = template.get("Metadata", {}).get("AWS::CloudFormation::Interface", {}).get("ParameterLabels", {})
    parameters = [
        {
            "name": key,
            "label": (parameter_labels.get(key, {}).get("default") or key).strip(),
            "description": value["Description"].replace("<", "\\<").replace("|", "\\|"),
        }
        for key, value in template["Parameters"].items()
    ]

    return {
        "template_url": template_url,
        "regions": regions,
        "parameters": parameters,
        "copy_ami_parameters": {
            "copy_source_ami_region": COPY_AMI_SOURCE_REGION,
            "copy_source_ami_id": copy_source_ami,
            "copy_ami_lambda_version": COPY_AMI_LAMBDA_VERSION,
        },
        "CURRENT_RELEASE": version,
        "version": version,
    }

def process_single_release(template_env, version, artifact_dir, template_file_name, release_readme_template_path):
    """
    Processes a single release: reads the built template and renders the README.

    Returns:
        dict: {
            'version': version,
            'readme_content': str,
            'cf_template_content': str,
        }
    """
    cft_path = os.path.join(artifact_dir, f"{version}-release-template.json")
    if not os.path.exists(cft_path):
        raise FileNotFoundError(f"No release template for {version} at {cft_path}")

    with open(cft_path, 'r', encoding='utf-8') as f:
        cft_content = f.read()

    # The release job records the URL it published the template at.
    url_path = os.path.join(artifact_dir, f"{version}-release-template-url.txt")
    if not os.path.exists(url_path):
        raise FileNotFoundError(f"No published template URL for {version} at {url_path}")
    with open(url_path, 'r', encoding='utf-8') as f:
        template_url = f.read().strip()
    readme_content = template_env.get_template(release_readme_template_path).render(
        **readme_data(json.loads(cft_content), version, template_url)
    )

    return {
        'version': version,
        'readme_content': readme_content,
        'cf_template_content': cft_content,
    }

def process_files(template_env, target_versions, artifact_dir, template_file_name, release_readme_template_path):
    return [
        process_single_release(
            template_env,
            version,
            artifact_dir,
            template_file_name,
            release_readme_template_path
        )
        for version in target_versions
    ]
