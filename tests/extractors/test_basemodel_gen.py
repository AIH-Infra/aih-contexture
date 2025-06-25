from marker.extractors.util import json_schema_to_base_model


def test_model_generator():
    test_schema = {
        "title": "UserModel",
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "format": "email",
                "description": "User's email address",
            },
            "age": {"type": "integer", "minimum": 0, "maximum": 150},
            "name": {"type": "string", "minLength": 1, "maxLength": 100},
            "status": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "tags": {"type": "array", "items": {"type": "string"}},
            "preferences": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string", "enum": ["dark", "light"]},
                    "notifications": {"type": "boolean", "default": True},
                },
            },
            "role": {
                "type": "string",
                "enum": ["admin", "user", "guest"],
                "default": "user",
            },
        },
        "required": ["email", "name"],
    }

    # Create the model
    UserModel = json_schema_to_base_model(test_schema)
    user = UserModel(
        email="test@example.com",
        name="John Doe",
        age=30,
        tags=["python", "pydantic"],
        preferences={"theme": "dark"},
        role="admin",
    )
    assert user is not None
