"""
Stair event handlers for EstiSketch canvas.

This module provides methods for placing and editing stairs,
including automatic calculation of dimensions based on levels.
"""
import math
from typing import Tuple, Dict
from ..components import Stair, Level


class CanvasStairEventsMixin:
    """Mixin for stair-related canvas events and operations."""

    def _handle_stair_click(self, n_press, x, y):
        """Handle click events for stair tool."""
        # Convert to model coordinates
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        model_x, model_y = self.device_to_model(x, y, pixels_per_inch)
        
        if getattr(self, "action_state", "idle") == "idle":
            self._start_adding_stair(model_x, model_y)
        elif self.action_state == "adding_stair_direction":
            self.finish_adding_stair()

    def _start_adding_stair(self, x, y):
        """Start the process of adding a stair."""
        self.temp_start_point = (x, y)
        self.temp_current_point = (x, y)
        
        # Calculate initial defaults based on levels
        start_level_id = self.active_level_id
        end_level_id = self._get_next_level_up(start_level_id)
        
        # Default rise calculation
        total_rise = self._calculate_default_rise(start_level_id, end_level_id)
        
        # Calculate optimal steps
        num_steps, riser_height = self._calculate_optimal_steps(total_rise)
        
        # Calculate run
        tread_depth = 11.0
        total_run = (num_steps - 1) * tread_depth
        
        # Create temporary stair for preview
        self.temp_object = Stair(
            start_point=(x, y),
            direction_angle=0.0,
            start_level_id=start_level_id,
            end_level_id=end_level_id,
            total_rise=total_rise,
            riser_height=riser_height,
            num_steps=num_steps,
            tread_depth=tread_depth,
            total_run=total_run
        )
        
        self.action_state = "adding_stair_direction"
        self.queue_draw()

    def _handle_stair_motion(self, x, y):
        """Handle motion events for stair tool."""
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        model_x, model_y = self.device_to_model(x, y, pixels_per_inch)
        
        if getattr(self, "action_state", None) == "adding_stair_direction":
            self._update_adding_stair(model_x, model_y)

    def _update_adding_stair(self, x, y):
        """Update the stair preview while moving mouse."""
        if not self.temp_object:
            return
            
        self.temp_current_point = (x, y)
        
        # Update direction angle
        dx = x - self.temp_object.start_point[0]
        dy = y - self.temp_object.start_point[1]
        
        # Only update if moved far enough to determine direction
        if math.hypot(dx, dy) > 5.0:
            angle = math.atan2(dy, dx)
            
            # Snap angle to 45 degrees if snap is enabled
            # Check if snap is enabled via config or snap manager
            snap_enabled = getattr(self.config, 'SNAP_ENABLED', True) if hasattr(self, 'config') else True
            
            if snap_enabled: 
                 # Simple angle snapping to 45 degrees
                 angle_deg = math.degrees(angle)
                 snapped_deg = round(angle_deg / 45) * 45
                 angle = math.radians(snapped_deg)
            
            self.temp_object.direction_angle = angle
            
        self.queue_draw()

    def finish_adding_stair(self):
        """Finalize stair placement."""
        if not self.temp_object:
            return
            
        # Generate identifier
        stair_id = self.generate_identifier("stair", self.existing_ids)
        self.temp_object.identifier = stair_id
        self.temp_object.layer_id = self.active_layer_id
        
        # Add to canvas
        self.stairs.append(self.temp_object)
        
        # Notify layers panel
        self.emit('content-changed')
        
        # Clean up
        self.temp_object = None
        self.temp_start_point = None
        self.action_state = "idle"
        
        # Save state
        self.save_state()
        self.queue_draw()
        print(f"Added stair: {stair_id}")

    def _get_next_level_up(self, current_level_id: str) -> str:
        """Find the ID of the level immediately above the current one."""
        if not current_level_id:
            return ""
            
        current_level = self.get_level_by_id(current_level_id)
        if not current_level:
            return ""
            
        # Sort levels by elevation
        sorted_levels = sorted(self.levels, key=lambda l: l.elevation)
        
        for i, level in enumerate(sorted_levels):
            if level.id == current_level_id:
                if i + 1 < len(sorted_levels):
                    return sorted_levels[i+1].id
                break
        
        return ""

    def _calculate_default_rise(self, start_level_id: str, end_level_id: str) -> float:
        """Calculate total rise based on levels."""
        # Default fallback (8ft + 10in floor)
        default_rise = 106.0
        
        if not start_level_id:
            return default_rise
            
        start_level = self.get_level_by_id(start_level_id)
        if not start_level:
            return default_rise
            
        if end_level_id:
            end_level = self.get_level_by_id(end_level_id)
            if end_level:
                # Rise is height difference
                return end_level.elevation - start_level.elevation
        
        # If no end level or end level not found, use start level height + floor thickness
        return start_level.height + getattr(start_level, 'floor_thickness', 10.0)

    def _calculate_optimal_steps(self, total_rise: float) -> Tuple[int, float]:
        """
        Calculate optimal number of steps and riser height.
        Target riser height: ~7.5 inches (IRC max is 7.75)
        """
        target_riser = 7.5
        max_riser = 7.75
        
        # First try target
        num_steps = math.ceil(total_rise / target_riser)
        riser_height = total_rise / num_steps
        
        # If result exceeds max due to rounding oddities (unlikely with ceil), adjust
        if riser_height > max_riser:
            num_steps += 1
            riser_height = total_rise / num_steps
            
        return num_steps, riser_height

    def check_stair_compliance(self, stair: Stair) -> Dict:
        """Check stair against common building codes (IRC)."""
        warnings = []
        
        # Riser height (IRC max 7 3/4 inch)
        if stair.riser_height > 7.75:
            warnings.append(f"Riser height {stair.riser_height:.2f}\" exceeds IRC max (7.75\")")
        elif stair.riser_height < 4.0:
            warnings.append(f"Riser height {stair.riser_height:.2f}\" is unusually low")
            
        # Tread depth (IRC min 10 inch)
        if stair.tread_depth < 10.0:
            warnings.append(f"Tread depth {stair.tread_depth:.2f}\" is below IRC min (10\")")
            
        # Width (IRC min 36 inch)
        if stair.width < 36.0:
            warnings.append(f"Width {stair.width:.2f}\" is below IRC min (36\")")
            
        return {
            "compliant": len(warnings) == 0,
            "warnings": warnings
        }

    def get_level_by_id(self, level_id: str) -> Level:
        """Helper to find level object by ID."""
        for level in self.levels:
            if level.id == level_id:
                return level
        return None

    def update_stairs_for_level_change(self, changed_level_id: str):
        """
        Recalculate rise and run for stairs connected to the changed level.
        Called when a level's elevation is updated.
        """
        if not changed_level_id:
            return

        stairs_updated = False
        
        for stair in self.stairs:
            # Check if this stair is connected to the changed level
            update_needed = False
            start = getattr(stair, 'start_level_id', None)
            end = getattr(stair, 'end_level_id', None)
            
            if start == changed_level_id:
                update_needed = True
            if end == changed_level_id:
                update_needed = True
                
            if update_needed:
                # Recalculate total rise
                new_rise = self._calculate_default_rise(stair.start_level_id, stair.end_level_id)
                
                # Check if rise actually changed
                if abs(new_rise - stair.total_rise) > 0.01:
                    stair.total_rise = new_rise
                    
                    # Update riser height (keep number of steps constant usually, unless extreme?)
                    # Strategy: Keep num_steps constant, update riser_height.
                    # This preserves the run length.
                    if stair.num_steps > 0:
                        stair.riser_height = new_rise / stair.num_steps
                    
                    stairs_updated = True
        
        if stairs_updated:
            self.queue_draw()
            
            # If any of the updated stairs are selected, refresh the properties panel
            # to verify they show the new rise value immediately.
            if getattr(self, "selected_items", None) and hasattr(self, "properties_dock"):
                 # Check if any selected item is a stair that might have been updated
                 # For simplicity, just refresh if we have a stair selection
                 has_selected_stair = any(item.get("type") == "stair" for item in self.selected_items)
                 if has_selected_stair:
                     self.properties_dock.refresh_tabs(self.selected_items)

