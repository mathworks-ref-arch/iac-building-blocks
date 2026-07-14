
## Process Release Files (`actions/process-release-files`)

### Overview

This action handles the final documentation assembly prior to a GitHub Release. It relies on a suite of Python scripts and the Jinja2 templating engine to generate context-aware `README.md`, `LICENSE.md`, and permission documentation for the repository.

### The Workflow

1. **Data Aggregation:** Deserializes the target version array and locates all related CloudFormation artifacts generated earlier in the pipeline.
2. **Template Rendering:**
* Compiles the top-level repository README outlining all available releases.
* Generates version-specific READMEs containing dynamic S3 launch links.
* Filters the internal AWS IAM provisioning policies to strip out highly-privileged actions (e.g., `iam:CreateRole`), generating a safe "restricted" policy document for consumers.


3. **Repository Structuring:** Writes the fully rendered documentation and flattened artifacts into a staging directory matching the target repository's structure.

### Inputs & Outputs

| Input | Required | Description |
| --- | --- | --- |
| `target_versions` | Yes | JSON string array of the MATLAB versions being released. |
| `source_path` | No | Path to the raw Jinja2 markdown templates. Defaults to `./src`. |
| `artifact_path` | No | Path to the directory containing downloaded CFN artifacts. |
| `s3_bucket_url` | Yes | Base URL of the production S3 bucket hosting the templates. |
| `dual_repo_url` | Yes | URL pointer to the sister repository (for cross-OS referencing). |

### Example Usage

```yaml
- name: Process and Assemble Documentation
  uses: mathworks-ref-arch/iac-building-blocks/.github/actions/process-release-files@main
  with:
    target_versions: '["R2025a", "R2024b"]'
    source_path: './src'
    artifact_path: './artifacts'
    s3_bucket_url: 's3://my-prod-bucket/templates/'
    dual_repo_url: 'https://github.com/my-org/sister-repo'

```

----

Copyright 2026 The MathWorks, Inc.

----
