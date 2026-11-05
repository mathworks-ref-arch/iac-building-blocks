# Copyright 2026 The MathWorks, Inc.
"""Tests for cleanup.py with stubbed AWS clients (no AWS calls)."""
import unittest
from unittest import mock

from helpers import StubbedClients, image

import cleanup

REGION = 'ap-northeast-3'
RUN = 'owner/repo/42'
FILTERS = [
    {'Name': 'tag:mw-release-test', 'Values': ['true']},
    {'Name': 'tag:mw-github-run', 'Values': [RUN]},
]
TEST_TAGS = {'mw-release-test': 'true', 'mw-github-run': RUN}


class CleanupTestCase(unittest.TestCase):

    def setUp(self):
        self.aws = StubbedClients()
        self.stub = self.aws.stub('ec2', REGION)
        for p in (mock.patch.object(cleanup, 'get_client', side_effect=self.aws.get_client),
                  mock.patch.object(cleanup.time, 'sleep')):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.aws.assert_done()

    def expect_images(self, images):
        self.stub.add_response('describe_images', {'Images': images}, {'Owners': ['self'], 'Filters': FILTERS})

    def expect_snapshots(self, snaps):
        self.stub.add_response('describe_snapshots', {'Snapshots': snaps}, {'OwnerIds': ['self'], 'Filters': FILTERS})

    def ec2(self):
        return self.aws.get_client('ec2', REGION)

    def test_removes_copies_and_verifies(self):
        self.expect_images([image('ami-0test', tags=TEST_TAGS, snaps=('snap-01',))])
        self.stub.add_response('deregister_image', {}, {'ImageId': 'ami-0test'})
        self.stub.add_response('delete_snapshot', {}, {'SnapshotId': 'snap-01'})
        self.expect_snapshots([])
        self.expect_images([])
        self.expect_snapshots([])
        cleanup.cleanup_region(self.ec2(), REGION, RUN)

    def test_refuses_untagged_image(self):
        self.expect_images([image('ami-0real', tags={'mw-github-run': RUN})])
        with self.assertRaisesRegex(cleanup.CleanupError, 'Refusing to touch ami-0real'):
            cleanup.cleanup_region(self.ec2(), REGION, RUN)

    def test_fails_when_something_is_left(self):
        self.expect_images([image('ami-0test', tags=TEST_TAGS, snaps=())])
        self.stub.add_response('deregister_image', {}, {'ImageId': 'ami-0test'})
        self.expect_snapshots([])
        self.expect_images([image('ami-0test', tags=TEST_TAGS, snaps=())])
        self.expect_snapshots([])
        with self.assertRaisesRegex(cleanup.CleanupError, 'Still present in ap-northeast-3: ami-0test'):
            cleanup.cleanup_region(self.ec2(), REGION, RUN)

    def test_deletes_leftover_snapshot_and_retries_in_use(self):
        self.expect_images([])
        self.expect_snapshots([{'SnapshotId': 'snap-0left', 'Tags': [{'Key': k, 'Value': v} for k, v in TEST_TAGS.items()]}])
        self.stub.add_client_error('delete_snapshot', 'InvalidSnapshot.InUse', expected_params={'SnapshotId': 'snap-0left'})
        self.stub.add_response('delete_snapshot', {}, {'SnapshotId': 'snap-0left'})
        self.expect_images([])
        self.expect_snapshots([])
        cleanup.cleanup_region(self.ec2(), REGION, RUN)
        cleanup.time.sleep.assert_called_once_with(cleanup.SNAPSHOT_RETRY_SECONDS)

    def test_rejects_wildcard_run(self):
        with self.assertRaises(SystemExit) as exit_info:
            cleanup.main(['--regions', REGION, '--github-run', 'owner/*'])
        self.assertEqual(exit_info.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
