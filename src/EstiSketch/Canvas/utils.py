from typing import Collection, List, Optional
import uuid


def generate_identifier(
        component_type: str,
        existing_ids: Optional[Collection[str]] = None) -> str:
    """Generate a unique identifier for a component in Sweet Home 3D format.

    The identifier format matches Sweet Home 3D (HomeObject.createId):
        {component_type}-{8 hex}-{4 hex}-{4 hex}-{4 hex}-{12 hex}

    Example:
        wall-0f3253ce-86f9-4286-97df-beaae4a53ece

    Parameters:
        component_type (str): The type of component (e.g., "wall", "door").
        existing_ids (Optional[Collection[str]]): Existing identifiers to
            ensure uniqueness.
    """
    prefix = component_type.lower()
    existing = existing_ids if existing_ids is not None else ()
    while True:
        identifier = f"{prefix}-{uuid.uuid4()}"
        if identifier not in existing:
            return identifier


class UtilsMixin:
    def generate_identifier(
            self,
            component_type: str,
            existing_ids: Optional[List[str]] = None) -> str:
        """Generate a unique identifier for a component."""
        return generate_identifier(component_type, existing_ids)
