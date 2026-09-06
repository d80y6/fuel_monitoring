import datetime
from decimal import Decimal


class BaseModel:
    """Base model class with common functionality."""

    def to_dict(self):
        """Convert model to dictionary."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime.datetime):
                value = value.isoformat()
            elif isinstance(value, Decimal):
                value = float(value)
            result[column.name] = value
        return result
