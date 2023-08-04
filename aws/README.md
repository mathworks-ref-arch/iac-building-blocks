# Infrastructure as Code Building Blocks for Amazon Web Services

This repository contains AWS&reg; CloudFormation templates used by multiple [MathWorks Reference Architectures](https://github.com/mathworks-ref-arch) for Amazon Web Services&reg;.

Each template configures a specific chunk of infrastructure. MathWorks&reg; reference architectures use a selection of the available templates to create their overall infrastructure by using nested stacks. Learn more about using nested stacks in the [AWS documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-nested-stacks.html).

## Available Templates

| Name          | Description |
| ------------- | ----------- |
| [security-group](security-group) | Creates a security group to control the inbound and outbound traffic for the resources deployed in AWS. |
| [log-location](log-location) | Creates a CloudWatch log group to store log events from AWS services. |

## Usage

The CloudFormation templates in this repository are automatically published to the following Amazon S3&trade; bucket:
```
s3://mathworks-reference-architectures-templates/
```

Templates in this bucket are publicly accessible. The MathWorks reference architectures directly reference these templates in `AWS::CloudFormation::Stack` resources. For more information about this type of resource, refer to the [AWS documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-stack.html).

### Example

The following code shows you how to create a nested stack based on the security group template.

The `AWS::CloudFormation::Stack` resource declares the nested stack.
 - The `TemplateURL` property defines the template to use. Set it to the Amazon S3 bucket URL of the security group template version `v1.0.0`.
 - The `Parameters` property defines the inputs to the nested stack. Set the parameters `VpcId` and `CidrIp` to the values of the root stack. Add subsequent parameters to explicitly allow SSH, NICE DCV, and MATLAB Job Scheduler access but deny RDP access. Leave other parameters at their default values.

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

## Related repositories
 - [matlab-on-aws](https://github.com/mathworks-ref-arch/matlab-on-aws)
 - [matlab-parallel-server-on-aws](https://github.com/mathworks-ref-arch/matlab-parallel-server-on-aws)
 - [license-manager-for-matlab-on-aws](https://github.com/mathworks-ref-arch/license-manager-for-matlab-on-aws)

## Technical Support
For support, visit [MathWorks Technical Support](https://www.mathworks.com/support/contact_us.html).

---
Copyright 2023 The MathWorks, Inc.
