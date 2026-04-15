"""
Copyright 2026 The MathWorks, Inc.

Unit tests for the Active Directory trigger Lambda (EventBridge -> Lambda -> SSM Automation).
Tests are extracted from the inline Lambda code in the CloudFormation template.
"""
import os
import sys
import importlib.util
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from moto import mock_aws

TEST_DIR = Path(__file__).parent
REPO_ROOT = TEST_DIR.parents[3]
YAML_FILE_PATH = TEST_DIR.parent / 'active-directory.yaml'

sys.path.insert(0, str(REPO_ROOT))
from aws.test_utils.lambda_test_fixtures import create_lambda_function_files_fixture

# Create the fixture using the factory
lambda_function_files = create_lambda_function_files_fixture(YAML_FILE_PATH)


class TestADJoinTriggerLambda:
    """Tests for the AD Join Trigger Lambda that starts SSM Automation for Windows instances."""

    def default_env(self):
        """Set minimal environment variables required by the Lambda."""
        os.environ['AUTOMATION_DOCUMENT_NAME'] = 'MW-ADDomainJoin-doc'
        os.environ['AUTOMATION_ASSUME_ROLE_ARN'] = 'arn:aws:iam::123456789012:role/MW/SSMAutomationRole'
        os.environ['TARGET_VPC_ID'] = 'vpc-1234567890abcdef0'

    def make_event(self, instance_id=None, source='aws.ec2', detail_type='EC2 Instance State-change Notification'):
        """Helper to craft an incoming EventBridge event."""
        event = {
            'version': '0',
            'id': 'abcd-1234',
            'detail-type': detail_type,
            'source': source,
            'account': '123456789012',
            'time': '2026-02-13T12:00:00Z',
            'region': 'us-east-1',
            'resources': [],
            'detail': {
                'state': 'running'
            }
        }
        if instance_id:
            event['detail']['instance-id'] = instance_id
        return event

    def make_instance(
        self,
        instance_id='i-0123456789abcdef0',
        vpc_id='vpc-1234567890abcdef0',
        platform_details='Windows',
        product_tag='mathworks-matlab-windows',
        join_tag_value='Pending', 
    ):
        """Return an instance dict shaped like EC2 DescribeInstances output."""
        tags = []
        if product_tag is not None:
            tags.append({'Key': 'mw-ProductID', 'Value': product_tag})
        if join_tag_value is not None:
            tags.append({'Key': 'mw-JoinToActiveDirectory', 'Value': join_tag_value})
        return {
            'InstanceId': instance_id,
            'VpcId': vpc_id,
            'PlatformDetails': platform_details,
            'Platform': 'windows' if platform_details.lower().startswith('windows') else 'linux',
            'Tags': tags
        }

    def load_lambda_with_mocks(self, lambda_function_files, mock_ec2_client, mock_ssm_client):
        """
        Import the Lambda module from the extracted temp file while patching boto3.client so the
        module-level 'ec2' and 'ssm' variables are your mocks.
        """
        _, temp_path, _ = lambda_function_files

        def client_side_effect(service_name, **kwargs):
            if service_name == 'ec2':
                return mock_ec2_client
            if service_name == 'ssm':
                return mock_ssm_client
            # If any other service is requested, return a simple MagicMock
            return MagicMock()

        with patch('boto3.client') as mock_boto_client:
            mock_boto_client.side_effect = client_side_effect

            spec = importlib.util.spec_from_file_location("ad_lambda_module", temp_path)
            ad_lambda_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ad_lambda_module)

        # Safety: overwrite in case the module grabbed the clients during import
        ad_lambda_module.ec2 = mock_ec2_client
        ad_lambda_module.ssm = mock_ssm_client
        return ad_lambda_module

    def setup_ec2_mock(self, instance_dict=None, raise_error=False):
        """
        Create a mock EC2 client that supports describe_instances with either:
          - a successful response containing the provided instance dict
          - or a response with no instances
          - or raises an exception if raise_error=True
        """
        mock_ec2 = MagicMock()

        if raise_error:
            mock_ec2.describe_instances.side_effect = Exception("EC2 error during DescribeInstances")
            return mock_ec2

        if instance_dict is None:
            # No instance found path
            mock_ec2.describe_instances.return_value = {
                'Reservations': []
            }
        else:
            # Successful instance fetch path
            mock_ec2.describe_instances.return_value = {
                'Reservations': [
                    {
                        'Instances': [instance_dict]
                    }
                ]
            }
        return mock_ec2

    def setup_ssm_mock(self, behavior='success'):
        """
        Create a mock SSM client.
        behavior:
          - 'success': start_automation_execution succeeds
          - 'doc_not_found': raises AutomationDefinitionNotFoundException
          - 'error': raises generic Exception
        """
        mock_ssm = MagicMock()

        # Build out a realistic exceptions namespace
        class AutomationDefinitionNotFoundException(Exception):
            pass

        mock_ssm.exceptions = SimpleNamespace(
            AutomationDefinitionNotFoundException=AutomationDefinitionNotFoundException
        )

        if behavior == 'success':
            mock_ssm.start_automation_execution.return_value = {
                'AutomationExecutionId': 'exec-123'
            }
        elif behavior == 'doc_not_found':
            mock_ssm.start_automation_execution.side_effect = \
                mock_ssm.exceptions.AutomationDefinitionNotFoundException("Document not found")
        else:
            mock_ssm.start_automation_execution.side_effect = Exception("Generic SSM error")

        return mock_ssm

    # -------------------
    # Test Cases
    # -------------------

    @mock_aws
    def test_ignores_non_matching_event(self, lambda_function_files):
        # arrange
        self.default_env()
        mock_ec2 = self.setup_ec2_mock()  # won't be used
        mock_ssm = self.setup_ssm_mock()  # won't be used
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(source='aws.s3')
        event2 = self.make_event(instance_id=None)
        # act
        result = mod.handler(event, context=None)
        result2 = mod.handler(event2, context=None)
        # assert
        assert result == {'started': [], 'skipped': []}
        mock_ssm.start_automation_execution.assert_not_called()
        assert result2 == {'started': [], 'skipped': []}
        mock_ssm.start_automation_execution.assert_not_called()

    @mock_aws
    def test_skips_when_reservation_has_no_instances(self, lambda_function_files):
        # arrange
        self.default_env()
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {'Reservations': [{'Instances': []}]}
        mock_ssm = self.setup_ssm_mock()
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id='i-nonexistent')
        # act
        result = mod.handler(event, context=None)
        # assert
        assert result['started'] == []
        assert result['skipped'][0]['instance'] == 'i-nonexistent'
        assert 'DescribeInstances returned no instance' in result['skipped'][0]['reason']
        mock_ssm.start_automation_execution.assert_not_called()

    @mock_aws
    def test_skips_when_instance_not_found(self, lambda_function_files):
        # arrange
        self.default_env()
        mock_ec2 = self.setup_ec2_mock(instance_dict=None)  # no instance
        mock_ssm = self.setup_ssm_mock()
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id='i-doesnotexist')
        # act
        result = mod.handler(event, context=None)
        # assert
        assert len(result['started']) == 0
        assert len(result['skipped']) == 1
        assert result['skipped'][0]['instance'] == 'i-doesnotexist'
        assert 'DescribeInstances returned no instance' in result['skipped'][0]['reason']
        mock_ssm.start_automation_execution.assert_not_called()

    @mock_aws
    def test_skips_when_not_in_target_vpc(self, lambda_function_files):
        # arrange
        self.default_env()
        inst = self.make_instance(vpc_id='vpc-different')
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst)
        mock_ssm = self.setup_ssm_mock()
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        assert result['started'] == []
        assert result['skipped'][0]['reason'] == 'Not in target VPC'
        mock_ssm.start_automation_execution.assert_not_called()

    @mock_aws
    def test_skips_when_not_windows(self, lambda_function_files):
        # arrange
        self.default_env()
        inst = self.make_instance(platform_details='Linux/UNIX')
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst)
        mock_ssm = self.setup_ssm_mock()
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        assert result['started'] == []
        assert result['skipped'][0]['reason'] == 'Not Windows'
        mock_ssm.start_automation_execution.assert_not_called()

    @mock_aws
    def test_skips_when_product_tag_missing_or_wrong(self, lambda_function_files):
        # arrange
        self.default_env()
        # No mw-ProductID tag at all
        inst_no_tag = self.make_instance(product_tag=None)
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst_no_tag)
        mock_ssm = self.setup_ssm_mock()
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst_no_tag['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        assert result['started'] == []
        assert 'Unsupported product or join state' in result['skipped'][0]['reason']
        mock_ssm.start_automation_execution.assert_not_called()

        # arrange (wrong product tag)
        inst_wrong_tag = self.make_instance(product_tag='some-other-product')
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst_wrong_tag)
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst_wrong_tag['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        assert result['started'] == []
        assert 'Unsupported product or join state' in result['skipped'][0]['reason']
        mock_ssm.start_automation_execution.assert_not_called()

    @mock_aws
    def test_starts_automation_when_all_checks_pass(self, lambda_function_files):
        # arrange
        self.default_env()
        inst = self.make_instance(
            vpc_id=os.environ['TARGET_VPC_ID'],
            platform_details='Windows',
            product_tag='mathworks-matlab-windows',
            join_tag_value='Pending'
        )
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst)
        mock_ssm = self.setup_ssm_mock(behavior='success')
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        mock_ssm.start_automation_execution.assert_called_once()
        call_kwargs = mock_ssm.start_automation_execution.call_args.kwargs
        assert call_kwargs['DocumentName'] == os.environ['AUTOMATION_DOCUMENT_NAME']
        assert call_kwargs['Parameters'] == {
            'InstanceId': [inst['InstanceId']],
            'AutomationAssumeRole': [os.environ['AUTOMATION_ASSUME_ROLE_ARN']]
        }
        assert result['started'] == [inst['InstanceId']]
        assert result['skipped'] == []

    @mock_aws
    def test_documents_not_found_path(self, lambda_function_files):
        # arrange
        self.default_env()
        inst = self.make_instance(
            vpc_id=os.environ['TARGET_VPC_ID'],
            platform_details='Windows',
            product_tag='mathworks-matlab-windows',
            join_tag_value='Pending'
        )
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst)
        mock_ssm = self.setup_ssm_mock(behavior='doc_not_found')
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        assert result['started'] == []
        assert len(result['skipped']) == 1
        assert result['skipped'][0]['reason'] == 'Document not found'

    @mock_aws
    def test_generic_exception_path(self, lambda_function_files):
        # arrange
        self.default_env()
        inst = self.make_instance(
            vpc_id=os.environ['TARGET_VPC_ID'],
            platform_details='Windows',
            product_tag='mathworks-matlab-windows',
            join_tag_value='Pending'
        )
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst)
        mock_ssm = self.setup_ssm_mock(behavior='error')
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        assert result['started'] == []
        assert 'Generic SSM error' in result['skipped'][0]['reason']

    @mock_aws
    @pytest.mark.parametrize("case_variant", [
        "mathworks-matlab-windows",
        "MathWorks-MATLAB-Windows",
        "MATHWORKS-MATLAB-WINDOWS",
    ])
    def test_product_tag_case_insensitive(self, lambda_function_files, case_variant):
        # arrange
        self.default_env()
        inst = self.make_instance(
            vpc_id=os.environ['TARGET_VPC_ID'],
            platform_details='Windows',
            product_tag=case_variant,
            join_tag_value='Pending' 
        )
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst)
        mock_ssm = self.setup_ssm_mock(behavior='success')
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        mock_ssm.start_automation_execution.assert_called_once()
        assert result['started'] == [inst['InstanceId']]

    @mock_aws
    def test_skips_when_join_already_completed(self, lambda_function_files):
        # arrange
        self.default_env()
        inst = self.make_instance(
            vpc_id=os.environ['TARGET_VPC_ID'],
            platform_details='Windows',
            product_tag='mathworks-matlab-windows',
            join_tag_value='Join-complete'
        )
        mock_ec2 = self.setup_ec2_mock(instance_dict=inst)
        mock_ssm = self.setup_ssm_mock()
        mod = self.load_lambda_with_mocks(lambda_function_files, mock_ec2, mock_ssm)
        event = self.make_event(instance_id=inst['InstanceId'])
        # act
        result = mod.handler(event, context=None)
        # assert
        assert result['started'] == []
        assert 'Unsupported product or join state' in result['skipped'][0]['reason']
        mock_ssm.start_automation_execution.assert_not_called()