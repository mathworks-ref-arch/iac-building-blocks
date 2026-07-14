
## Create AWS Template (`actions/create-aws-template`)

### Overview

This action acts as the template compiler for our CloudFormation infrastructure. It takes a generic, region-agnostic meta-template and a JSON RegionMap, merges them using `jq`, and produces a valid, deployable CloudFormation JSON artifact.

### The Workflow

1. **Dependency Verification:** Ensures `jq` is installed on the runner.
2. **Region Map Injection:** Reads the provided `region_map` string and injects it into the `.Mappings.RegionMap` block of the source meta-template. This overrides any placeholder mappings.
3. **Lambda Code Injection:** For each entry in `lambda_injections`, reads the source file and injects its contents into `.Resources[<ResourceName>].Properties.Code.ZipFile`. Errors if the resource is missing from the template or the source file does not exist.
4. **Artifact Publishing:** Uploads the newly generated CloudFormation template as a GitHub Actions artifact for downstream jobs (like deployment or release aggregation) to consume.

### Inputs & Outputs

| Input | Required | Description |
| --- | --- | --- |
| `region_map` | Yes | The JSON string containing region-to-AMI mappings. |
| `output_filename` | Yes | The desired filename for the compiled template. |
| `artifact_name` | Yes | The name to assign the uploaded GitHub Actions artifact (passed straight to `upload-artifact`'s `name`). This is an artifact label, not a filesystem path. |
| `metatemplate_file_path` | Yes | Relative path to the source JSON meta-template. |
| `lambda_injections` | No | JSON object mapping Lambda resource logical IDs to source files to embed. Defaults to `'{}'`. |

### Example Usage

```yaml
- name: Generate CloudFormation Template
  uses: mathworks-ref-arch/iac-building-blocks/.github/actions/create-aws-template@main
  with:
    region_map: '{"us-east-1": {"AMI": "ami-0123456789abcdef0"}}'
    output_filename: 'R2025a-release-template.json'
    artifact_name: 'R2025a-release-template'
    metatemplate_file_path: 'src/meta-template.json'
    lambda_injections: '{"AttachInstanceProfileLambda": "src/attachinstanceprofile.py"}'

```

----

Copyright 2026 The MathWorks, Inc.

----
