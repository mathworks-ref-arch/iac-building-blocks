# Copyright 2026 The MathWorks, Inc.
"""Shared fixtures for the publish-ami tests: stubbed boto3 clients and image shapes."""
import os
import sys

import boto3
from botocore.stub import Stubber

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

CALLER = '111111111111'
OTHER = '222222222222'
SRC_AMI = 'ami-0source0000000000'
SRC_REGION = 'us-east-1'


class StubbedClients:
    """Creates one stubbed client per (service, region) and checks they were fully used."""

    def __init__(self):
        self.clients = {}
        self.stubbers = {}

    def stub(self, service, region):
        key = (service, region)
        if key not in self.clients:
            client = boto3.client(
                service, region_name=region,
                aws_access_key_id='testing', aws_secret_access_key='testing',
            )
            stubber = Stubber(client)
            stubber.activate()
            self.clients[key] = client
            self.stubbers[key] = stubber
        return self.stubbers[key]

    def get_client(self, service, region):
        return self.clients[(service, region)]

    def assert_done(self):
        for stubber in self.stubbers.values():
            stubber.assert_no_pending_responses()


def image(ami, state='available', owner=CALLER, tags=None, snaps=('snap-0aaa',),
          created='2026-10-13T00:00:00.000Z', reason=None):
    result = {
        'ImageId': ami,
        'State': state,
        'OwnerId': owner,
        'CreationDate': created,
        'Tags': [{'Key': k, 'Value': v} for k, v in (tags or {}).items()],
        'BlockDeviceMappings': [
            {'DeviceName': f'/dev/sd{chr(97 + i)}', 'Ebs': {'SnapshotId': s}}
            for i, s in enumerate(snaps)
        ],
    }
    if reason:
        result['StateReason'] = {'Code': 'Server.InternalError', 'Message': reason}
    return result
