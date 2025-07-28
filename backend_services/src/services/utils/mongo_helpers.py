from bson import ObjectId
from typing import Any
from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

class PyObjectId(ObjectId):
    """Custom ObjectId class for Pydantic v2 models"""
    
    @classmethod
    def __get_pydantic_core_schema__(
        cls, 
        source_type: Any, 
        handler: Any
    ) -> core_schema.CoreSchema:
        """Define how to generate the core schema for PyObjectId"""
        def validate_object_id(value: Any, validation_info=None) -> ObjectId:
            if isinstance(value, ObjectId):
                return value
            if isinstance(value, str):
                return ObjectId(value)
            raise ValueError(f"Invalid ObjectId: {value}")
        
        return core_schema.with_info_plain_validator_function(
            validate_object_id,
            serialization=core_schema.to_string_ser_schema(),
        )
    
    @classmethod
    def __get_pydantic_json_schema__(
        cls, 
        core_schema: core_schema.CoreSchema, 
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Define the JSON schema for PyObjectId"""
        return {
            "type": "string",
            "format": "objectid"
        }