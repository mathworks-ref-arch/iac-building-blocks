# Copyright 2026 The MathWorks, Inc.
"""Publish a source AMI to multiple AWS regions.

Copies a single source AMI into each target region (skipping any region that
already holds a copy), waits for each copy to become available, makes both the
AMI and its backing EBS snapshots public, and emits a CloudFormation RegionMap
as the ``region_map_json`` GitHub Actions output.

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

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ami-id', required=True)
    parser.add_argument('--src-region', required=True)
    parser.add_argument('--dest-regions', required=True, help="Comma separated list")
    parser.add_argument('--version', required=True, help="Matlab version for naming")
    parser.add_argument('--refarch-type', required=True, help="Refarch type for naming")
    parser.add_argument('--test-mode', action='store_true')
    return parser.parse_args()

def write_region_map(region_map):
    """Serialize the RegionMap and write it to the GitHub Actions output."""
    final_json = json.dumps({'RegionMap': region_map})
    print(f"Final Region Map: {final_json}")
    with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
        fh.write(f"region_map_json={final_json}\n")

def copy_ami_to_region(src_ami, src_region, dest_region, version, refarch_type):
    """Ensure a public copy of src_ami exists in dest_region.

    Returns a tuple (dest_ami_id, is_pending) where is_pending indicates the
    copy was freshly initiated and still needs to reach the 'available' state.
    """
    ec2 = boto3.client('ec2', region_name=dest_region)

    # Idempotency: reuse an existing copy if one is already present.
    all_amis = ec2.describe_images(Owners=['self'])
    for image in all_amis['Images']:
        if 'Description' in image and f"[Copied {src_ami} from {src_region}]" in image['Description']:
            dest_ami_id = image['ImageId']
            print(f"Found existing copy in {dest_region}: {dest_ami_id}")
            if not image.get('Public', False):
                print(f"Making existing AMI {dest_ami_id} public...")
                ec2.modify_image_attribute(
                    ImageId=dest_ami_id,
                    LaunchPermission={"Add": [{"Group": "all"}]}
                )
            return dest_ami_id, False

    print(f"Copying {src_ami} to {dest_region}...")
    response = ec2.copy_image(
        Description=f"[Copied {src_ami} from {src_region}]",
        Name=f"{version}-{refarch_type}-{int(time.time())}",
        SourceImageId=src_ami,
        SourceRegion=src_region
    )
    return response['ImageId'], True

def finalize_ami(dest_region, dest_ami):
    """Wait for a freshly copied AMI to become available and make it public."""
    print(f"Waiting for {dest_ami} in {dest_region}...")
    ec2 = boto3.client('ec2', region_name=dest_region)

    waiter = ec2.get_waiter('image_available')
    # Wait up to 30 mins (45 attempts * 40s)
    waiter.wait(
        ImageIds=[dest_ami],
        WaiterConfig={'Delay': 40, 'MaxAttempts': 45}
    )

    print(f"AMI {dest_ami} is available. Setting permissions...")

    # Make AMI Public
    ec2.modify_image_attribute(
        ImageId=dest_ami,
        LaunchPermission={"Add": [{"Group": "all"}]}
    )

    # Make backing snapshots public
    ami_details = ec2.describe_images(ImageIds=[dest_ami])
    if ami_details['Images']:
        block_mappings = ami_details['Images'][0].get('BlockDeviceMappings', [])
        for mapping in block_mappings:
            if 'Ebs' in mapping and 'SnapshotId' in mapping['Ebs']:
                snap_id = mapping['Ebs']['SnapshotId']
                ec2.modify_snapshot_attribute(
                    SnapshotId=snap_id,
                    CreateVolumePermission={"Add": [{"Group": "all"}]}
                )

def main():
    args = get_args()

    src_ami = args.ami_id
    src_region = args.src_region
    dest_regions = [r.strip() for r in args.dest_regions.split(',') if r.strip()]

    # Initialize RegionMap with the source
    region_map = {
        src_region: {"AMI": src_ami}
    }

    if args.test_mode:
        print(f"::notice::Running in TEST MODE. No resources will be created.")
        for region in dest_regions:
            if region == src_region:
                continue
            # Return a mock AMI for all regions to validate template generation
            region_map[region] = {"AMI": f"ami-test-{region}"}
        write_region_map(region_map)
        return

    # This flow is intentionally all-or-nothing: any failure aborts the run so
    # we never publish a partial RegionMap. The try/except exists to turn opaque
    # boto3 stack traces into an actionable, region-scoped error message.
    pending_regions = []
    try:
        for dest_region in dest_regions:
            if dest_region == src_region:
                continue
            print(f"Processing region: {dest_region}...")
            dest_ami_id, is_pending = copy_ami_to_region(
                src_ami, src_region, dest_region, args.version, args.refarch_type
            )
            if is_pending:
                pending_regions.append((dest_region, dest_ami_id))
            region_map[dest_region] = {"AMI": dest_ami_id}

        if pending_regions:
            print(f"Waiting for AMIs to become available in: {[x[0] for x in pending_regions]}")
        for dest_region, dest_ami in pending_regions:
            finalize_ami(dest_region, dest_ami)
    except (BotoCoreError, ClientError) as e:
        print(f"::error::Failed to publish {src_ami} from {src_region}: {e}")
        sys.exit(1)

    write_region_map(region_map)

if __name__ == "__main__":
    main()
