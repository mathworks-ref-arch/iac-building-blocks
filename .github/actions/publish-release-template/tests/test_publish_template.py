# Copyright 2026 The MathWorks, Inc.
"""Unit tests for publish_template.py, using botocore's Stubber (no AWS calls)."""
import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

import boto3
from botocore.stub import Stubber

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import publish_template as pt  # noqa: E402

BUCKET = 'release-bucket'
KEY = 'R2026b/aws-matlab-template.json'
REPO = 'example-org/example-repo'
RUN_ID = 2000
BODY = b'{"AWSTemplateFormatVersion": "2010-09-09"}'
MD5 = hashlib.md5(BODY, usedforsecurity=False).hexdigest()
OLD_ETAG = '"0123456789abcdef0123456789abcdef"'


def put_params(**extra):
    params = {
        'Bucket': BUCKET,
        'Key': KEY,
        'Body': BODY,
        'ContentType': 'application/json',
        'Metadata': {pt.RUN_ID_KEY: str(RUN_ID), pt.REPOSITORY_KEY: REPO},
        'ACL': 'public-read',
    }
    params.update(extra)
    return params


def head_response(etag, metadata):
    return {'ETag': etag, 'Metadata': metadata}


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.s3 = boto3.client('s3', region_name='us-east-1',
                               aws_access_key_id='testing', aws_secret_access_key='testing')
        self.stub = Stubber(self.s3)
        self.stub.activate()

    def tearDown(self):
        self.stub.deactivate()

    def expect_exists(self):
        self.stub.add_client_error('put_object', service_error_code='PreconditionFailed',
                                   http_status_code=412, expected_params=put_params(IfNoneMatch='*'))

    def expect_replace(self, metadata):
        self.expect_exists()
        self.stub.add_response('head_object', head_response(OLD_ETAG, metadata),
                               {'Bucket': BUCKET, 'Key': KEY})
        self.stub.add_response('put_object', {'ETag': f'"{MD5}"', 'VersionId': 'v2'},
                               put_params(IfMatch=OLD_ETAG))

    def run_publish(self, acl='public-read'):
        return pt.publish(self.s3, BODY, BUCKET, KEY, acl, REPO, RUN_ID)

    def test_new_key_is_created(self):
        self.stub.add_response('put_object', {'ETag': f'"{MD5}"', 'VersionId': 'v1'},
                               put_params(IfNoneMatch='*'))
        self.assertEqual(self.run_publish(), ('created', 'v1'))
        self.stub.assert_no_pending_responses()

    def test_object_without_metadata_is_replaced(self):
        self.expect_replace({})
        self.assertEqual(self.run_publish(), ('replaced', 'v2'))
        self.stub.assert_no_pending_responses()

    def test_older_run_is_replaced(self):
        self.expect_replace({pt.RUN_ID_KEY: str(RUN_ID - 1), pt.REPOSITORY_KEY: REPO})
        self.assertEqual(self.run_publish(), ('replaced', 'v2'))

    def test_same_run_is_replaced_on_rerun(self):
        self.expect_replace({pt.RUN_ID_KEY: str(RUN_ID), pt.REPOSITORY_KEY: REPO})
        self.assertEqual(self.run_publish(), ('replaced', 'v2'))

    def test_newer_run_of_other_repository_is_replaced(self):
        self.expect_replace({pt.RUN_ID_KEY: str(RUN_ID + 1), pt.REPOSITORY_KEY: 'example-org/other'})
        self.assertEqual(self.run_publish(), ('replaced', 'v2'))

    def test_non_integer_run_id_is_replaced(self):
        self.expect_replace({pt.RUN_ID_KEY: 'unknown', pt.REPOSITORY_KEY: REPO})
        self.assertEqual(self.run_publish(), ('replaced', 'v2'))

    def test_newer_run_is_refused(self):
        self.expect_exists()
        self.stub.add_response('head_object',
                               head_response(OLD_ETAG, {pt.RUN_ID_KEY: str(RUN_ID + 1),
                                                        pt.REPOSITORY_KEY: REPO}),
                               {'Bucket': BUCKET, 'Key': KEY})
        with self.assertRaisesRegex(pt.PublishError, f'newer run {RUN_ID + 1}'):
            self.run_publish()
        self.stub.assert_no_pending_responses()

    def test_change_during_replace_fails(self):
        self.expect_exists()
        self.stub.add_response('head_object', head_response(OLD_ETAG, {}), {'Bucket': BUCKET, 'Key': KEY})
        self.stub.add_client_error('put_object', service_error_code='PreconditionFailed',
                                   http_status_code=412, expected_params=put_params(IfMatch=OLD_ETAG))
        with self.assertRaisesRegex(pt.PublishError, 'changed while publishing'):
            self.run_publish()

    def test_other_errors_are_raised(self):
        self.stub.add_client_error('put_object', service_error_code='AccessDenied',
                                   http_status_code=403, expected_params=put_params(IfNoneMatch='*'))
        with self.assertRaises(pt.ClientError):
            self.run_publish()

    def test_acl_is_passed_through(self):
        self.stub.add_response('put_object', {'ETag': f'"{MD5}"'},
                               put_params(IfNoneMatch='*', ACL='private'))
        self.assertEqual(self.run_publish(acl='private'), ('created', ''))

    def test_empty_acl_sets_none(self):
        params = put_params(IfNoneMatch='*')
        del params['ACL']
        self.stub.add_response('put_object', {'ETag': f'"{MD5}"'}, params)
        self.assertEqual(self.run_publish(acl=''), ('created', ''))

    def test_verify_accepts_own_write(self):
        self.stub.add_response('head_object',
                               head_response(f'"{MD5}"', {pt.RUN_ID_KEY: str(RUN_ID)}),
                               {'Bucket': BUCKET, 'Key': KEY})
        pt.verify(self.s3, BUCKET, KEY, MD5, RUN_ID)

    def test_verify_fails_on_etag_mismatch(self):
        self.stub.add_response('head_object',
                               head_response(OLD_ETAG, {pt.RUN_ID_KEY: str(RUN_ID)}),
                               {'Bucket': BUCKET, 'Key': KEY})
        with self.assertRaisesRegex(pt.PublishError, 'has ETag'):
            pt.verify(self.s3, BUCKET, KEY, MD5, RUN_ID)

    def test_verify_fails_on_other_writer(self):
        self.stub.add_response('head_object',
                               head_response(f'"{MD5}"', {pt.RUN_ID_KEY: str(RUN_ID + 1)}),
                               {'Bucket': BUCKET, 'Key': KEY})
        with self.assertRaisesRegex(pt.PublishError, f'written by run {RUN_ID + 1}'):
            pt.verify(self.s3, BUCKET, KEY, MD5, RUN_ID)


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.template = os.path.join(self.tmp.name, 'template.json')
        with open(self.template, 'wb') as fh:
            fh.write(BODY)
        self.output = os.path.join(self.tmp.name, 'github_output')
        self.s3 = boto3.client('s3', region_name='us-east-1',
                               aws_access_key_id='testing', aws_secret_access_key='testing')
        self.stub = Stubber(self.s3)
        self.stub.activate()
        env = {'GITHUB_OUTPUT': self.output, 'GITHUB_RUN_ID': str(RUN_ID), 'GITHUB_REPOSITORY': REPO}
        argv = ['publish_template.py', '--template-file', self.template, '--bucket', BUCKET, '--key', KEY]
        self.patches = [mock.patch.dict(os.environ, env), mock.patch.object(sys, 'argv', argv),
                        mock.patch.object(pt.boto3, 'client', return_value=self.s3)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.stub.deactivate()
        self.tmp.cleanup()

    def test_outputs_written(self):
        self.stub.add_response('put_object', {'ETag': f'"{MD5}"', 'VersionId': 'v1'},
                               put_params(IfNoneMatch='*'))
        self.stub.add_response('head_object',
                               head_response(f'"{MD5}"', {pt.RUN_ID_KEY: str(RUN_ID)}),
                               {'Bucket': BUCKET, 'Key': KEY})
        pt.main()
        with open(self.output) as fh:
            lines = fh.read().splitlines()
        self.assertEqual(lines, [f'template_url=https://{BUCKET}.s3.amazonaws.com/{KEY}',
                                 'version_id=v1', 'result=created'])

    def test_refusal_exits_nonzero(self):
        self.stub.add_client_error('put_object', service_error_code='PreconditionFailed',
                                   http_status_code=412, expected_params=put_params(IfNoneMatch='*'))
        self.stub.add_response('head_object',
                               head_response(OLD_ETAG, {pt.RUN_ID_KEY: str(RUN_ID + 1),
                                                        pt.REPOSITORY_KEY: REPO}),
                               {'Bucket': BUCKET, 'Key': KEY})
        with self.assertRaises(SystemExit) as cm:
            pt.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertFalse(os.path.exists(self.output))


if __name__ == '__main__':
    unittest.main()
