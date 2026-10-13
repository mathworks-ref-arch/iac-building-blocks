# Copyright 2026 The MathWorks, Inc.
"""Publish a source AMI to multiple AWS regions.

Copies a source AMI into each target region, reusing copies this action made
earlier for the same source AMI, waits until every copy is available, can make
the copies and their EBS snapshots public, and emits a CloudFormation RegionMap
as the ``region_map_json`` GitHub Actions output.

When the source AMI is owned by another account, the source region is copied
too, so every AMI in the RegionMap belongs to the publishing account.

In test mode the AWS calls are skipped and a mock RegionMap is produced so the
downstream template-generation steps can be validated without incurring copy
costs.
"""
import os
import json
import boto3
import time
import argparse
import sys

from botocore.exceptions import BotoCoreError, ClientError

PLACEHOLDER = "Enter the ID of a custom AMI in this region."

# Every region the templates map. Regions without a published AMI keep the placeholder.
TEMPLATE_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2", "ca-central-1",
    "eu-central-1", "eu-west-1", "eu-west-2", "eu-west-3", "eu-north-1",
    "sa-east-1", "me-south-1", "ap-east-1", "ap-south-1", "ap-northeast-1",
    "ap-northeast-2", "ap-southeast-1", "ap-southeast-2",
    "us-gov-west-1", "us-gov-east-1", "cn-north-1", "cn-northwest-1",
]

PIPELINE_TAG = "mw-release-pipeline"
PIPELINE_TAG_VALUE = "public-builds"
TEST_TAG = "mw-release-test"
POLL_SECONDS = 15
IN_PROGRESS_STATES = ("pending",)


class PublishError(Exception):
    """A copy failed, timed out, or the source AMI is unusable."""


def get_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--ami-id', required=True)
    parser.add_argument('--src-region', required=True)
    parser.add_argument('--dest-regions', required=True, help="Comma separated list")
    parser.add_argument('--version', required=True, help="Matlab version for naming")
    parser.add_argument('--refarch-type', required=True, help="Refarch type for naming")
    parser.add_argument('--test-mode', action='store_true')
    parser.add_argument('--make-public', action='store_true')
    parser.add_argument('--timeout-minutes', type=float, default=45)
    return parser.parse_args(argv)


def get_client(service, region):
    return boto3.client(service, region_name=region)


def parse_regions(value):
    """Split a comma separated region list, dropping blanks and duplicates."""
    return list(dict.fromkeys(r.strip() for r in value.split(',') if r.strip()))


def base_region_map():
    return {region: {"AMI": PLACEHOLDER} for region in TEMPLATE_REGIONS}


def tag_dict(resource):
    return {t['Key']: t['Value'] for t in resource.get('Tags', [])}


def snapshot_ids(image):
    return [
        m['Ebs']['SnapshotId']
        for m in image.get('BlockDeviceMappings', [])
        if 'Ebs' in m and 'SnapshotId' in m['Ebs']
    ]


def copy_tags(src_ami, version, refarch_type, make_public):
    """Tags applied to new copies and their snapshots at creation."""
    tags = {
        PIPELINE_TAG: PIPELINE_TAG_VALUE,
        "mw-source-ami": src_ami,
        "mw-release": version,
        "mw-refarch-type": refarch_type,
    }
    repo = os.environ.get('GITHUB_REPOSITORY')
    run_id = os.environ.get('GITHUB_RUN_ID')
    if repo and run_id:
        tags["mw-github-run"] = f"{repo}/{run_id}"
    # A copy that is not made public is a test copy and can be cleaned up.
    if not make_public:
        tags[TEST_TAG] = "true"
    return [{'Key': k, 'Value': v} for k, v in tags.items()]


def describe_image(ec2, image_id):
    images = ec2.describe_images(ImageIds=[image_id])['Images']
    return images[0] if images else None


def find_existing_copy(ec2, src_ami, make_public):
    """Return a reusable copy of src_ami made by this action, or None.

    Available copies are preferred over pending ones. Failed copies are ignored,
    and a test copy is never reused for a public release.
    """
    images = ec2.describe_images(
        Owners=['self'],
        Filters=[
            {'Name': f'tag:{PIPELINE_TAG}', 'Values': [PIPELINE_TAG_VALUE]},
            {'Name': 'tag:mw-source-ami', 'Values': [src_ami]},
        ],
    )['Images']
    candidates = []
    for image in images:
        if image['State'] not in ('available',) + IN_PROGRESS_STATES:
            print(f"Ignoring copy {image['ImageId']} in state {image['State']}")
            continue
        if make_public and tag_dict(image).get(TEST_TAG) == 'true':
            print(f"Ignoring test copy {image['ImageId']}: test copies are never made public")
            continue
        candidates.append(image)
    if not candidates:
        return None
    candidates.sort(key=lambda i: i.get('CreationDate', ''), reverse=True)
    candidates.sort(key=lambda i: i['State'] != 'available')
    return candidates[0]


def start_copy(ec2, src_ami, src_region, version, refarch_type, tags):
    response = ec2.copy_image(
        Description=f"[Copied {src_ami} from {src_region}]",
        Name=f"{version}-{refarch_type}-{int(time.time())}",
        SourceImageId=src_ami,
        SourceRegion=src_region,
        TagSpecifications=[
            {'ResourceType': 'image', 'Tags': tags},
            {'ResourceType': 'snapshot', 'Tags': tags},
        ],
    )
    return response['ImageId']


def wait_for_copies(ec2_for, pending, deadline):
    """Poll all pending copies together until they are available.

    ``pending`` maps region to AMI id. Returns a map of region to the described
    image. Raises PublishError when a copy fails or the deadline passes.
    """
    pending = dict(pending)
    done = {}
    while True:
        for region, ami in list(pending.items()):
            image = describe_image(ec2_for(region), ami)
            state = image['State'] if image else 'missing'
            if state == 'available':
                done[region] = image
                del pending[region]
            elif state not in IN_PROGRESS_STATES:
                reason = (image or {}).get('StateReason', {}).get('Message', '')
                raise PublishError(f"Copy {ami} in {region} is {state}. {reason}".strip())
        if not pending:
            return done
        if time.monotonic() >= deadline:
            waiting = ", ".join(f"{r} ({a})" for r, a in pending.items())
            raise PublishError(f"Timed out waiting for copies to become available: {waiting}")
        print(f"Waiting for {len(pending)} copies: {', '.join(pending)}")
        time.sleep(POLL_SECONDS)


def make_image_public(ec2, image):
    ec2.modify_image_attribute(
        ImageId=image['ImageId'],
        LaunchPermission={"Add": [{"Group": "all"}]}
    )
    for snap_id in snapshot_ids(image):
        ec2.modify_snapshot_attribute(
            SnapshotId=snap_id,
            CreateVolumePermission={"Add": [{"Group": "all"}]}
        )


def mock_publish(src_ami, src_region, dest_regions):
    region_map = base_region_map()
    for region in dest_regions:
        ami = src_ami if region == src_region else f"ami-test-{region}"
        region_map[region] = {"AMI": ami}
    return region_map, []


def publish(src_ami, src_region, dest_regions, version, refarch_type,
            make_public=False, timeout_minutes=45):
    """Copy src_ami into dest_regions and return (region_map, copies)."""
    clients = {}

    def ec2_for(region):
        if region not in clients:
            clients[region] = get_client('ec2', region)
        return clients[region]

    deadline = time.monotonic() + timeout_minutes * 60
    source = describe_image(ec2_for(src_region), src_ami)
    if source is None:
        raise PublishError(f"Source AMI {src_ami} not found in {src_region}")
    caller = get_client('sts', src_region).get_caller_identity()['Account']
    cross_account = source['OwnerId'] != caller
    if cross_account:
        print(f"{src_ami} is owned by another account: copying into every target region")

    tags = copy_tags(src_ami, version, refarch_type, make_public)
    region_map = base_region_map()
    images, states, pending = {}, {}, {}

    for region in dest_regions:
        print(f"Processing region: {region}...")
        if region == src_region and not cross_account:
            ami = src_ami
            images[region], states[region] = source, 'source'
        else:
            existing = find_existing_copy(ec2_for(region), src_ami, make_public)
            if existing:
                ami = existing['ImageId']
                states[region] = 'reused'
                print(f"Reusing copy {ami} in {region} ({existing['State']})")
                if existing['State'] == 'available':
                    images[region] = existing
                else:
                    pending[region] = ami
            else:
                ami = start_copy(ec2_for(region), src_ami, src_region, version, refarch_type, tags)
                states[region] = 'created'
                print(f"Copying {src_ami} to {region}: {ami}")
                pending[region] = ami
        region_map[region] = {"AMI": ami}

    images.update(wait_for_copies(ec2_for, pending, deadline))

    if make_public:
        for region in dest_regions:
            print(f"Making {images[region]['ImageId']} in {region} public...")
            make_image_public(ec2_for(region), images[region])

    copies = [
        {
            "region": region,
            "ami_id": images[region]['ImageId'],
            "snapshot_ids": snapshot_ids(images[region]),
            "state": states[region],
        }
        for region in dest_regions
    ]
    return region_map, copies


def write_outputs(region_map, copies):
    """Serialize the RegionMap and the copy list to the GitHub Actions output."""
    region_map_json = json.dumps(region_map)
    copies_json = json.dumps(copies)
    print(f"Final Region Map: {region_map_json}")
    print(f"Copies: {copies_json}")
    with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
        fh.write(f"region_map_json={region_map_json}\n")
        fh.write(f"copies_json={copies_json}\n")


def main(argv=None):
    args = get_args(argv)
    dest_regions = parse_regions(args.dest_regions)
    if not dest_regions:
        print("::error::No target regions given")
        sys.exit(1)

    if args.test_mode:
        print("::notice::Running in TEST MODE. No resources will be created.")
        write_outputs(*mock_publish(args.ami_id, args.src_region, dest_regions))
        return

    # All or nothing: any failure aborts the run so a partial RegionMap is never published.
    try:
        region_map, copies = publish(
            args.ami_id, args.src_region, dest_regions, args.version,
            args.refarch_type, args.make_public, args.timeout_minutes,
        )
    except (BotoCoreError, ClientError, PublishError) as e:
        print(f"::error::Failed to publish {args.ami_id} from {args.src_region}: {e}")
        sys.exit(1)

    write_outputs(region_map, copies)


if __name__ == "__main__":
    main()
