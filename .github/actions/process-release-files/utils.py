# Copyright 2026 The MathWorks, Inc.
import os
import json
import copy
import re
import sys
from typing import List, Dict
from pathlib import Path

def deserialize_target_versions(target_versions_string:str ) -> List[str]:
    try:
        return json.loads(target_versions_string)
    except json.JSONDecodeError:
        print(f"Error: --target-versions must be a valid JSON list. Got: {target_versions_string}")
        sys.exit(1)

def calculate_removal_date(matlab_version: str) -> Dict[str, str]:
    """
    Parses a Matlab version (e.g., 'R2020a' or '2020b') and calculates
    the removal timeframe. Returns a dictionary with year and month.
    """
    # Regex handles 'R2020a', '2020a', '2020A', etc.
    match = re.search(r"(\d{4})([ab])", matlab_version, re.IGNORECASE)
    
    if not match:
        raise ValueError(f"Invalid Matlab version format: {matlab_version}")

    year = int(match.group(1))
    edition = match.group(2).lower()

    if edition == 'a':
        return {'month': 'September', 'year': str(year + 2)}
    elif edition == 'b':
        return {'month': 'March', 'year': str(year + 3)}
    
    raise ValueError(f"Unknown edition: {edition}")

def create_release_object(target_releases: List[str], dual_repo_url: str) -> List[Dict[str, str]]:

    base_url = dual_repo_url.rstrip('/')
    releases_data = []
    
    for release in sorted(target_releases, reverse=True):
        try:
            dates = calculate_removal_date(release)
            releases_data.append({
                'label': release,
                'dir': release,
                'dual_url': f"{base_url}/releases/{release}",
                'removal_month': dates['month'],
                'removal_year': dates['year']
            })
        except ValueError as e:
            print(f"Skipping {release}: {e}")

    return releases_data

def create_permissions_object(permissions_path):

    permissions_object = {}
    path_obj = Path(permissions_path)
    
    if not path_obj.exists() or not path_obj.is_dir():
        return permissions_object

    for file_path in path_obj.iterdir():
        if file_path.is_file() and file_path.suffix == '.json':
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    permissions_object[file_path.stem] = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error: {file_path.name} is not a valid JSON file. {e}")
            except UnicodeDecodeError:
                print(f"Error: Could not decode {file_path.name}")
            except PermissionError:
                print(f"Error: No permission to read {file_path.name}")
            except Exception as e:
                print(f"Unknown error reading {file_path.name}: {e}")
                
    return permissions_object

def remove_action_from_policy(policy: dict, action_to_remove: str) -> dict:
    """Remove single action from policy. """

    policy_copy = copy.deepcopy(policy)

    if "Statement" not in policy_copy:
        return policy_copy

    filtered_statements = []
    for statement in policy_copy["Statement"]:
        if "Action" in statement:
            if isinstance(statement["Action"], list):
                statement["Action"] = [
                    action
                    for action in statement["Action"]
                    if action.lower() != action_to_remove.lower()
                ]
                if statement["Action"]:
                    filtered_statements.append(statement)
            elif isinstance(statement["Action"], str):
                if statement["Action"] != action_to_remove:
                    filtered_statements.append(statement)
        else:
            filtered_statements.append(statement)

    policy_copy["Statement"] = filtered_statements
    return policy_copy

def remove_actions_from_policy(policy: dict, actions_to_remove: list) -> dict:
    """Remove actions from policy without modifying the original."""
    policy_copy = copy.deepcopy(policy)
    
    for action in actions_to_remove:
        policy_copy = remove_action_from_policy(policy_copy, action)
    return policy_copy

def parse_template_json(template_path):
    """
    Parses parameters and regions from the actual JSON file being released.
    This ensures documentation matches the exact artifact.
    """
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading template {template_path}: {e}")
        return [], []
    
    regions = list(data.get("Mappings", {}).get("RegionMap", {}).keys())

    params = []
    for key, value in data.get("Parameters", {}).items():
        params.append({
            "label": key,
            "description": value.get("Description", "")
        })
    return regions, params

def validate_output_directory(path: Path):
    """
    Validates that the output directory exists (or can be created) 
    and is writable.
    """
    try:
        if not path.exists():
            print(f"Output directory does not exist. Creating: {path}")
            path.mkdir(parents=True, exist_ok=True)
        
        if not path.is_dir():
            raise NotADirectoryError(f"The output path exists but is not a directory: {path}")
        
        if not os.access(path, os.W_OK):
            raise PermissionError(f"Write permission denied for directory: {path}")
            
    except PermissionError as e:
        print(f"ERROR: Permission denied. Cannot create or write to '{path}'.")
        print(f"   Details: {e}")
        print("   Check folder ownership (chown) or permissions (chmod).")
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: System error regarding path '{path}'.")
        print(f"   Details: {e}")
        sys.exit(1)

def write_to_disk(base_dir: str, structure: dict):
    """
    Recursive function to write the virtual filesystem to disk.
    Includes robust error handling for permissions and IO issues.
    """
    base_path = Path(base_dir).resolve()
    
    validate_output_directory(base_path)

    def _write_recursive(current_path: Path, current_struct: dict):
        for name, content in current_struct.items():
            target_path = current_path / name        
            try:
                if isinstance(content, dict):
                    if not target_path.exists():
                        target_path.mkdir(parents=True, exist_ok=True)
                    elif not target_path.is_dir():
                        raise NotADirectoryError(f"Path exists and is not a directory: {target_path}")
                    
                    _write_recursive(target_path, content)
                else:
                    if content is None: continue
                    # IMPORTANT: This line allows the repository_structure dictionary to use slashes in keys, 
                    # rather than requiring perfect nesting in the structure itself.
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    print(f"   Created: {target_path.relative_to(base_path)}")

            except PermissionError:
                print(f"ERROR: Permission denied writing: {target_path}")
                # We do not exit here to try writing other files, 
                # but depending on requirements, we might want to sys.exit(1)
            except IsADirectoryError:
                print(f"ERROR: Tried to write a file but path is a directory: {target_path}")
            except OSError as e:
                print(f"ERROR: OS Error writing {target_path}: {e}")

    print(f"Writing files to: {base_path}...")
    _write_recursive(base_path, structure)