from pydantic import create_model, Field
from sqlalchemy.inspection import inspect
from sqlalchemy import String, Integer, Boolean, DateTime, Float, Text, JSON, UUID
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import Enum as SQLEnum
from typing import Optional, get_type_hints, Union, Any, List, Dict, Type
import datetime
import logging
import uuid
from decimal import Decimal
import enum

logger = logging.getLogger(__name__)

def _is_valid_type(obj):
    """Kiểm tra xem obj có phải là một valid Python type class không"""
    try:
        # Type class thực sự
        if isinstance(obj, type):
            return True
        # Decimal là một exception
        if obj == Decimal or obj is Decimal:
            return True
        # Typing objects (Optional, Union, List, Dict, etc)
        if hasattr(obj, '__origin__'):
            return True
        return False
    except TypeError:
        return False

def _is_enum_type(python_type):
    """Check if a type is an Enum"""
    try:
        return isinstance(python_type, type) and issubclass(python_type, enum.Enum)
    except (TypeError, AttributeError):
        return False

def sqlalchemy_to_pydantic_type(column):
    """Convert SQLAlchemy column type to Python type with better handling and error checks."""
    
    python_type: Type = str 

    # 1. Handle PostgreSQL UUID
    if isinstance(column.type, (UUID, PG_UUID)):
        python_type = uuid.UUID
    
    # 2. Handle JSON fields
    elif isinstance(column.type, JSON):
        python_type = dict
        
    # 3. Handle SQLAlchemy Enum
    elif isinstance(column.type, SQLEnum):
        try:
            # Ưu tiên sử dụng Enum Class
            python_type = column.type.enum_class
        except AttributeError:
            python_type = str
    
    # 4. Handle standard types
    else:
        try:
            resolved_type = column.type.python_type
            
            if not _is_valid_type(resolved_type):
                raise TypeError("python_type attribute is not a valid type class.")
            
            python_type = resolved_type
                
        except (NotImplementedError, AttributeError, TypeError) as e:
            logger.debug(f"Column {column.name}: python_type resolution failed ({e}), falling back to isinstance checks")
            
            # 5. Fallback cho các kiểu phức tạp
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
            elif 'decimal' in str(type(column.type)).lower() or 'numeric' in str(type(column.type)).lower():
                python_type = Decimal
            else:
                python_type = str
                logger.warning(f"Column {column.name}: Unable to determine type for {type(column.type)}, using str fallback")
    
    # Handle nullable columns
    if column.nullable:
        if _is_valid_type(python_type) and not hasattr(python_type, '__origin__'):
            return Optional[python_type]
        
        if hasattr(python_type, '__origin__'):
            return python_type

        logger.warning(f"Final type check failed for nullable column {column.name}. Type: {python_type}. Falling back to Optional[str].")
        return Optional[str]

    # Trường hợp NON-NULLABLE
    if _is_valid_type(python_type):
        return python_type
    
    logger.warning(f"Final type check failed for required column {column.name}. Type: {python_type}. Falling back to str.")
    return str


def get_column_default(column):
    """Get default value from SQLAlchemy column with better handling"""
    try:
        if column.default is not None:
            if hasattr(column.default, 'arg'):
                default_value = column.default.arg
                if callable(default_value):
                    try:
                        if hasattr(default_value, '__name__') and default_value.__name__ == 'uuid4':
                            return Field(default_factory=uuid.uuid4)
                        return default_value()
                    except Exception as e:
                        logger.debug(f"Failed to call default function: {e}")
                        return None
                return default_value
        
        if column.server_default is not None:
            return None
        
        if not column.nullable:
            return ... # Dấu chấm lửng nghĩa là BẮT BUỘC (required field)
        
        return None
    except Exception as e:
        logger.debug(f"Error getting column default for {column.name}: {e}")
        return None

def get_field_constraints(column):
    """Extract field constraints for validation"""
    constraints = {}
    
    if isinstance(column.type, SQLEnum):
        return constraints

    # Chỉ áp dụng max_length cho String/Text types, không cho Enum
    if isinstance(column.type, (String, Text)):
        if hasattr(column.type, 'length') and column.type.length:
            constraints['max_length'] = column.type.length
    
    return constraints

def _is_optional_type(type_hint):
    """Check if a type hint is Optional[T]"""
    try:
        return (hasattr(type_hint, '__origin__') and 
                type_hint.__origin__ is Union and
                type(None) in type_hint.__args__)
    except (AttributeError, TypeError):
        return False

def _get_example_value(python_type, field_name: str):
    """Generate realistic example values for OpenAPI docs"""
    try:
        # --- FIX: Trích xuất Base Type an toàn ---
        base_type = python_type
        if _is_optional_type(python_type):
            non_none_args = [arg for arg in python_type.__args__ if arg is not type(None)]
            base_type = non_none_args[0] if non_none_args else str
        
        # SỬ DỤNG base_type cho tất cả các kiểm tra tiếp theo
        
        # Field-specific examples (giữ nguyên)
        field_examples = {
            'email': 'user@example.com', 'phone': '+1234567890', 'name': 'Example Name',
            'first_name': 'John', 'last_name': 'Doe', 'title': 'Example Title',
            'description': 'This is an example description', 'password': 'SecurePassword123',
            'url': 'https://example.com', 'address': '123 Main St, City, State',
        }
        
        for key, value in field_examples.items():
            if key in field_name.lower():
                return value
        
        # Handle Enum types
        if _is_enum_type(base_type):
            try:
                first_member = next(iter(base_type))
                return str(first_member.value)
            except (StopIteration, AttributeError):
                return None
        
        # --- Type-based examples ---
        if base_type == str: return 'example string'
        elif base_type == int: 
            # Cung cấp ví dụ Integer hợp lý hơn cho các trường phổ biến
            if 'capacity' in field_name.lower() or 'max_students' in field_name.lower():
                return 20
            elif 'hour' in field_name.lower():
                return 60
            return 42
        elif base_type == float: return 123.45
        elif base_type == bool: return True
        elif base_type == datetime.datetime: return '2024-01-01T00:00:00Z'
        elif base_type == datetime.date: return '2024-01-01'
        elif base_type == uuid.UUID: return str(uuid.uuid4())
        elif base_type == dict: return {}
        elif base_type == Decimal or base_type is Decimal: return 999.99
        
        return None
    except Exception as e:
        logger.debug(f"Error generating example value for {field_name}: {e}")
        return None

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
            
            # Khởi tạo giá trị mặc định
            default_value = get_column_default(column)
            
            # --- LOGIC GHI ĐÈ BẮT BUỘC CHO UPDATE SCHEMA (PARTIAL UPDATE) ---
            is_explicitly_optional = column.name in optional_fields
            
            if is_explicitly_optional:
                # 1. Buộc kiểu dữ liệu là Optional[T]
                if not _is_optional_type(python_type):
                    python_type = Optional[python_type]
                    
                # 2. Buộc giá trị mặc định là None (thay thế ...) để trở thành tùy chọn
                if default_value is ...:
                    default_value = None 
            # -------------------------------------------------------------------
            
            # Logic required_fields (giữ nguyên)
            elif column.name in required_fields:
                if _is_optional_type(python_type):
                    non_none_args = [arg for arg in python_type.__args__ if arg is not type(None)]
                    if non_none_args:
                        python_type = non_none_args[0]
                    else:
                        python_type = str
            
            # Validate type
            if not _is_valid_type(python_type):
                logger.warning(f"Invalid type {python_type} for column {column.name}. Using Optional[str].")
                raise TypeError(f"Resolved type {python_type} is not a valid Python type class.")

            # Get constraints
            constraints = get_field_constraints(column)
            
            # Create Field with all information
            field_kwargs = {
                'description': f"{column.name.replace('_', ' ').title()}",
                **constraints
            }
            
            # Add example safely
            example_value = _get_example_value(python_type, column.name)
            if example_value is not None:
                field_kwargs['example'] = example_value
            
            # Handle default value safely
            if default_value is not None:
                if hasattr(default_value, '__class__') and default_value.__class__.__name__ == 'FieldInfo':
                    # Handle Field(default_factory)
                    field_info = Field(default=default_value.default, **field_kwargs)
                else:
                    field_info = Field(default=default_value, **field_kwargs)
            else:
                # Nếu default_value là None, Field sẽ coi là tùy chọn và mặc định là None
                field_info = Field(default=None, **field_kwargs)
            
            fields[column.name] = (python_type, field_info)
            
        except Exception as e:
            logger.warning(
                f"Column processing failed for '{column.name}'. Using Optional[str] as fallback. "
                f"Original error: {str(e)}"
            )
            # Fallback to optional string
            fields[column.name] = (Optional[str], Field(default=None, description=f"{column.name.replace('_', ' ').title()}"))
    
    # Add relationships if requested
    if include_relationships:
        for relationship in mapper.relationships:
            if relationship.key not in exclude_fields:
                try:
                    from typing import TYPE_CHECKING
                    if TYPE_CHECKING:
                        fields[relationship.key] = (Optional[Any], Field(default=None))
                    else:
                        fields[relationship.key] = (Optional[dict], Field(default=None))
                except Exception as e:
                    logger.debug(f"Error adding relationship {relationship.key}: {e}")
    
    return create_model(model_name, **fields)

# Auto-generate schema sets for a model
def generate_model_schemas(sqlalchemy_model, exclude_audit_fields: bool = True):
    """Generate Create, Update, and Response schemas for a model"""
    model_name = sqlalchemy_model.__name__
    
    # Standard fields to exclude
    base_exclude = ['id'] if exclude_audit_fields else []
    audit_exclude = ['created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at'] if exclude_audit_fields else []
    
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
        optional_fields=all_fields # Đảm bảo TẤT CẢ các trường này được xử lý là optional
    )
    
    return {
        'response': response_schema,
        'create': create_schema,
        'update': update_schema
    }