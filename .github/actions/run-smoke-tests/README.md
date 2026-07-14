
## Run Smoke Tests (`actions/run-smoke-tests`)

### Overview

This action executes pytest-based end-to-end smoke tests against a live CloudFormation stack. It validates that a deployed infrastructure stack is functional by running the test suite from the source repository's `tests/e2e` directory, providing JUnit XML reports and a GitHub Step Summary with results.

### The Workflow

1. **Validation:** Confirms the test directory and its `requirements.txt` exist before proceeding.
2. **Environment Setup:** Installs Python (via the shared `PYTHON_VERSION` variable) and test dependencies from the e2e requirements file.
3. **Execution:** Runs `pytest` against the deployed stack, passing the stack name and region as CLI arguments and injecting the MATLAB license string as an environment variable.

### Inputs & Outputs

| Input | Required | Description |
| --- | --- | --- |
| `region` | Yes | AWS region where the stack is deployed. |
| `stack_name` | Yes | Name of the deployed CloudFormation stack to test against. |
| `matlab_license_string` | Yes | MATLAB license string for product activation during tests. |

### Example Usage

```yaml
- name: Run Smoke Tests
  id: smoke-tests
  uses: mathworks-ref-arch/iac-building-blocks/.github/actions/run-smoke-tests@main
  with:
    region: 'us-east-1'
    stack_name: 'test-stack-12345'
    matlab_license_string: ${{ secrets.MATLAB_LICENSE_STRING }}
```

----

Copyright 2026 The MathWorks, Inc.

----

