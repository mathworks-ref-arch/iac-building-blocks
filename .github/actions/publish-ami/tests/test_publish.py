# Copyright 2026 The MathWorks, Inc.
"""Tests for publish.py with stubbed AWS clients (no AWS calls)."""
import itertools
import json
import os
import tempfile
import unittest
from unittest import mock

from botocore.stub import ANY

from helpers import CALLER, OTHER, SRC_AMI, SRC_REGION, StubbedClients, image

import publish

COPY_FILTERS = [
    {'Name': 'tag:mw-release-pipeline', 'Values': ['public-builds']},
    {'Name': 'tag:mw-source-ami', 'Values': [SRC_AMI]},
]
RUN_ENV = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '42'}


class PublishTestCase(unittest.TestCase):

    def setUp(self):
        self.aws = StubbedClients()
        patches = [
            mock.patch.object(publish, 'get_client', side_effect=self.aws.get_client),
            mock.patch.object(publish.time, 'sleep'),
            mock.patch.object(publish.time, 'monotonic', side_effect=itertools.count(0, 50)),
            mock.patch.dict(os.environ, RUN_ENV),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.aws.assert_done()

    def expect_source(self, owner=CALLER):
        self.aws.stub('ec2', SRC_REGION).add_response(
            'describe_images', {'Images': [image(SRC_AMI, owner=owner)]}, {'ImageIds': [SRC_AMI]})
        self.aws.stub('sts', SRC_REGION).add_response(
            'get_caller_identity', {'UserId': 'u', 'Account': CALLER, 'Arn': f'arn:aws:sts::{CALLER}:assumed-role/test/session'}, {})

    def expect_existing(self, region, images):
        self.aws.stub('ec2', region).add_response(
            'describe_images', {'Images': images}, {'Owners': ['self'], 'Filters': COPY_FILTERS})

    def expect_copy(self, region, new_ami, tags=ANY):
        specs = ANY if tags is ANY else [
            {'ResourceType': 'image', 'Tags': tags},
            {'ResourceType': 'snapshot', 'Tags': tags},
        ]
        self.aws.stub('ec2', region).add_response('copy_image', {'ImageId': new_ami}, {
            'Description': f'[Copied {SRC_AMI} from {SRC_REGION}]',
            'Name': ANY,
            'SourceImageId': SRC_AMI,
            'SourceRegion': SRC_REGION,
            'TagSpecifications': specs,
        })

    def expect_state(self, region, ami, state, **kwargs):
        self.aws.stub('ec2', region).add_response(
            'describe_images', {'Images': [image(ami, state=state, **kwargs)]}, {'ImageIds': [ami]})

    def expect_public(self, region, ami, snaps=('snap-0aaa',)):
        stub = self.aws.stub('ec2', region)
        stub.add_response('modify_image_attribute', {}, {
            'ImageId': ami, 'LaunchPermission': {'Add': [{'Group': 'all'}]}})
        for snap in snaps:
            stub.add_response('modify_snapshot_attribute', {}, {
                'SnapshotId': snap, 'CreateVolumePermission': {'Add': [{'Group': 'all'}]}})


class TestMockMode(unittest.TestCase):

    def test_bare_region_map_with_placeholders(self):
        with tempfile.NamedTemporaryFile('r', suffix='.out') as out, \
                mock.patch.dict(os.environ, {'GITHUB_OUTPUT': out.name}):
            publish.main(['--ami-id', SRC_AMI, '--src-region', SRC_REGION,
                          '--dest-regions', 'us-east-1, eu-west-1', '--version', 'R2026b',
                          '--refarch-type', 'matlab-linux', '--test-mode'])
            lines = dict(line.rstrip('\n').split('=', 1) for line in out.readlines())
        region_map = json.loads(lines['region_map_json'])
        self.assertNotIn('RegionMap', region_map)
        self.assertEqual(len(region_map), len(publish.TEMPLATE_REGIONS))
        self.assertEqual(region_map['us-east-1'], {'AMI': SRC_AMI})
        self.assertEqual(region_map['eu-west-1'], {'AMI': 'ami-test-eu-west-1'})
        self.assertEqual(region_map['us-west-2'], {'AMI': publish.PLACEHOLDER})
        self.assertEqual(json.loads(lines['copies_json']), [])


class TestCopy(PublishTestCase):

    def test_same_account_uses_source_in_source_region(self):
        self.expect_source(owner=CALLER)
        self.expect_existing('eu-west-1', [])
        self.expect_copy('eu-west-1', 'ami-0new')
        self.expect_state('eu-west-1', 'ami-0new', 'available')
        region_map, copies = publish.publish(SRC_AMI, SRC_REGION, ['us-east-1', 'eu-west-1'],
                                             'R2026b', 'matlab-linux')
        self.assertEqual(region_map['us-east-1'], {'AMI': SRC_AMI})
        self.assertEqual(region_map['eu-west-1'], {'AMI': 'ami-0new'})
        self.assertEqual(region_map['ap-east-1'], {'AMI': publish.PLACEHOLDER})
        self.assertEqual([c['state'] for c in copies], ['source', 'created'])

    def test_cross_account_copies_source_region_too(self):
        self.expect_source(owner=OTHER)
        for region, ami in (('us-east-1', 'ami-0east'), ('eu-west-1', 'ami-0west')):
            self.expect_existing(region, [])
            self.expect_copy(region, ami)
        for region, ami in (('us-east-1', 'ami-0east'), ('eu-west-1', 'ami-0west')):
            self.expect_state(region, ami, 'available')
        region_map, copies = publish.publish(SRC_AMI, SRC_REGION, ['us-east-1', 'eu-west-1'],
                                             'R2026b', 'matlab-linux')
        self.assertEqual(region_map['us-east-1'], {'AMI': 'ami-0east'})
        self.assertEqual([c['state'] for c in copies], ['created', 'created'])

    def test_tags_on_image_and_snapshot(self):
        common = [
            {'Key': 'mw-release-pipeline', 'Value': 'public-builds'},
            {'Key': 'mw-source-ami', 'Value': SRC_AMI},
            {'Key': 'mw-release', 'Value': 'R2026b'},
            {'Key': 'mw-refarch-type', 'Value': 'ps-linux'},
            {'Key': 'mw-github-run', 'Value': 'owner/repo/42'},
        ]
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [])
        self.expect_copy('eu-west-1', 'ami-0test', tags=common + [{'Key': 'mw-release-test', 'Value': 'true'}])
        self.expect_state('eu-west-1', 'ami-0test', 'available')
        publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'ps-linux', make_public=False)

        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [])
        self.expect_copy('eu-west-1', 'ami-0rel', tags=common)
        self.expect_state('eu-west-1', 'ami-0rel', 'available')
        self.expect_public('eu-west-1', 'ami-0rel')
        publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'ps-linux', make_public=True)

    def test_make_public_covers_every_snapshot(self):
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [])
        self.expect_copy('eu-west-1', 'ami-0new')
        self.expect_state('eu-west-1', 'ami-0new', 'available', snaps=('snap-01', 'snap-02'))
        self.expect_public('eu-west-1', 'ami-0new', snaps=('snap-01', 'snap-02'))
        _, copies = publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'matlab-linux',
                                    make_public=True)
        self.assertEqual(copies[0]['snapshot_ids'], ['snap-01', 'snap-02'])


class TestReuse(PublishTestCase):

    def test_reuses_available_copy(self):
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [image('ami-0old', tags={'mw-release-pipeline': 'public-builds'})])
        self.expect_public('eu-west-1', 'ami-0old')
        region_map, copies = publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b',
                                             'matlab-linux', make_public=True)
        self.assertEqual(region_map['eu-west-1'], {'AMI': 'ami-0old'})
        self.assertEqual(copies[0]['state'], 'reused')

    def test_waits_for_pending_reused_copy(self):
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [image('ami-0old', state='pending')])
        self.expect_state('eu-west-1', 'ami-0old', 'pending')
        self.expect_state('eu-west-1', 'ami-0old', 'available')
        _, copies = publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'matlab-linux')
        self.assertEqual(copies[0], {'region': 'eu-west-1', 'ami_id': 'ami-0old',
                                     'snapshot_ids': ['snap-0aaa'], 'state': 'reused'})
        publish.time.sleep.assert_called_once_with(publish.POLL_SECONDS)

    def test_ignores_failed_copy(self):
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [image('ami-0bad', state='failed')])
        self.expect_copy('eu-west-1', 'ami-0new')
        self.expect_state('eu-west-1', 'ami-0new', 'available')
        _, copies = publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'matlab-linux')
        self.assertEqual(copies[0]['ami_id'], 'ami-0new')

    def test_never_publishes_a_test_copy(self):
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [image('ami-0test', tags={'mw-release-test': 'true'})])
        self.expect_copy('eu-west-1', 'ami-0new')
        self.expect_state('eu-west-1', 'ami-0new', 'available')
        self.expect_public('eu-west-1', 'ami-0new')
        _, copies = publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'matlab-linux',
                                    make_public=True)
        self.assertEqual(copies[0]['ami_id'], 'ami-0new')

    def test_prefers_available_over_pending(self):
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [
            image('ami-0pend', state='pending', created='2026-10-13T02:00:00.000Z'),
            image('ami-0ready', created='2026-10-13T01:00:00.000Z'),
        ])
        _, copies = publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'matlab-linux')
        self.assertEqual(copies[0]['ami_id'], 'ami-0ready')


class TestFailures(PublishTestCase):

    def test_deadline_expiry(self):
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [])
        self.expect_copy('eu-west-1', 'ami-0slow')
        self.expect_state('eu-west-1', 'ami-0slow', 'pending')
        self.expect_state('eu-west-1', 'ami-0slow', 'pending')
        with self.assertRaisesRegex(publish.PublishError, r'Timed out.*eu-west-1 \(ami-0slow\)'):
            publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'matlab-linux',
                            timeout_minutes=1)

    def test_failed_copy_names_region_and_ami(self):
        self.expect_source(owner=OTHER)
        self.expect_existing('eu-west-1', [])
        self.expect_copy('eu-west-1', 'ami-0bad')
        self.expect_state('eu-west-1', 'ami-0bad', 'failed', reason='Copy failed')
        with self.assertRaisesRegex(publish.PublishError, r'ami-0bad in eu-west-1 is failed\. Copy failed'):
            publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'matlab-linux')

    def test_missing_source_ami(self):
        self.aws.stub('ec2', SRC_REGION).add_response('describe_images', {'Images': []}, {'ImageIds': [SRC_AMI]})
        with self.assertRaisesRegex(publish.PublishError, 'not found'):
            publish.publish(SRC_AMI, SRC_REGION, ['eu-west-1'], 'R2026b', 'matlab-linux')

    def test_main_writes_no_output_on_failure(self):
        self.aws.stub('ec2', SRC_REGION).add_client_error('describe_images', 'UnauthorizedOperation')
        with tempfile.NamedTemporaryFile('r', suffix='.out') as out, \
                mock.patch.dict(os.environ, {'GITHUB_OUTPUT': out.name}):
            with self.assertRaises(SystemExit) as exit_info:
                publish.main(['--ami-id', SRC_AMI, '--src-region', SRC_REGION,
                              '--dest-regions', 'eu-west-1', '--version', 'R2026b',
                              '--refarch-type', 'matlab-linux'])
            self.assertEqual(exit_info.exception.code, 1)
            self.assertEqual(out.read(), '')


if __name__ == '__main__':
    unittest.main()
