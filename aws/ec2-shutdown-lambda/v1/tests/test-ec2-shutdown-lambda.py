"""
Copyright 2026 The MathWorks, Inc.

Unit test for EC2 shutdown Lambda function.
Tests the Lambda handler extracted from the CloudFormation template.
"""
import os
import sys
import importlib.util
import pytest
import boto3
from moto import mock_aws
from pathlib import Path
from datetime import datetime, timedelta, UTC

# Get paths using pathlib
TEST_DIR = Path(__file__).parent
REPO_ROOT = TEST_DIR.parents[3]  # Go up 3 levels from the test directory
YAML_FILE_PATH = TEST_DIR.parent / 'ec2-shutdown-lambda.yml'

# Add to path for imports
sys.path.insert(0, str(REPO_ROOT))
from aws.test_utils.lambda_test_fixtures import create_lambda_function_files_fixture

# Create the fixture using the factory
lambda_function_files = create_lambda_function_files_fixture(YAML_FILE_PATH)


class TestEC2ShutdownLambda:
    """Test the EC2 shutdown Lambda function behavior"""
    
    def load_lambda_module(self, lambda_function_files):
        """Helper to load the Lambda module. Must be called within mock_aws context."""
        _, temp_path, _ = lambda_function_files
        spec = importlib.util.spec_from_file_location("lambda_module", temp_path)
        lambda_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lambda_module)
        return lambda_module
    
    def set_env_vars(self, instance_id: str, shutdown_time: str, tag_to_monitor: str = "mw-autoshutdown"):
        """Helper to set required environment variables for Lambda function."""
        os.environ['EC2_INSTANCE_ID'] = instance_id
        os.environ['SHUTDOWN_BEHAVIOUR'] = shutdown_time
        os.environ['TAG_TO_MONITOR'] = tag_to_monitor
    
    def create_instance(self, ec2_client, image_id: str = 'ami-12345678', instance_type: str = 't2.micro') -> str:
        """Helper to create an EC2 instance and return its instance ID."""
        response = ec2_client.run_instances(
            ImageId=image_id,
            MinCount=1,
            MaxCount=1,
            InstanceType=instance_type
        )
        return response['Instances'][0]['InstanceId']

    def _get_launch_time_naive(self, ec2_client, instance_id: str) -> datetime:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        launch_time = instance.get('LaunchTime')
        if launch_time is None:
            raise AssertionError("LaunchTime is None in test setup; cannot construct non-stale shutdown tag.")
        if launch_time.tzinfo is not None:
            return launch_time.replace(tzinfo=None)
        return launch_time

    def _freeze_lambda_now(self, monkeypatch, lambda_module, frozen_now_naive: datetime):
        """
        Freeze lambda_module.datetime.now(...) to return frozen_now_naive.
        The Lambda imports `datetime` directly (`from datetime import datetime, ...`),
        so we patch the module attribute `datetime`.
        """
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return frozen_now_naive
                return frozen_now_naive.replace(tzinfo=tz)

        monkeypatch.setattr(lambda_module, "datetime", FrozenDatetime)

    @mock_aws
    def test_handler_with_non_existent_instance(self, capsys, lambda_function_files):
        """Test handler behavior with non-existent instance ID"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Set environment variables with non-existent instance
        self.set_env_vars("i-nonexistent", "After 2 hours")
        
        # Execute handler
        result = lambda_module.handler(event=None, context=None)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Verify behavior - matches Lambda error message format
        assert result is None
        assert "Invalid or non-existent EC2 Instance ID: i-nonexistent" in captured.out
        assert "Error:" in captured.out
    
    @mock_aws
    def test_handler_with_stopped_instance(self, capsys, lambda_function_files):
        """Test handler behavior with stopped instance (non-actionable)"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create and stop an instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        ec2.stop_instances(InstanceIds=[instance_id])
        
        # Set environment variables
        self.set_env_vars(instance_id, "After 2 hours")
        
        # Execute handler
        result = lambda_module.handler(event=None, context=None)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Verify behavior - matches Lambda message format
        assert result is None
        assert "EC2 instance is not in running state" in captured.out
        assert "skipping any action" in captured.out
        assert "(current state:" in captured.out
    
    @mock_aws
    def test_handler_removes_tag_from_stopped_instance(self, capsys, lambda_function_files):
        """Test handler removes shutdown tag from a stopped instance that has one"""
        lambda_module = self.load_lambda_module(lambda_function_files)

        # Create and stop an instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)

        # Add a shutdown tag before stopping
        future_time = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2)
        tag_value = future_time.strftime('%a, %d %b %Y %H:%M:%S GMT')
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{'Key': 'mw-autoshutdown', 'Value': tag_value}]
        )

        ec2.stop_instances(InstanceIds=[instance_id])

        # Set environment variables
        self.set_env_vars(instance_id, "After 2 hours")

        # Execute handler
        lambda_module.handler(event=None, context=None)

        # Verify tag was removed
        captured = capsys.readouterr()
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}

        assert os.environ['TAG_TO_MONITOR'] not in tags
        assert f"Removed {os.environ['TAG_TO_MONITOR']} tag from EC2 instance {instance_id}" in captured.out

    @mock_aws
    def test_handler_with_terminated_instance(self, capsys, lambda_function_files):
        """Test handler behavior with terminated instance"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create and terminate an instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        ec2.terminate_instances(InstanceIds=[instance_id])
        
        # Set environment variables
        self.set_env_vars(instance_id, "After 2 hours")
        
        # Execute handler
        result = lambda_module.handler(event=None, context=None)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Verify behavior
        assert result is None
        assert "EC2 instance is not in running state" in captured.out
        assert "(current state:" in captured.out
        assert ("terminated" in captured.out or "shutting-down" in captured.out)
    
    @mock_aws
    def test_handler_never_shutdown_without_tag(self, capsys, lambda_function_files):
        """Test handler with 'Never' shutdown behavior and no existing tag"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        
        # Set environment variables with Never
        self.set_env_vars(instance_id, "Never")
        
        # Execute handler
        result = lambda_module.handler(event=None, context=None)
        
        # Capture output and verify
        captured = capsys.readouterr()
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
        
        assert result is None
        assert instance['State']['Name'] == 'running'
        assert os.environ['TAG_TO_MONITOR'] not in tags
        # Verify exact message format from Lambda
        assert "Shutdown behavior parameter is set to Never" in captured.out
        assert f"there is no '{os.environ['TAG_TO_MONITOR']}' tag" in captured.out
        assert "Skipping..." in captured.out
    
    @mock_aws
    def test_handler_adds_shutdown_tag_first_run(self, capsys, lambda_function_files):
        """Test handler adds shutdown tag on first run with hour-based behavior"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        
        # Set environment variables
        self.set_env_vars(instance_id, "After 2 hours")
        
        # Execute handler
        lambda_module.handler(event=None, context=None)
        
        # Capture output and verify
        captured = capsys.readouterr()
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
        
        # Verify tag was added
        assert os.environ['TAG_TO_MONITOR'] in tags
        # Verify exact message format from Lambda
        assert f"Adding the tag {os.environ['TAG_TO_MONITOR']} with value" in captured.out
        assert "EC2 instance is set to stop after" in captured.out
        assert "minutes" in captured.out
        
        # Verify tag has correct format
        tag_value = tags[os.environ['TAG_TO_MONITOR']]
        shutdown_time = datetime.strptime(tag_value, '%a, %d %b %Y %H:%M:%S GMT')
        time_diff = (shutdown_time - datetime.now(UTC).replace(tzinfo=None)).total_seconds()
        assert 7000 < time_diff < 7300  # Should be approximately 2 hours
    
    @mock_aws
    def test_handler_respects_future_shutdown_tag(self, capsys, lambda_function_files):
        """Test handler respects existing future shutdown tag"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)

        # Set environment variables (ensures TAG_TO_MONITOR exists deterministically)
        self.set_env_vars(instance_id, "After 1 hour")
        
        # Add future shutdown tag
        future_time = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=3)
        tag_value = future_time.strftime('%a, %d %b %Y %H:%M:%S GMT')
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{'Key': os.environ['TAG_TO_MONITOR'], 'Value': tag_value}]
        )
        
        # Execute handler
        lambda_module.handler(event=None, context=None)
        
        # Capture output and verify
        captured = capsys.readouterr()
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        
        # Instance should still be running
        assert instance['State']['Name'] == 'running'
        # Verify exact message format from Lambda
        assert "No action needed." in captured.out
        assert f"EC2 instance {instance_id} will shut down at" in captured.out
        assert "Remaining minutes:" in captured.out
    
    @mock_aws
    def test_handler_stops_instance_when_time_reached(self, capsys, monkeypatch, lambda_function_files):
        """Test handler stops instance when shutdown time is reached"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        
        # Set environment variables FIRST (deterministic TAG_TO_MONITOR)
        self.set_env_vars(instance_id, "After 2 hours")

        # Construct a non-stale shutdown time: AFTER LaunchTime but BEFORE "now" (frozen)
        launch_time = self._get_launch_time_naive(ec2, instance_id)
        shutdown_time = launch_time + timedelta(seconds=5)
        tag_value = shutdown_time.strftime('%a, %d %b %Y %H:%M:%S GMT')

        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{'Key': os.environ['TAG_TO_MONITOR'], 'Value': tag_value}]
        )
        
        # Freeze lambda "now" to after shutdown_time to trigger shutdown
        frozen_now = shutdown_time + timedelta(minutes=1)
        self._freeze_lambda_now(monkeypatch, lambda_module, frozen_now)
        
        # Execute handler
        lambda_module.handler(event=None, context=None)
        
        # Capture output and verify
        captured = capsys.readouterr()
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
        
        # Verify instance was stopped and tag removed
        assert instance['State']['Name'] in ['stopping', 'stopped']
        assert os.environ['TAG_TO_MONITOR'] not in tags
        # Verify exact message format from Lambda
        assert f"Stopping EC2 instance {instance_id}" in captured.out
        assert f"EC2 instance {instance_id} has been stopped" in captured.out
        assert f"The tag {os.environ['TAG_TO_MONITOR']} has been removed from EC2 instance {instance_id}" in captured.out
    
    @mock_aws
    def test_handler_with_custom_tag_name(self, capsys, monkeypatch, lambda_function_files):
        """Test handler with custom tag name (not the default mw-autoshutdown)"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        
        # Set environment variables with custom tag
        custom_tag = 'CustomShutdownTag'
        self.set_env_vars(instance_id, "After 3 hours", custom_tag)
        
        # Execute handler - should add tag
        lambda_module.handler(event=None, context=None)
        
        # Verify custom tag was added
        response = ec2.describe_instances(InstanceIds=[instance_id])
        tags = {tag['Key']: tag['Value']
                for tag in response['Reservations'][0]['Instances'][0].get('Tags', [])}
        
        assert custom_tag in tags
        
        # Now force a due shutdown tag that is NOT stale:
        # shutdown_time must be after LaunchTime, and we freeze now after it.
        launch_time = self._get_launch_time_naive(ec2, instance_id)
        shutdown_time = launch_time + timedelta(seconds=5)
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{'Key': custom_tag, 'Value': shutdown_time.strftime('%a, %d %b %Y %H:%M:%S GMT')}]
        )
        
        # Clear output
        capsys.readouterr()
        
        # Freeze lambda "now" so shutdown triggers
        frozen_now = shutdown_time + timedelta(minutes=1)
        self._freeze_lambda_now(monkeypatch, lambda_module, frozen_now)
        
        # Execute handler again - should stop and remove custom tag
        lambda_module.handler(event=None, context=None)
        
        captured = capsys.readouterr()
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        tags_after = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
        
        assert instance['State']['Name'] in ['stopping', 'stopped']
        assert custom_tag not in tags_after
        assert f"Stopping EC2 instance {instance_id}" in captured.out
    
    @pytest.mark.parametrize("config_string,expected_hours", [
        ("After 1 hour", 1),   # Singular
        ("After 2 hours", 2),  # Plural
        ("After 5 hours", 5),
        ("After 12 hours", 12),
        ("After 24 hours", 24)
    ])
    @mock_aws
    def test_handler_with_different_hour_values(self, capsys, config_string, expected_hours, lambda_function_files):
        """Test handler with various hour configurations from CloudFormation AllowedValues"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create new instance for each test
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        
        # Set environment variables
        self.set_env_vars(instance_id, config_string)
        
        # Execute handler
        lambda_module.handler(event=None, context=None)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Verify tag was set with correct time
        response = ec2.describe_instances(InstanceIds=[instance_id])
        tags = {tag['Key']: tag['Value']
                for tag in response['Reservations'][0]['Instances'][0].get('Tags', [])}
        
        assert os.environ['TAG_TO_MONITOR'] in tags, f"Tag should be added for {config_string}"
        
        # Parse and verify the shutdown time
        tag_value = tags[os.environ['TAG_TO_MONITOR']]
        shutdown_time = datetime.strptime(tag_value, '%a, %d %b %Y %H:%M:%S GMT')
        time_diff_seconds = (shutdown_time - datetime.now(UTC).replace(tzinfo=None)).total_seconds()
        expected_seconds = expected_hours * 3600
        
        # Allow 5 minute tolerance
        assert abs(time_diff_seconds - expected_seconds) < 300, \
            f"For {config_string}, expected ~{expected_seconds}s, got {time_diff_seconds}s"
        
        # Verify output mentions minutes
        assert "EC2 instance is set to stop after" in captured.out
        assert "minutes" in captured.out
    
    @mock_aws
    def test_handler_preserves_other_tags(self, capsys, monkeypatch, lambda_function_files):
        """Test handler preserves other tags when stopping instance"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create instance with multiple tags
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        
        # Set environment variables FIRST (deterministic TAG_TO_MONITOR)
        self.set_env_vars(instance_id, "After 2 hours")

        # Construct a due, non-stale shutdown time
        launch_time = self._get_launch_time_naive(ec2, instance_id)
        shutdown_time = launch_time + timedelta(seconds=5)
        tag_value = shutdown_time.strftime('%a, %d %b %Y %H:%M:%S GMT')

        # Add multiple tags including shutdown tag
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[
                {'Key': os.environ['TAG_TO_MONITOR'], 'Value': tag_value},
                {'Key': 'Name', 'Value': 'TestInstance'},
                {'Key': 'Environment', 'Value': 'Testing'},
                {'Key': 'Owner', 'Value': 'TestUser'}
            ]
        )
        
        # Freeze lambda "now" to after shutdown_time
        frozen_now = shutdown_time + timedelta(minutes=1)
        self._freeze_lambda_now(monkeypatch, lambda_module, frozen_now)
        
        # Execute handler - should stop and remove only shutdown tag
        lambda_module.handler(event=None, context=None)
        
        # Verify other tags preserved
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
        
        assert instance['State']['Name'] in ['stopping', 'stopped']
        assert os.environ['TAG_TO_MONITOR'] not in tags
        assert tags.get('Name') == 'TestInstance'
        assert tags.get('Environment') == 'Testing'
        assert tags.get('Owner') == 'TestUser'
    
    @mock_aws
    def test_handler_respects_never_with_existing_tag(self, capsys, monkeypatch, lambda_function_files):
        """Test that 'Never' shutdown behavior still checks existing tags"""
        lambda_module = self.load_lambda_module(lambda_function_files)
        
        # Create instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)
        
        # Set environment variables FIRST (deterministic TAG_TO_MONITOR)
        self.set_env_vars(instance_id, "Never")
        
        # Add a due, non-stale shutdown tag
        launch_time = self._get_launch_time_naive(ec2, instance_id)
        shutdown_time = launch_time + timedelta(seconds=5)
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{'Key': os.environ['TAG_TO_MONITOR'], 'Value': shutdown_time.strftime('%a, %d %b %Y %H:%M:%S GMT')}]
        )
        
        # Freeze lambda "now" so shutdown triggers
        frozen_now = shutdown_time + timedelta(minutes=1)
        self._freeze_lambda_now(monkeypatch, lambda_module, frozen_now)
        
        # Execute handler - should still stop because tag exists
        lambda_module.handler(event=None, context=None)
        
        # Capture output and verify
        captured = capsys.readouterr()
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
        
        # Should stop the instance because tag exists and time is past
        assert instance['State']['Name'] in ['stopping', 'stopped']
        assert os.environ['TAG_TO_MONITOR'] not in tags
        assert f"Stopping EC2 instance {instance_id}" in captured.out

    @mock_aws
    def test_handler_ignores_stale_shutdown_tag(self, capsys, lambda_function_files):
        """
        Test handler ignores a stale shutdown tag.

        A stale tag is one where the shutdown_time is <= instance LaunchTime,
        which can happen if the instance was restarted after a previously scheduled shutdown time.
        In this case, the Lambda should take no action and must not stop the instance.
        """
        lambda_module = self.load_lambda_module(lambda_function_files)

        # Create instance
        ec2 = boto3.client('ec2', region_name='us-east-1')
        instance_id = self.create_instance(ec2)

        # Set environment variables FIRST (deterministic TAG_TO_MONITOR)
        self.set_env_vars(instance_id, "After 2 hours")

        # Create a stale shutdown tag: shutdown_time BEFORE LaunchTime
        launch_time = self._get_launch_time_naive(ec2, instance_id)
        stale_shutdown_time = launch_time - timedelta(minutes=1)
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{
                'Key': os.environ['TAG_TO_MONITOR'],
                'Value': stale_shutdown_time.strftime('%a, %d %b %Y %H:%M:%S GMT')
            }]
        )

        # Execute handler - should return early (no action)
        lambda_module.handler(event=None, context=None)

        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}

        # Instance should still be running and stale tag should not be deleted
        assert instance['State']['Name'] == 'running'
        assert os.environ['TAG_TO_MONITOR'] in tags

if __name__ == "__main__":
    pytest.main([__file__, '-sv'])
