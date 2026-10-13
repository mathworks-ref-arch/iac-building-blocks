## Publish AMI (`actions/publish-ami`)

### Overview
This action copies a source AMI into a list of target regions, waits until every copy is available, can make the copies and their EBS snapshots public, and outputs a `RegionMap` for direct injection into a CloudFormation template.

### The Workflow
1. **Ownership check:** If the source AMI belongs to another account (for example, it was built in a build account and shared with the publishing account), the source region is copied too, so every AMI in the `RegionMap` belongs to the account running the action. If the caller owns the source AMI, the source region uses it as is.
2. **Reuse:** Each target region is searched for a copy this action made earlier for the same source AMI (by tag, see below). An available copy is reused, a pending one is waited for, and a failed one is ignored. This makes a re-run after a partial failure safe.
3. **Copy:** New copies are started in all regions at once, with tags applied to the AMI and its snapshots at creation.
4. **Wait:** All pending copies are polled together until they are available, one fails, or `timeout_minutes` passes.
5. **Make public (`make_public: true`):** The `LaunchPermission` of each AMI in the `RegionMap` and the `CreateVolumePermission` of its snapshots are set to `all`. Both calls are idempotent.
6. **Output:** A `RegionMap` covering every region the templates support. Regions without a published AMI get the value `Enter the ID of a custom AMI in this region.`

### Tags on copies
| Tag | Value |
| :--- | :--- |
| `mw-release-pipeline` | `public-builds` |
| `mw-source-ami` | Source AMI ID |
| `mw-release` | `matlab_version` |
| `mw-refarch-type` | `refarch_type` |
| `mw-github-run` | `<repository>/<run id>` of the workflow run |
| `mw-release-test` | `true`, only when `make_public` is `false` |

A copy that is not made public is a test copy. A public run never reuses a test copy. `cleanup.py --regions <list> --github-run <repository>/<run id>` deregisters the test copies of one run, deletes their snapshots and checks nothing is left; it never touches resources without `mw-release-test=true`. In a workflow, use the `publish-ami/cleanup` action, which runs it for the current run:

```yaml
- name: Remove Test Copies
  uses: mathworks-ref-arch/iac-building-blocks/.github/actions/publish-ami/cleanup@main
  with:
    regions: 'ap-northeast-3'
```

### Operational Modes
* **Standard Mode:** Executes boto3 calls against AWS.
* **Test Mode (`test_mode: true`):** Skips all AWS API calls and generates a mock `RegionMap` (e.g., `ami-test-us-east-2`). This allows for rapid pipeline validation without incurring AWS transfer costs or waiting for snapshot copies.

### Inputs & Outputs
| Input | Required | Description |
| :--- | :---: | :--- |
| `ami_id` | Yes | The Source AMI ID built in the origin region. |
| `source_ami_region` | Yes | The AWS region where the source AMI resides. |
| `target_ami_regions` | Yes | Comma-separated list of target regions (e.g., `us-east-1,eu-west-1`). |
| `matlab_version` | Yes | Target MATLAB version, used for naming and tags. |
| `refarch_type` | Yes | Architecture type (e.g., `matlab-linux`), used for naming and tags. |
| `test_mode` | No | Boolean to bypass AWS execution. Defaults to `true`. |
| `make_public` | No | Make the AMIs in the `RegionMap` and their snapshots public. Defaults to `false` (test copies). |
| `timeout_minutes` | No | Total time to wait for the copies. Defaults to `45`. |
| `python_version` | No | Python version for the script. Defaults to `3.11`. |

**Outputs:**
* `region_map_json`: The `RegionMap` as a JSON string, `{"region": {"AMI": "ami-id"}}`.
* `copies_json`: A JSON list of `{"region", "ami_id", "snapshot_ids", "state"}` for the target regions, where `state` is `created`, `reused` or `source`.

### Example Usage
```yaml
- name: Publish Built AMI
  id: publish_ami
  uses: mathworks-ref-arch/iac-building-blocks/.github/actions/publish-ami@experimental
  with:
    ami_id: 'ami-0123456789abcdef0'
    source_ami_region: 'us-east-1'
    target_ami_regions: 'us-east-1,eu-west-1,ap-south-1'
    matlab_version: 'R2025a'
    refarch_type: 'matlab-linux'
    test_mode: false
    make_public: true

```

### Tests
`python -m unittest discover -s .github/actions/publish-ami/tests` (needs `boto3`; AWS calls are stubbed).

----

Copyright 2026 The MathWorks, Inc.

----
