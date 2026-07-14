
## Deploy CFN (`actions/deploy-cfn`)

### Overview

This action deploys an ephemeral CloudFormation stack for integration and smoke testing. To avoid massive, brittle conditional blocks in our workflow YAMLs, this action utilizes a "Flavor Mapping" pattern. It dynamically constructs CloudFormation parameters based on the specific architecture being deployed (e.g., Linux vs. Windows, Single Node vs. Parallel Server).

### The Workflow

1. **Type Resolution:** Reads `refarch-type-mappings.json` to lookup the default parameter values and variable names (like identifying whether to use `SSHKeyName` or `RDPKeyName`) for the requested `refarch_type`.
2. **Dynamic Parameter Injection:** Fetches the GitHub Runner's current IP address and injects it, along with standard inputs (VPC, Subnet, SSH Key), into a generated `params.json` file.
3. **Execution:** Triggers `aws cloudformation create-stack` and blocks until the `stack-create-complete` signal is received.
4. **Data Retrieval:** Parses the final CloudFormation stack outputs into a flattened JSON key-value string.

### Inputs & Outputs

| Input | Required | Description |
| --- | --- | --- |
| `compiled_template_file_path` | Yes | Path to the already-compiled CloudFormation template. |
| `refarch_type` | Yes | Target deployment architecture type matching a key in `refarch-type-mappings.json`. |
| `region` | Yes | AWS region to deploy the stack into. |
| `stack_name` | Yes | Unique identifier for the temporary stack. |
| `vpc_id` / `subnet_id` | Yes | Network configuration for the deployment. |
| `key_pair_name` | Yes | Name of the pre-provisioned AWS EC2 key pair for access. |

**Outputs:**

* `stack_outputs`: A flat JSON string of the CloudFormation stack outputs (e.g., `{"HeadnodePublicDNS": "ec2-...", "RDPConnection": "..."}`).

### Example Usage

```yaml
- name: Deploy Ephemeral Stack
  id: deploy
  uses: mathworks-ref-arch/iac-building-blocks/.github/actions/deploy-cfn@main
  with:
    compiled_template_file_path: './R2025a-test-template.json'
    refarch_type: 'matlab-linux'
    region: 'us-east-1'
    stack_name: 'smoke-test-matlab-linux-R2025a-${{ github.run_id }}'
    vpc_id: 'vpc-0abcd1234'
    subnet_id: 'subnet-0abcd1234'
    key_pair_name: 'smoke-test-key'

```

----

Copyright 2026 The MathWorks, Inc.

----
