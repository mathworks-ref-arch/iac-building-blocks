# Infrastructure as Code Building Blocks for Microsoft Azure

This repository contains Microsoft&reg; Azure&reg; Resource Manager (ARM) templates used by multiple [MathWorks Reference Architectures](https://github.com/mathworks-ref-arch) for Microsoft Azure.

Each template configures specific infrastructure. MathWorks&reg; reference architectures use a selection of the available templates to create their overall infrastructure by using linked templates. To learn more about using linked templates, see [Using linked and nested templates when deploying Azure resources (Azure)](https://learn.microsoft.com/azure/azure-resource-manager/templates/linked-templates).

## Available Templates

| Name          | Description |
| ------------- | ----------- |
| [parallelserver-proxy](parallelserver-proxy) | Deploys a Linux&reg; virtual machine that runs the MATLAB&reg; Parallel Server&trade; proxy server. This server provides a [SOCKS5](https://www.mathworks.com/help/matlab-parallel-server/configure-socks5-proxy-for-matlab-job-scheduler.html) endpoint that allows clients to submit jobs to a private cluster from external networks. For details, see [Parallel Server Proxy ARM Template for MATLAB Parallel Server on Azure](parallelserver-proxy/README.md). |

## Usage

The ARM templates in this repository are published in the [mathworks-ref-arch/iac-building-blocks](https://github.com/mathworks-ref-arch/iac-building-blocks) GitHub repository, under the `azure-building-blocks/` folder. Each template is stored in a versioned folder, for example `azure-building-blocks/parallelserver-proxy/v1.0.0/parallelserverproxy-deploy.json`.

GitHub serves the raw file contents at `https://raw.githubusercontent.com/mathworks-ref-arch/iac-building-blocks/main/azure-building-blocks/<template-path>`, which is publicly accessible. MathWorks reference architectures directly reference these raw URLs in `Microsoft.Resources/deployments` resources. For details, see [Microsoft.Resources deployments (Azure)](https://learn.microsoft.com/azure/templates/microsoft.resources/deployments).

### Example

This code shows you how to create a linked deployment based on the MATLAB Parallel Server proxy template.

The `Microsoft.Resources/deployments` resource declares the linked deployment.
 - The `templateLink.uri` property defines the template to use. Set it to the raw GitHub URL of the Parallel Server Proxy template version `v1.0.0`.
 - The `parameters` property defines the inputs to the linked deployment. Set the parameters to the values of the parent deployment.

```json
{
    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {
        "subnetId": {
            "type": "string",
            "metadata": {
                "description": "Resource ID of the subnet to use."
            }
        },
        "clientIPAddresses": {
            "type": "string",
            "metadata": {
                "description": "Comma-separated IP CIDR ranges to allow traffic from."
            }
        }
    },
    "resources": [
        {
            "type": "Microsoft.Resources/deployments",
            "apiVersion": "2022-09-01",
            "name": "parallelServerProxy",
            "properties": {
                "mode": "Incremental",
                "templateLink": {
                    "uri": "https://raw.githubusercontent.com/mathworks-ref-arch/iac-building-blocks/main/azure-building-blocks/parallelserver-proxy/v1.0.0/parallelserverproxy-deploy.json",
                    "contentVersion": "1.0.0.0"
                },
                "parameters": {
                    "location": { "value": "[resourceGroup().location]" },
                    "subnetId": { "value": "[parameters('subnetId')]" },
                    "clientIPAddresses": { "value": "[parameters('clientIPAddresses')]" }
                }
            }
        }
    ]
}
```

## Related Reference Architectures
 - [MATLAB on Azure](https://github.com/mathworks-ref-arch/matlab-on-azure)
 - [MATLAB Parallel Server on Azure](https://github.com/mathworks-ref-arch/matlab-parallel-server-on-azure)
 - [License Manager for MATLAB on Azure](https://github.com/mathworks-ref-arch/license-manager-for-matlab-on-azure)

## Technical Support
For support, visit [MathWorks Technical Support](https://www.mathworks.com/support/contact_us.html).

---
Copyright 2026 The MathWorks, Inc.
