# Copyright 2026 The MathWorks, Inc

import tempfile
import os
from typing import Optional, Tuple, Any, Dict, IO
from .cfn_yaml_loader import load_yaml

def extract_lambda_functions(
    yaml_file_path: str
) -> Tuple[Optional[IO[str]], Optional[str], Optional[str]]:
    """
    Extract and print Lambda function code from a YAML file.
    This function will only extract the first Lambda function.

    Args:
        yaml_file_path: Path to the YAML file

    Returns:
        A tuple containing:
        - The temporary file object (or None)
        - The temporary file path (or None)
        - The temporary directory path (or None)
    """
    try:
        with open(yaml_file_path, 'r') as file:
            # Use custom CloudFormation YAML loader
            lambda_file: Dict[str, Any] = load_yaml(file.read())
        
        # Basic validation
        if not lambda_file or 'Resources' not in lambda_file:
            print(f"No Resources found in {yaml_file_path}")
            return None, None, None
        
        # Determine temp directory based on environment
        # Use RUNNER_TEMP if available (GitHub Actions), otherwise use system temp
        if 'RUNNER_TEMP' in os.environ:
            # Running on GitHub Actions
            base_temp_dir: str = os.environ['RUNNER_TEMP']
            print(f"Using GitHub Runner temp directory: {base_temp_dir}")
        else:
            # Running locally
            base_temp_dir = tempfile.gettempdir()
            print(f"Using system temp directory: {base_temp_dir}")
    
        # Create a subdirectory for our lambda test files
        temp_dir_name: str = f'lambda_test_{os.getpid()}'  # Include PID to make it unique
        temp_dir_path: str = os.path.join(base_temp_dir, temp_dir_name)
    
        # Create the directory if it doesn't exist
        if not os.path.exists(temp_dir_path):
            os.makedirs(temp_dir_path)
            print(f"Created temp directory: {temp_dir_path}")
        
        # Iterate through resources to find Lambda functions
        for resource_name, resource in lambda_file['Resources'].items():
            if resource.get('Type') == 'AWS::Lambda::Function':
                properties: Dict[str, Any] = resource.get('Properties', {})
                code_config: Dict[str, Any] = properties.get('Code', {})
                code: Optional[str] = code_config.get('ZipFile')

                if code:
                    # Create temp file in our temp directory
                    temp_file = tempfile.NamedTemporaryFile(
                        mode='w+', 
                        suffix='.py', 
                        delete=False, 
                        dir=temp_dir_path,
                        prefix='lambda_function_'
                    )
                    temp_file.write(code)
                    temp_file.flush()
                    
                    print(f"Created temp file: {temp_file.name}")
                    return temp_file, temp_file.name, temp_dir_path
                else:
                    print(f"No inline code found for {resource_name}")

    except Exception as e:
        print(f"Error processing {yaml_file_path}: {str(e)}")
    
    return None, None, None

