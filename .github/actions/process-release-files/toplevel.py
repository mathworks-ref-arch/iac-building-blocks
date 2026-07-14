# Copyright 2026 The MathWorks, Inc.
"""Render the top-level files for the released repository.

Generates the repository-root README, the permissions document (with
admin-level IAM actions stripped from the provisioning policy), and the LICENSE
file from their Jinja2 templates.
"""
import utils
import json
from datetime import datetime

def process_readme(template_env, releases_data, dual_repo_url, readme_path):
    """
    Loads the README template and renders it with release data.
    """
    template = template_env.get_template(readme_path)
    
    return template.render(
        releases=releases_data, 
        dual_url=dual_repo_url.rstrip('/')
    )

def process_permissions(template_env, permissions_data, permissions_readme_path):
    """
    Loads the permissions template and renders it.
    """
    ADMIN_LEVEL_ACTIONS = [
        "iam:AttachRolePolicy",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:DeleteRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:TagRole",
    ]
    restricted_provisioning_policy = utils.remove_actions_from_policy(
        permissions_data['provisioning_policy'],    
        ADMIN_LEVEL_ACTIONS
    )

    template = template_env.get_template(permissions_readme_path)
    
    return template.render(
        full_provisioning_policy        = json.dumps(permissions_data['provisioning_policy'], indent=4),
        restricted_provisioning_policy  = json.dumps(restricted_provisioning_policy, indent=4),
        execution_policy                = json.dumps(permissions_data['execution_policy'], indent=4),
        execution_policy_trust          = json.dumps(permissions_data['execution_policy_trust'], indent=4)
    )

def process_license(template_env, year, license_readme_path):
    """
    Loads the LICENSE template.
    """
    template = template_env.get_template(license_readme_path)
    return template.render(current_year=year)

def process_files(
        template_env, 
        target_releases, 
        dual_repo_url, 
        permission_files_path, 
        readme_path, 
        permissions_readme_path, 
        license_readme_path
    ):
    """
    Orchestrates the data gathering and rendering for top-level files.
    """
    releases_data       = utils.create_release_object(target_releases, dual_repo_url)
    permissions_data    = utils.create_permissions_object(permission_files_path)
    current_year        = datetime.now().year

    readme_content      = process_readme(template_env, releases_data, dual_repo_url, readme_path)
    permissions_content = process_permissions(template_env, permissions_data, permissions_readme_path)
    license_content     = process_license(template_env, current_year, license_readme_path)

    return readme_content, permissions_content, license_content