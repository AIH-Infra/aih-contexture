from typing import Any, Type, Union, Optional
from pydantic import BaseModel, Field, create_model, validator
from enum import Enum
import re
from datetime import datetime
from uuid import UUID


def json_schema_to_base_model(
    schema: dict[str, Any], model_name: str = None
) -> Type[BaseModel]:
    """Convert a JSON schema to a Pydantic BaseModel dynamically."""

    # Enhanced type mapping with format support
    def get_type_from_schema(field_props: dict[str, Any]) -> type:
        json_type = field_props.get("type", "string")
        format_type = field_props.get("format")

        # Handle format-specific types
        if json_type == "string":
            if format_type == "date-time":
                return datetime
            elif format_type == "uuid":
                return UUID
            else:
                return str
        elif json_type == "integer":
            return int
        elif json_type == "number":
            return float
        elif json_type == "boolean":
            return bool
        elif json_type == "array":
            return list
        elif json_type == "object":
            return dict
        else:
            return str  # fallback

    def handle_union_types(field_props: dict[str, Any]) -> type:
        """Handle anyOf, oneOf, and type arrays."""
        any_of = field_props.get("anyOf", [])
        one_of = field_props.get("oneOf", [])
        type_list = field_props.get("type", [])

        if any_of:
            types = [get_type_from_schema(schema) for schema in any_of]
            return Union[tuple(types)]
        elif one_of:
            types = [get_type_from_schema(schema) for schema in one_of]
            return Union[tuple(types)]
        elif isinstance(type_list, list):
            types = [get_type_from_schema({"type": t}) for t in type_list]
            return Union[tuple(types)]

        return None

    def create_validator_from_constraints(field_name: str, field_props: dict[str, Any]):
        """Create Pydantic validators from JSON schema constraints."""
        validators = {}

        # String constraints
        if "minLength" in field_props:
            min_len = field_props["minLength"]

            def min_length_validator(cls, v):
                if isinstance(v, str) and len(v) < min_len:
                    raise ValueError(
                        f"{field_name} must be at least {min_len} characters"
                    )
                return v

            validators[f"{field_name}_min_length"] = validator(
                field_name, allow_reuse=True
            )(min_length_validator)

        if "maxLength" in field_props:
            max_len = field_props["maxLength"]

            def max_length_validator(cls, v):
                if isinstance(v, str) and len(v) > max_len:
                    raise ValueError(
                        f"{field_name} must be at most {max_len} characters"
                    )
                return v

            validators[f"{field_name}_max_length"] = validator(
                field_name, allow_reuse=True
            )(max_length_validator)

        if "pattern" in field_props:
            pattern = field_props["pattern"]

            def pattern_validator(cls, v):
                if isinstance(v, str) and not re.match(pattern, v):
                    raise ValueError(f"{field_name} must match pattern {pattern}")
                return v

            validators[f"{field_name}_pattern"] = validator(
                field_name, allow_reuse=True
            )(pattern_validator)

        # Numeric constraints
        if "minimum" in field_props:
            min_val = field_props["minimum"]

            def min_validator(cls, v):
                if isinstance(v, (int, float)) and v < min_val:
                    raise ValueError(f"{field_name} must be at least {min_val}")
                return v

            validators[f"{field_name}_minimum"] = validator(
                field_name, allow_reuse=True
            )(min_validator)

        if "maximum" in field_props:
            max_val = field_props["maximum"]

            def max_validator(cls, v):
                if isinstance(v, (int, float)) and v > max_val:
                    raise ValueError(f"{field_name} must be at most {max_val}")
                return v

            validators[f"{field_name}_maximum"] = validator(
                field_name, allow_reuse=True
            )(max_validator)

        return validators

    def process_field(field_name: str, field_props: dict[str, Any]) -> tuple:
        """Process a single field from the schema."""

        # Handle const values
        if "const" in field_props:
            const_value = field_props["const"]
            return type(const_value), Field(default=const_value, const=True)

        # Handle enums
        enum_values = field_props.get("enum")
        if enum_values:
            enum_name = f"{field_name.capitalize()}Enum"
            field_type = Enum(enum_name, {str(v): v for v in enum_values})

        # Handle union types (anyOf, oneOf, type arrays)
        elif union_type := handle_union_types(field_props):
            field_type = union_type

        # Handle nested objects
        elif field_props.get("type") == "object" and "properties" in field_props:
            nested_model_name = f"{field_name.capitalize()}Model"
            field_type = json_schema_to_base_model(field_props, nested_model_name)

        # Handle arrays
        elif field_props.get("type") == "array" and "items" in field_props:
            item_props = field_props["items"]

            # Handle array of objects
            if item_props.get("type") == "object" and "properties" in item_props:
                item_model_name = f"{field_name.capitalize()}ItemModel"
                item_type = json_schema_to_base_model(item_props, item_model_name)
            else:
                item_type = get_type_from_schema(item_props)

            field_type = list[item_type]

        # Handle primitive types
        else:
            field_type = get_type_from_schema(field_props)

        # Handle nullable
        if field_props.get("nullable", False):
            field_type = Optional[field_type]

        # Determine default value
        if "default" in field_props:
            default_value = field_props["default"]
        elif field_name not in schema.get("required", []):
            default_value = None
            if not field_props.get("nullable", False):
                field_type = Optional[field_type]
        else:
            default_value = ...

        # Create field with metadata
        field_info = Field(
            default=default_value,
            description=field_props.get("description", field_props.get("title", "")),
            title=field_props.get("title"),
            examples=field_props.get("examples"),
        )

        return field_type, field_info

    # Process schema
    properties = schema.get("properties", {})
    model_fields = {}
    validators = {}

    # Process each field
    for field_name, field_props in properties.items():
        model_fields[field_name] = process_field(field_name, field_props)

        # Add validators for constraints
        field_validators = create_validator_from_constraints(field_name, field_props)
        validators.update(field_validators)

    # Create the model
    model_name = model_name or schema.get("title", "DynamicModel")

    # Create model with validators
    model_class = create_model(model_name, **model_fields, __validators__=validators)

    return model_class
