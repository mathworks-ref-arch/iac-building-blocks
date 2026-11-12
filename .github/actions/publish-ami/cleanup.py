# Copyright 2026 The MathWorks, Inc.
"""Remove the test copies one workflow run made with publish.py.

Deregisters the AMIs tagged ``mw-release-test=true`` and
``mw-github-run=<repository>/<run id>`` in the given regions, deletes their
snapshots, and verifies that nothing tagged that way is left. Anything without
the test tag is never touched. A role that may not delete keeps its copies:
they are listed as a warning, not an error.
"""
import argparse
import os
import sys
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

TEST_TAG = "mw-release-test"
RUN_TAG = "mw-github-run"
SNAPSHOT_RETRIES = 3
SNAPSHOT_RETRY_SECONDS = 10
REFUSED_CODES = ('UnauthorizedOperation', 'AccessDenied')


class CleanupError(Exception):
    """Something tagged for cleanup could not be removed."""


def get_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--regions', required=True, help="Comma separated list")
    parser.add_argument('--github-run', required=True, help="<repository>/<run id>")
    return parser.parse_args(argv)


def get_client(service, region):
    return boto3.client(service, region_name=region)


def test_filters(github_run):
    return [
        {'Name': f'tag:{TEST_TAG}', 'Values': ['true']},
        {'Name': f'tag:{RUN_TAG}', 'Values': [github_run]},
    ]


def is_test_resource(resource, github_run):
    tags = {t['Key']: t['Value'] for t in resource.get('Tags', [])}
    return tags.get(TEST_TAG) == 'true' and tags.get(RUN_TAG) == github_run


def refused(error):
    return error.response.get('Error', {}).get('Code') in REFUSED_CODES


def snapshot_ids(image):
    return [
        m['Ebs']['SnapshotId']
        for m in image.get('BlockDeviceMappings', [])
        if 'Ebs' in m and 'SnapshotId' in m['Ebs']
    ]


def delete_snapshot(ec2, snap_id):
    # A snapshot can stay in use for a few seconds after its AMI is deregistered.
    for attempt in range(1, SNAPSHOT_RETRIES + 1):
        try:
            ec2.delete_snapshot(SnapshotId=snap_id)
            return
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code')
            if code == 'InvalidSnapshot.NotFound':
                return
            if code != 'InvalidSnapshot.InUse' or attempt == SNAPSHOT_RETRIES:
                raise
            time.sleep(SNAPSHOT_RETRY_SECONDS)


def live_images(ec2, github_run):
    images = ec2.describe_images(Owners=['self'], Filters=test_filters(github_run))['Images']
    return [i for i in images if i.get('State') != 'deregistered']


def tagged_snapshots(ec2, github_run):
    # A role that may not delete (the prod release role) may not list snapshots either.
    try:
        return ec2.describe_snapshots(OwnerIds=['self'], Filters=test_filters(github_run))['Snapshots']
    except ClientError as e:
        if not refused(e):
            raise
        return []


def cleanup_region(ec2, region, github_run):
    """Remove the run's test copies and their snapshots in one region; return those the role may not delete."""
    kept = []
    for image in live_images(ec2, github_run):
        if not is_test_resource(image, github_run):
            raise CleanupError(f"Refusing to touch {image['ImageId']} in {region}: not a test copy of {github_run}")
        snaps = snapshot_ids(image)
        print(f"Deregistering {image['ImageId']} in {region}")
        try:
            ec2.deregister_image(ImageId=image['ImageId'])
        except ClientError as e:
            if not refused(e):
                raise
            kept += [image['ImageId'], *snaps]
            continue
        for snap_id in snaps:
            print(f"Deleting snapshot {snap_id} in {region}")
            try:
                delete_snapshot(ec2, snap_id)
            except ClientError as e:
                if not refused(e):
                    raise
                kept.append(snap_id)

    # Snapshots left behind by a copy that failed before its AMI registered.
    for snap in tagged_snapshots(ec2, github_run):
        if snap['SnapshotId'] in kept:
            continue
        if not is_test_resource(snap, github_run):
            raise CleanupError(f"Refusing to touch {snap['SnapshotId']} in {region}: not a test snapshot of {github_run}")
        print(f"Deleting leftover snapshot {snap['SnapshotId']} in {region}")
        try:
            delete_snapshot(ec2, snap['SnapshotId'])
        except ClientError as e:
            if not refused(e):
                raise
            kept.append(snap['SnapshotId'])

    remaining = [i['ImageId'] for i in live_images(ec2, github_run)]
    remaining += [s['SnapshotId'] for s in tagged_snapshots(ec2, github_run)]
    remaining = [r for r in remaining if r not in kept]
    if remaining:
        raise CleanupError(f"Still present in {region}: {', '.join(remaining)}")
    return kept


def report_kept(kept):
    """Warn about the copies the role may not delete, in the log and the job summary."""
    lines = [f"{region}: {', '.join(ids)}" for region, ids in kept.items()]
    print(f"::warning::This role may not delete test copies. Delete them by hand: {'; '.join(lines)}")
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as fh:
            fh.write("Test copies left for deletion by hand:\n\n")
            fh.writelines(f"- {line}\n" for line in lines)


def main(argv=None):
    args = get_args(argv)
    regions = list(dict.fromkeys(r.strip() for r in args.regions.split(',') if r.strip()))
    github_run = args.github_run.strip()
    if not regions or '/' not in github_run or any(c in github_run for c in '*?'):
        print("::error::Give --regions and an exact --github-run <repository>/<run id>")
        sys.exit(1)

    failed = False
    kept = {}
    for region in regions:
        try:
            left = cleanup_region(get_client('ec2', region), region, github_run)
        except (BotoCoreError, ClientError, CleanupError) as e:
            print(f"::error::Cleanup failed in {region}: {e}")
            failed = True
            continue
        if left:
            kept[region] = left
    if kept:
        report_kept(kept)
    if failed:
        sys.exit(1)
    if not kept:
        print(f"No test copies of {github_run} left in {', '.join(regions)}")


if __name__ == "__main__":
    main()
