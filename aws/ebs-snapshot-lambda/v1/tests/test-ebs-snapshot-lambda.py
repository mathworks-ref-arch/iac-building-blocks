"""
Copyright 2026 The MathWorks, Inc

Unit test for EBS snapshot Lambda function.
Tests the Lambda handler extracted from the CloudFormation template.
"""
import os
import sys
import importlib.util
import pytest
import boto3
from moto import mock_aws
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

# Get paths using pathlib
TEST_DIR = Path(__file__).parent
REPO_ROOT = TEST_DIR.parents[3]  # Go up 3 levels from the test directory
YAML_FILE_PATH = TEST_DIR.parent / 'ebs-snapshot-lambda.yml'

# Add to path for imports
sys.path.insert(0, str(REPO_ROOT))
from aws.test_utils.lambda_test_fixtures import create_lambda_function_files_fixture

# Create the fixture using the factory
lambda_function_files = create_lambda_function_files_fixture(YAML_FILE_PATH)


class MockCfnResponse:
    """Mock cfnresponse module for testing"""
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'
    
    def __init__(self):
        self.send = MagicMock()
    
    @staticmethod
    def send(event, context, responseStatus, responseData, physicalResourceId=None, noEcho=False, reason=None):
        """Mock send function that does nothing but allows us to verify calls"""
        pass


@pytest.fixture
def mock_cfn_send():
    """Fixture to mock cfnresponse.send"""
    mock_module = MockCfnResponse()
    sys.modules['cfnresponse'] = mock_module
    
    mock_send = MagicMock()
    mock_module.send = mock_send
    
    yield mock_send


class TestEBSSnapshotLambda:
    """Test the EBS snapshot Lambda function behavior"""
    
    def load_lambda_module(self, lambda_function_files, mock_cfn_send):
        """Helper to load the Lambda module."""
        if 'cfnresponse' not in sys.modules:
            mock_module = MockCfnResponse()
            mock_module.send = mock_cfn_send
            sys.modules['cfnresponse'] = mock_module
        else:
            sys.modules['cfnresponse'].send = mock_cfn_send
        
        _, temp_path, _ = lambda_function_files
        spec = importlib.util.spec_from_file_location("lambda_module", temp_path)
        lambda_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lambda_module)
        return lambda_module
    
    def create_instance_with_volume(
        self, 
        ec2_client, 
        device_name: str = '/dev/sda1',
        image_id: str = 'ami-12345678', 
        instance_type: str = 't2.micro'
    ) -> tuple[str, str]:
        """Helper to create an EC2 instance with a volume and return instance ID and volume ID."""
        response = ec2_client.run_instances(
            ImageId=image_id,
            MinCount=1,
            MaxCount=1,
            InstanceType=instance_type,
            BlockDeviceMappings=[{
                'DeviceName': device_name,
                'Ebs': {
                    'VolumeSize': 10,
                    'DeleteOnTermination': False,
                    'VolumeType': 'gp2'
                }
            }]
        )
        instance_id = response['Instances'][0]['InstanceId']
        
        instance_info = ec2_client.describe_instances(InstanceIds=[instance_id])
        volume_id = instance_info['Reservations'][0]['Instances'][0]['BlockDeviceMappings'][0]['Ebs']['VolumeId']
        
        return instance_id, volume_id
    
    def get_snapshots_for_volume(self, ec2_client, volume_id: str) -> list:
        """Helper to get snapshots for a specific volume"""
        all_snapshots = ec2_client.describe_snapshots(OwnerIds=['self'])['Snapshots']
        return [s for s in all_snapshots if s.get('VolumeId') == volume_id]
    
    def create_cfn_event(
        self,
        request_type: str,
        instance_id: str,
        device_name: str = '/dev/sda1',
        product_id: str = 'test-product',
        tags: str = '',
        pre_snapshot_command: str = ''
    ) -> dict:
        """Helper to create a CloudFormation custom resource event."""
        return {
            'RequestType': request_type,
            'ResponseURL': 'https://cloudformation-custom-resource-response-useast1.s3.amazonaws.com/test',
            'StackId': 'arn:aws:cloudformation:us-east-1:123456789012:stack/test-stack/test-id',
            'RequestId': 'test-request-id',
            'ResourceType': 'Custom::SnapshotResource',
            'LogicalResourceId': 'SnapshotCustomResource',
            'ResourceProperties': {
                'EC2InstanceId': instance_id,
                'VolumeDeviceName': device_name,
                'ProductId': product_id,
                'Tags': tags,
                'PreSnapshotCommand': pre_snapshot_command
            }
        }
    
    def create_mock_context(self):
        """Helper to create a mock Lambda context object."""
        class MockContext:
            def __init__(self):
                self.function_name = 'test-function'
                self.function_version = '$LATEST'
                self.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:test-function'
                self.memory_limit_in_mb = 512
                self.aws_request_id = 'test-request-id'
                self.log_group_name = '/aws/lambda/test-function'
                self.log_stream_name = 'test-stream'
        
        return MockContext()
    
    def setup_mock_ssm(self, original_boto3_client, mock_ssm_config):
        """Helper to setup SSM mocking for tests"""
        mock_ssm = Mock()
        
        if 'send_command_return' in mock_ssm_config:
            mock_ssm.send_command.return_value = mock_ssm_config['send_command_return']
        
        if 'list_invocations_return' in mock_ssm_config:
            mock_ssm.list_command_invocations.return_value = mock_ssm_config['list_invocations_return']
        
        def client_side_effect(service_name, **kwargs):
            if service_name == 'ec2':
                return original_boto3_client('ec2', region_name='us-east-1')
            elif service_name == 'ssm':
                return mock_ssm
            return original_boto3_client(service_name, **kwargs)
        
        return mock_ssm, client_side_effect

    @mock_aws
    @pytest.mark.parametrize("request_type", ['Create', 'Update'])
    def test_handler_ignores_non_delete_requests(
        self, mock_cfn_send, lambda_function_files, request_type
    ):
        """Test that snapshots are never created for non-Delete request types"""
        lambda_module = self.load_lambda_module(lambda_function_files, mock_cfn_send)
        
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id, volume_id = self.create_instance_with_volume(ec2)
        
        event = self.create_cfn_event(
            request_type, 
            instance_id,
            pre_snapshot_command='{{AWS-RunShellScript}} echo "test"'
        )
        context = self.create_mock_context()
        
        lambda_module.handler(event, context)
        
        # Verify SUCCESS with empty data and no snapshots
        mock_cfn_send.assert_called_once()
        assert mock_cfn_send.call_args[0][2] == 'SUCCESS'
        assert mock_cfn_send.call_args[0][3] == {}
        assert len(self.get_snapshots_for_volume(ec2, volume_id)) == 0

    @mock_aws
    def test_handler_processes_delete_request(self, mock_cfn_send, lambda_function_files):
        """Test that handler processes Delete request and creates snapshot"""
        lambda_module = self.load_lambda_module(lambda_function_files, mock_cfn_send)
        
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id, volume_id = self.create_instance_with_volume(ec2)
        
        product_id = 'test-product-delete'
        event = self.create_cfn_event('Delete', instance_id, product_id=product_id)
        context = self.create_mock_context()
        
        lambda_module.handler(event, context)
        
        # Verify SUCCESS and snapshot created
        mock_cfn_send.assert_called_once()
        call_args = mock_cfn_send.call_args
        assert call_args[0][2] == 'SUCCESS'
        
        snapshots = self.get_snapshots_for_volume(ec2, volume_id)
        assert len(snapshots) == 1
        assert snapshots[0]['VolumeId'] == volume_id
        
        # Verify tags and response
        snapshot_tags = {tag['Key']: tag['Value'] for tag in snapshots[0].get('Tags', [])}
        assert snapshot_tags.get('mw-ProductId') == product_id
        
        response_data = call_args[0][3]
        assert 'Snapshot created successfully' in response_data['Message']
        assert snapshots[0]['SnapshotId'] in response_data['Message']

    @mock_aws
    def test_non_delete_request_without_ec2_calls(
        self, mock_cfn_send, lambda_function_files
    ):
        """Test that non-Delete requests don't make EC2 API calls"""
        lambda_module = self.load_lambda_module(lambda_function_files, mock_cfn_send)
        
        # Invalid instance ID - would fail if EC2 calls were made
        event = self.create_cfn_event('Create', 'i-invalidinstance123')
        context = self.create_mock_context()
        
        lambda_module.handler(event, context)
        
        mock_cfn_send.assert_called_once()
        assert mock_cfn_send.call_args[0][2] == 'SUCCESS'
    
    @mock_aws
    @pytest.mark.parametrize("instance_state,pre_command,ssm_status,should_call_ssm,should_create_snapshot,test_description", [
        # Instance running with command - SSM should be called
        ('running', '{{AWS-RunShellScript}} echo "test"', 'Success', True, True, 
         "Execute command when instance running"),
        
        # Instance stopped with command - SSM should NOT be called
        ('stopped', '{{AWS-RunShellScript}} echo "test"', None, False, True,
         "Skip command when instance stopped"),
        
        # Instance running with empty command - SSM should NOT be called
        ('running', '', None, False, True,
         "Skip SSM when command is empty"),
        
        # Instance running with PowerShell - SSM should be called
        ('running', '{{AWS-RunPowerShellScript}} Write-Host "test"', 'Success', True, True,
         "Execute PowerShell command"),
        
        # Instance running with failed command - snapshot still created
        ('running', '{{AWS-RunShellScript}} exit 1', 'Failed', True, True,
         "Create snapshot even if SSM fails"),
        
        # Instance running with timed out command - snapshot still created
        ('running', '{{AWS-RunShellScript}} sleep 100', 'TimedOut', True, True,
         "Create snapshot even if SSM times out"),
    ])
    def test_pre_snapshot_command_scenarios(
        self, 
        mock_cfn_send, 
        lambda_function_files,
        instance_state,
        pre_command,
        ssm_status,
        should_call_ssm,
        should_create_snapshot,
        test_description
    ):
        """Parametrized test for various PreSnapshotCommand scenarios"""
        lambda_module = self.load_lambda_module(lambda_function_files, mock_cfn_send)
        
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id, volume_id = self.create_instance_with_volume(ec2)
        
        # Set instance state
        if instance_state == 'stopped':
            ec2.stop_instances(InstanceIds=[instance_id])
        
        # Verify instance state
        instance_info = ec2.describe_instances(InstanceIds=[instance_id])
        actual_state = instance_info['Reservations'][0]['Instances'][0]['State']['Name']
        assert actual_state == instance_state
        
        event = self.create_cfn_event('Delete', instance_id, pre_snapshot_command=pre_command)
        context = self.create_mock_context()
        
        original_boto3_client = boto3.client
        
        # Setup SSM mock
        mock_ssm_config = {}
        if should_call_ssm:
            mock_ssm_config['send_command_return'] = {
                'Command': {'CommandId': 'test-command-id'}
            }
            mock_ssm_config['list_invocations_return'] = {
                'CommandInvocations': [{
                    'Status': ssm_status,
                    'CommandPlugins': [{'Output': f'Command {ssm_status.lower()}'}]
                }]
            }
        
        with patch('boto3.client') as mock_boto_client:
            mock_ssm, client_side_effect = self.setup_mock_ssm(original_boto3_client, mock_ssm_config)
            mock_boto_client.side_effect = client_side_effect
            
            with patch('time.sleep'):
                lambda_module.handler(event, context)
            
            # Verify SSM interaction
            if should_call_ssm:
                mock_ssm.send_command.assert_called_once()
                call_args = mock_ssm.send_command.call_args
                
                # Verify correct document type for PowerShell vs Shell
                if 'PowerShell' in pre_command:
                    assert call_args[1]['DocumentName'] == 'AWS-RunPowerShellScript'
                else:
                    assert call_args[1]['DocumentName'] == 'AWS-RunShellScript'
            else:
                mock_ssm.send_command.assert_not_called()
        
        # Verify snapshot creation
        snapshots = self.get_snapshots_for_volume(ec2, volume_id)
        if should_create_snapshot:
            assert len(snapshots) == 1, f"{test_description}: Expected snapshot to be created"
        else:
            assert len(snapshots) == 0, f"{test_description}: Expected no snapshot"
        
        # Verify success response
        mock_cfn_send.assert_called_once()
        assert mock_cfn_send.call_args[0][2] == 'SUCCESS'
    
    @mock_aws
    @pytest.mark.parametrize("input_cmd,expected_doc,expected_cmd", [
        ('{{AWS-RunShellScript}} echo "hello"', 'AWS-RunShellScript', 'echo "hello"'),
        ('{{AWS-RunPowerShellScript}} Write-Host "test"', 'AWS-RunPowerShellScript', 'Write-Host "test"'),
        ('{{AWS-RunShellScript}}ls -la', 'AWS-RunShellScript', 'ls -la'),
        ('{{AWS-RunShellScript}}   echo "spaces"', 'AWS-RunShellScript', 'echo "spaces"'),
    ])
    def test_extract_document_and_command_valid(
        self, 
        lambda_function_files, 
        mock_cfn_send,
        input_cmd,
        expected_doc,
        expected_cmd
    ):
        """Test that command parsing works for valid formats"""
        lambda_module = self.load_lambda_module(lambda_function_files, mock_cfn_send)
        
        doc_name, command = lambda_module.extract_document_and_command(input_cmd)
        assert doc_name == expected_doc
        assert command == expected_cmd

    @mock_aws
    @pytest.mark.parametrize("invalid_cmd", [
        'echo "no brackets"',
        '{single brackets} echo "test"',
        'AWS-RunShellScript echo "no brackets"',
    ])
    def test_extract_document_and_command_invalid(
        self, 
        lambda_function_files, 
        mock_cfn_send,
        invalid_cmd
    ):
        """Test that command parsing raises exception for invalid formats"""
        lambda_module = self.load_lambda_module(lambda_function_files, mock_cfn_send)
        
        with pytest.raises(Exception) as exc_info:
            lambda_module.extract_document_and_command(invalid_cmd)
        assert "Document name or command couldn't be fetched" in str(exc_info.value)
    
    @mock_aws
    def test_handler_fails_when_instance_not_found_on_delete(
        self, mock_cfn_send, lambda_function_files
    ):
        """Test that handler fails when trying to snapshot non-existent instance"""
        lambda_module = self.load_lambda_module(lambda_function_files, mock_cfn_send)
        
        # Delete request with non-existent instance
        event = self.create_cfn_event('Delete', 'i-nonexistent123')
        context = self.create_mock_context()
        
        lambda_module.handler(event, context)
        
        # Should fail (cannot create snapshot without valid instance)
        mock_cfn_send.assert_called_once()
        assert mock_cfn_send.call_args[0][2] == 'FAILED'
    
    @mock_aws
    def test_handler_fails_when_volume_device_not_found(
        self, mock_cfn_send, lambda_function_files
    ):
        """Test that handler fails when specified device doesn't exist on instance"""
        lambda_module = self.load_lambda_module(lambda_function_files, mock_cfn_send)
        
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id, _ = self.create_instance_with_volume(ec2, device_name='/dev/sda1')
        
        # Request snapshot for non-existent device
        event = self.create_cfn_event('Delete', instance_id, device_name='/dev/nonexistent')
        context = self.create_mock_context()
        
        lambda_module.handler(event, context)
        
        # Should fail (cannot create snapshot without valid volume)
        mock_cfn_send.assert_called_once()
        assert mock_cfn_send.call_args[0][2] == 'FAILED'

if __name__ == "__main__":
    pytest.main([__file__, '-sv'])

