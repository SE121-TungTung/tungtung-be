from pydantic import create_model, Field
from sqlalchemy.inspection import inspect
from sqlalchemy import String, Integer, Boolean, DateTime, Float, Text, JSON, UUID
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from typing import Optional, get_type_hints, Union, Any, List
import datetime
import logging
import uuid

logger = logging.getLogger(__name__)

def sqlalchemy_to_pydantic_type(column):
    """Convert SQLAlchemy column type to Python type with better handling"""
    try:
        # Handle PostgreSQL UUID specifically
        if isinstance(column.type, (UUID, PG_UUID)):
            return uuid.UUID
        
        # Handle JSON fields
        if isinstance(column.type, JSON):
            return dict
        
        # Handle standard types
        python_type = column.type.python_type
        
    except (NotImplementedError, AttributeError):
        # Fallback for complex types
        if isinstance(column.type, (String, Text)):
            python_type = str
        elif isinstance(column.type, Integer):
            python_type = int
        elif isinstance(column.type, Float):
            python_type = float
        elif isinstance(column.type, Boolean):
            python_type = bool
        elif isinstance(column.type, DateTime):
            python_type = datetime.datetime
        else:
            python_type = str
    
    # Handle nullable columns
    if column.nullable:
        return Optional[python_type]
    return python_type

def get_column_default(column):
    """Get default value from SQLAlchemy column with better handling"""
    # Check for client-side default
    if column.default is not None:
        if hasattr(column.default, 'arg'):
            default_value = column.default.arg
            if callable(default_value):
                try:
                    # Handle functions like uuid.uuid4
                    if default_value.__name__ == 'uuid4':
                        return Field(default_factory=uuid.uuid4)
                    return default_value()
                except:
                    return None
            return default_value
    
    # Server defaults can't be evaluated client-side
    if column.server_default is not None:
        return None
    
    # Required field if not nullable and no default
    if not column.nullable:
        return ...
    
    return None

def get_field_constraints(column):
    """Extract field constraints for validation"""
    constraints = {}
    
    # String length constraints
    if hasattr(column.type, 'length') and column.type.length:
        constraints['max_length'] = column.type.length
    
    # Numeric constraints (if any check constraints exist)
    # This is basic - could be expanded for more complex constraints
    
    return constraints

def create_pydantic_model_from_sqlalchemy(
    sqlalchemy_model,
    model_name: str,
    exclude_fields: List[str] = None,
    include_relationships: bool = False,
    optional_fields: List[str] = None,
    required_fields: List[str] = None
):
    """Enhanced auto-generate Pydantic model from SQLAlchemy model"""
    exclude_fields = exclude_fields or []
    optional_fields = optional_fields or []
    required_fields = required_fields or []
    
    fields = {}
    mapper = inspect(sqlalchemy_model)
    
    # Process columns
    for column in mapper.columns:
        if column.name in exclude_fields:
            continue
        
        try:
            python_type = sqlalchemy_to_pydantic_type(column)
            
            # Override optionality based on parameters
            if column.name in optional_fields:
                if not _is_optional_type(python_type):
                    python_type = Optional[python_type]
            elif column.name in required_fields:
                if _is_optional_type(python_type):
                    # Extract the non-optional type
                    python_type = python_type.__args__[0]
            
            # Get default value
            default_value = get_column_default(column)
            
            # Get constraints
            constraints = get_field_constraints(column)
            
            # Create Field with all information
            field_kwargs = {
                'description': f"{column.name.replace('_', ' ').title()}",
                'example': _get_example_value(python_type, column.name),
                **constraints
            }
            
            if default_value is not None:
                if isinstance(default_value, Field):
                    # If it's already a Field (like uuid default_factory)
                    field_kwargs.update(default_value.__dict__)
                    field_info = Field(**field_kwargs)
                else:
                    field_info = Field(default=default_value, **field_kwargs)
            else:
                field_info = Field(**field_kwargs)
            
            fields[column.name] = (python_type, field_info)
            
        except Exception as e:
            logger.warning(f"Could not process column {column.name}: {e}")
            # Fallback to optional string
            fields[column.name] = (Optional[str], Field(default=None))
    
    # Add relationships if requested
    if include_relationships:
        for relationship in mapper.relationships:
            if relationship.key not in exclude_fields:
                # Import here to avoid circular imports
                from typing import TYPE_CHECKING
                if TYPE_CHECKING:
                    fields[relationship.key] = (Optional[Any], Field(default=None))
                else:
                    fields[relationship.key] = (Optional[dict], Field(default=None))
    
    return create_model(model_name, **fields)

def _is_optional_type(type_hint):
    """Check if a type hint is Optional[T]"""
    return (hasattr(type_hint, '__origin__') and 
            type_hint.__origin__ is Union and
            type(None) in type_hint.__args__)

def _get_example_value(python_type, field_name: str):
    """Generate realistic example values for OpenAPI docs"""
    # Handle Optional types
    if _is_optional_type(python_type):
        python_type = python_type.__args__[0]
    
    # Field-specific examples
    field_examples = {
        'email': 'user@example.com',
        'phone': '+1234567890',
        'name': 'Example Name',
        'first_name': 'John',
        'last_name': 'Doe',
        'title': 'Example Title',
        'description': 'This is an example description',
        'password': 'SecurePassword123',
        'url': 'https://example.com',
        'address': '123 Main St, City, State',
    }
    
    for key, value in field_examples.items():
        if key in field_name.lower():
            return value
    
    # Type-based examples
    if python_type == str:
        return 'example string'
    elif python_type == int:
        return 42
    elif python_type == float:
        return 123.45
    elif python_type == bool:
        return True
    elif python_type == datetime.datetime:
        return '2024-01-01T00:00:00Z'
    elif python_type == datetime.date:
        return '2024-01-01'
    elif python_type == uuid.UUID:
        return str(uuid.uuid4())
    elif python_type == dict:
        return {}
    
    return None

# Auto-generate schema sets for a model
def generate_model_schemas(sqlalchemy_model, exclude_audit_fields: bool = True):
    """Generate Create, Update, and Response schemas for a model"""
    model_name = sqlalchemy_model.__name__
    
    # Standard fields to exclude
    base_exclude = ['id'] if exclude_audit_fields else []
    audit_exclude = ['created_at', 'updated_at', 'created_by', 'updated_by'] if exclude_audit_fields else []
    
    # Response schema (include everything)
    response_schema = create_pydantic_model_from_sqlalchemy(
        sqlalchemy_model,
        f"{model_name}Response"
    )
    
    # Create schema (exclude id and audit fields)
    create_schema = create_pydantic_model_from_sqlalchemy(
        sqlalchemy_model,
        f"{model_name}Create",
        exclude_fields=base_exclude + audit_exclude
    )
    
    # Update schema (exclude id, audit fields, make everything optional)
    mapper = inspect(sqlalchemy_model)
    all_fields = [col.name for col in mapper.columns if col.name not in base_exclude + audit_exclude]
    
    update_schema = create_pydantic_model_from_sqlalchemy(
        sqlalchemy_model,
        f"{model_name}Update",
        exclude_fields=base_exclude + audit_exclude,
        optional_fields=all_fields
    )
    
    return {
        'response': response_schema,
        'create': create_schema,
        'update': update_schema
    }