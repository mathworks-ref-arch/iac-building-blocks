# Infrastructure as Code Building Blocks for Amazon Web Services

This repository contains AWS&reg; CloudFormation templates used by multiple [MathWorks Reference Architectures](https://github.com/mathworks-ref-arch) for Amazon Web Services&reg;.

Each template configures specific infrastructure. MathWorks&reg; reference architectures use a selection of the available templates to create their overall infrastructure by using nested stacks. To learn more about using nested stacks, see [Nested Stacks (AWS)](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-nested-stacks.html).

## Available Templates

| Name          | Description |
| ------------- | ----------- |
| [security-group](security-group) | Creates a security group to control the inbound and outbound traffic for the resources deployed in AWS. |
| [log-location](log-location) | Creates a CloudWatch log group to store log events from AWS services. |
| [storage-location](storage-location) | Creates an Amazon S3&trade; Bucket to store objects in AWS. |
| [vpc-template](vpc-template) | Creates an Amazon Virtual Private Cloud (VPC) with four subnets evenly distributed across two availability zones, gateway endpoints for Amazon S3 and DynamoDB services, an optional NAT Gateway, and optional interface endpoints for various AWS services. For details, see [Amazon Virtual Private Cloud CloudFormation Template for MATLAB Reference Architectures](vpc-template/v1/README.md). |

## Usage

The CloudFormation templates in this repository are automatically published to the following Amazon S3&trade; bucket:
```
s3://mathworks-reference-architectures-templates/
```

Templates in this bucket are publicly accessible. The MathWorks reference architectures directly reference these templates in `AWS::CloudFormation::Stack` resources. For details, see [AWS Cloud Formation Stack Resources (AWS)](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-stack.html).

### Example

The following code shows you how to create a nested stack based on the security group template.

The `AWS::CloudFormation::Stack` resource declares the nested stack.
 - The `TemplateURL` property defines the template to use. Set it to the Amazon S3 bucket URL of the security group template version `v1.0.0`.
 - The `Parameters` property defines the inputs to the nested stack. Set the parameters `VpcId` and `CidrIp` to the values of the root stack. Add subsequent parameters to explicitly allow SSH, NICE DCV, and MATLAB Job Scheduler access but deny RDP access. Leave other parameters to their default values.

The [GetAtt](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-getatt.html) function retrieves an output value from the nested stack to the root stack.
```json
{
    "AWSTemplateFormatVersion" : "2010-09-09",
    "Parameters" : {
        "VPC" : {
            "Type" : "AWS::EC2::VPC::Id",
            "Description" : "ID of the VPC you want to use."
        },
        "IPAddresses" : {
            "Type" : "String",
            "Description" : "IP CIDR range to allow traffic from."
        }
    },
    "Resources" : {
        "MWSecurityGroup": {
            "Type" : "AWS::CloudFormation::Stack",
            "Properties" : {
                "TemplateURL" : "https://mathworks-reference-architectures-templates.s3.amazonaws.com/security-group/v1/0/0/security-group.yml",
                "Parameters" : {
                    "VpcId" : { "Ref" : "VPC" },
                    "CidrIp" : { "Ref" : "IPAddresses" },
                    "SSHAccess" : "Yes",
                    "RDPAccess" : "No",
                    "NICEDCVAccess" : "Yes",
                    "MJSAccess" : "Yes"
                }
            }
        }
    },
    "Outputs" : {
        "SecurityGroup" : {
            "Value" : { "Fn::GetAtt" : [ "MWSecurityGroup", "Outputs.SecurityGroupId" ] }
        }
    }
}
```

## Related Reference Architectures
 - [MATLAB on AWS](https://github.com/mathworks-ref-arch/matlab-on-aws)
 - [MATLAB Parallel Server on AWS](https://github.com/mathworks-ref-arch/matlab-parallel-server-on-aws)
 - [License Manager for MATLAB on AWS](https://github.com/mathworks-ref-arch/license-manager-for-matlab-on-aws)

## Technical Support
For support, visit [MathWorks Technical Support](https://www.mathworks.com/support/contact_us.html).

---
Copyright 2024-2025 The MathWorks, Inc.
