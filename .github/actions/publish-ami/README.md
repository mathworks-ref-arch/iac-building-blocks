## Publish AMI (`actions/publish-ami`)

### Overview
This action handles the cross-region publishing of a newly minted AMI. It takes a single source AMI and duplicates it across a specified list of target release regions, ensuring that both the AMI and its underlying EBS snapshots are made public. Finally, it generates a `RegionMap` JSON object intended for direct injection into a CloudFormation template.

### The Workflow
1. **Idempotency Check:** Scans destination regions for existing copies of the source AMI (identified via description tagging) to prevent duplicate copying.
2. **Publishing:** Initiates asynchronous `copy_image` requests via `boto3` to all target regions.
3. **Verification & Permissions:** Polls AWS until all AMIs are in an `available` state. Once available, it modifies the `LaunchPermission` of the AMI and the `CreateVolumePermission` of the snapshot to `all` (public).
4. **Output Generation:** Constructs a structured JSON map linking each region to its new localized AMI ID.

### Operational Modes
* **Standard Mode:** Executes standard boto3 calls against AWS infrastructure.
* **Test Mode (`test_mode: true`):** Skips all AWS API calls and generates a mock `RegionMap` (e.g., `ami-test-us-east-2`). This allows for rapid pipeline validation without incurring AWS transfer costs or waiting for snapshot copies.

### Inputs & Outputs
| Input | Required | Description |
| :--- | :---: | :--- |
| `ami_id` | Yes | The Source AMI ID built in the origin region. |
| `source_ami_region` | Yes | The AWS region where the source AMI resides. |
| `target_ami_regions` | Yes | Comma-separated list of target regions (e.g., `us-east-1,eu-west-1`). |
| `matlab_version` | Yes | Target MATLAB version, used for artifact naming. |
| `refarch_type` | Yes | Architecture type (e.g., `matlab-linux`), used for naming. |
| `test_mode` | No | Boolean to bypass AWS execution. Defaults to `true`. |

**Outputs:**
* `region_map_json`: A stringified JSON object formatted as `{"RegionMap": {"region": {"AMI": "ami-id"}}}`.

### Example Usage
```yaml
- name: Publish Built AMI
  id: publish_ami
  uses: mathworks-ref-arch/iac-building-blocks/.github/actions/publish-ami@main
  with:
    ami_id: 'ami-0123456789abcdef0'
    source_ami_region: 'us-east-1'
    target_ami_regions: 'us-east-2,eu-west-1,ap-south-1'
    matlab_version: 'R2025a'
    refarch_type: 'matlab-linux'
    test_mode: false

```

----

Copyright 2026 The MathWorks, Inc.

----
