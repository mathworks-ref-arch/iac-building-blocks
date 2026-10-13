## Publish Release Template (`actions/publish-release-template`)

### Overview
This action writes a compiled release template to a fixed S3 key, so the template URL of a release stays the same across updates. It creates the key if it doesn't exist and otherwise replaces the current object, unless a newer run of the same repository wrote it.

### The Workflow
1. **Create:** Writes the template with `If-None-Match: *`, which only succeeds if the key doesn't exist yet.
2. **Replace:** If the key exists, reads the object's metadata. If a newer run of the same repository wrote it, the action fails without writing. Otherwise it writes with `If-Match` on the ETag it just read, so an object that changes in the meantime is never overwritten.
3. **Verify:** Reads the object back and checks its ETag against the template's MD5 and its metadata against this run.
4. **Outputs:** Sets the template URL, the version id and whether the key was created or replaced.

The object carries `github-run-id` and `github-repository` metadata, which is what later runs compare against. Objects without that metadata are replaced. A re-run of the same run replaces its own object, so a failed job can be re-run safely.

### Inputs & Outputs
| Input | Required | Description |
| :--- | :---: | :--- |
| `template_file` | Yes | Path to the compiled release template. |
| `bucket` | Yes | S3 bucket to publish to. |
| `key` | Yes | Object key, e.g. `R2026b/aws-matlab-template.json`. |
| `acl` | No | Canned ACL for the object. Defaults to `public-read`; empty sets none. |
| `region` | No | Region of the bucket. Defaults to `us-east-1`. |
| `python_version` | No | Python version for the publish script. Defaults to `3.11`. |

**Outputs:**
* `template_url`: `https://<bucket>.s3.amazonaws.com/<key>`.
* `version_id`: Version id of the written object, empty if the bucket isn't versioned.
* `result`: `created` or `replaced`.

### Permissions
The credentials in the job (for example from `aws-actions/configure-aws-credentials`) need, on the key:
* `s3:PutObject`
* `s3:PutObjectAcl`, when an ACL is set
* `s3:GetObject`, to read the metadata of an existing object and to verify the write

`s3:ListBucket` isn't needed. The ETag check assumes the bucket uses SSE-S3 or no default encryption, where a single-part upload's ETag is its MD5.

### Example Usage
```yaml
- name: Publish Release Template
  id: publish_template
  uses: mathworks-ref-arch/iac-building-blocks/.github/actions/publish-release-template@experimental
  with:
    template_file: 'R2026b-release-template.json'
    bucket: 'my-release-bucket'
    key: 'R2026b/aws-matlab-template.json'
```

### Tests
```
python -m unittest discover -s .github/actions/publish-release-template/tests -v
```

----

Copyright 2026 The MathWorks, Inc.

----
