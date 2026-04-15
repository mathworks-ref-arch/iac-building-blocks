# Copyright 2026 The MathWorks, Inc

import yaml
from typing import Any, Dict, Union

class CloudFormationYAMLLoader(yaml.SafeLoader):
    """
    Custom YAML loader that handles CloudFormation intrinsic functions.
    """
    pass


def multi_constructor(
    loader: yaml.Loader,
    tag_suffix: str,
    node: Union[yaml.ScalarNode, yaml.SequenceNode, yaml.MappingNode]
) -> Dict[str, Any]:
    """
    Handle CloudFormation !Ref, !Sub, !Join style functions
    
    Args:
        loader: The YAML loader instance
        tag_suffix: The suffix of the tag (e.g., "Ref", "Sub", "Join")
        node: The YAML node to construct
        
    Returns:
        A dictionary with the CloudFormation function format
    """
    # Convert to CloudFormation format (e.g., !Ref -> Ref, !Sub -> Fn::Sub)
    if tag_suffix == "Ref":
        tag = tag_suffix
    else:
        tag = f"Fn::{tag_suffix}"
    
    # Construct the value based on node type
    value: Any
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node)
    else:
        raise Exception(f"Unknown node type for !{tag_suffix}")
    
    return {tag: value}

CloudFormationYAMLLoader.add_multi_constructor("!", multi_constructor)


def load_yaml(yaml_content: str) -> Dict[str, Any]:
    """
    Load CloudFormation YAML with support for intrinsic functions.
    
    Args:
        yaml_content: String containing YAML content
        
    Returns:
        Dict representation of the CloudFormation template
    """
    return yaml.load(yaml_content, Loader=CloudFormationYAMLLoader)
