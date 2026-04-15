"""
Shared pytest fixtures for Lambda function testing.
"""
import os
import shutil
import pytest
from pathlib import Path
from aws.test_utils.extract_lambda_functions import extract_lambda_functions


def create_lambda_function_files_fixture(yaml_file_path: Path):
    """
    Factory function to create a lambda_function_files fixture for a specific YAML file.
    
    Args:
        yaml_file_path: Path to the CloudFormation YAML file containing Lambda function
    
    Returns:
        A pytest fixture function that extracts and cleans up Lambda functions
    
    Example:
        In your test file:
        >>> YAML_FILE_PATH = TEST_DIR.parent / 'my-lambda.yml'
        >>> lambda_function_files = create_lambda_function_files_fixture(YAML_FILE_PATH)
    """
    @pytest.fixture(scope="session")
    def lambda_function_files():
        """Extract Lambda function from YAML once for all tests"""
        # Set AWS region
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        
        # Verify YAML file exists
        if not yaml_file_path.exists():
            pytest.exit(f"YAML file not found at: {yaml_file_path}", 3)
        
        # Extract Lambda function from YAML
        temp_file, temp_path, temp_dir_path = extract_lambda_functions(yaml_file_path)
        
        if not temp_file:
            pytest.exit(
                "Failed to extract Lambda function from YAML. "
                "This indicates an issue with the YAML file or extraction logic.", 
                3
            )
        
        yield temp_file, temp_path, temp_dir_path
        
        # Cleanup after all tests complete
        if temp_file:
            try:
                temp_file.close()
            except:
                pass
        if temp_dir_path and os.path.exists(temp_dir_path):
            try:
                shutil.rmtree(temp_dir_path)
            except Exception as e:
                print(f"Warning: Could not remove directory {temp_dir_path}: {e}")
    
    return lambda_function_files