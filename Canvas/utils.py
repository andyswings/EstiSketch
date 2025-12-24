import random
import string
from typing import List

class UtilsMixin:
    def generate_identifier(self, component_type: str, existing_ids: List[str]) -> str:
        ''' Generate a unique identifier for a component.
    
         The identifier format is: {component_type}-{8 chars}-{4 chars}-{4 chars}-{4 chars}-{12 chars}
         
         Example: wall-A1B2C3D4-E5F6-G7H8-I9J0-K1L2M3N4O5P6
         
         Parameters:
             component_type (str): The type of component (e.g., "wall", "door").
             existing_ids (List[str]): List of existing identifiers to ensure uniqueness.'''
        characters = string.ascii_letters + string.digits
        while True:
            pt1 = ''.join(random.choices(characters, k=8))
            pt2 = ''.join(random.choices(characters, k=4))
            pt3 = ''.join(random.choices(characters, k=4))
            pt4 = ''.join(random.choices(characters, k=4))
            pt5 = ''.join(random.choices(characters, k=12))
            identifier = f"{component_type}-{pt1}-{pt2}-{pt3}-{pt4}-{pt5}".lower()
            if identifier not in existing_ids:
                return identifier
