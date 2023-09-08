# Infrastructure as Code Building Blocks

This repository contains the building blocks of the infrastructure as code (IaC) templates used by [MathWorks Reference Architectures](https://github.com/mathworks-ref-arch). The IaC templates define and configure the resources to create for a given reference architecture. The templates in this repository help to ensure that infrastructure creation and management are automated and repeatable.

You can explore the templates to learn more about the infrastructure supporting the MathWorks&reg; reference architectures. For the AWS&reg; CloudFormation templates used by the MathWorks reference architectures, see the [aws](aws) folder.

## Costs
You are responsible for the cost of the cloud services you use when you create cloud resources using these templates. Resource settings, such as instance type, affect the cost of deployment. For cost estimates, see the pricing pages for each cloud service you use. Prices are subject to change.

## Publishing Process
Changes to the IaC templates in this repository automatically update the public MathWorks IaC templates stored on the corresponding cloud platforms such as the Amazon S3&trade; bucket. The MathWorks reference architectures directly use the versions available in those public locations. For more information, refer to the documentation of the cloud provider.

### Versioning the Templates
Each template in this repository uses semantic versioning in the form of `vMAJOR.MINOR.PATCH`. Major updates to the IaC templates result in new versions that you can find in the repository. You can find the other updates in the Git&trade; commit history.

| Version component | Change                           |
| ----------------- | -------------------------------- |
| PATCH             | Internal changes                 |
| MINOR             | New features to the interface (new optional parameters, new outputs, ...) |
| MAJOR             | Breaking changes to the interface (new required parameters, compatibility changes, renamed or removed parameters or outputs, ...) |

## Related Repositories
 - [matlab-on-aws](https://github.com/mathworks-ref-arch/matlab-on-aws)
 - [matlab-parallel-server-on-aws](https://github.com/mathworks-ref-arch/matlab-parallel-server-on-aws)
 - [license-manager-for-matlab-on-aws](https://github.com/mathworks-ref-arch/license-manager-for-matlab-on-aws)
 - [matlab-on-azure](https://github.com/mathworks-ref-arch/matlab-on-azure)
 - [matlab-parallel-server-on-azure](https://github.com/mathworks-ref-arch/matlab-parallel-server-on-azure)
 - [license-manager-for-matlab-on-azure](https://github.com/mathworks-ref-arch/license-manager-for-matlab-on-azure)

## Technical Support
For support, visit [MathWorks Technical Support](https://www.mathworks.com/support/contact_us.html).

---
Copyright 2023 The MathWorks, Inc.
