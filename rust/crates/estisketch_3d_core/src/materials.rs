//! Warm architectural PBR & procedural material preset catalog.

use crate::mesh::{MaterialDef, MaterialStyle};

fn color3(rgb: Option<[f64; 3]>, fallback: [f32; 3]) -> [f32; 4] {
    if let Some([r, g, b]) = rgb {
        [
            (r as f32).clamp(0.0, 1.0),
            (g as f32).clamp(0.0, 1.0),
            (b as f32).clamp(0.0, 1.0),
            1.0,
        ]
    } else {
        [fallback[0], fallback[1], fallback[2], 1.0]
    }
}

/// Resolve an EstiSketch wall finish name & optional RGB tint into a [`MaterialDef`].
pub fn wall_finish_material(finish: &str, rgb_override: Option<[f64; 3]>) -> MaterialDef {
    let lower = finish.trim().to_lowercase();
    if lower.contains("brick") {
        MaterialDef {
            name: finish.to_string(),
            base_color: color3(rgb_override, [0.58, 0.29, 0.23]),
            roughness: 0.85,
            metallic: 0.0,
            style: MaterialStyle::Brick,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else if lower.contains("stone") {
        MaterialDef {
            name: finish.to_string(),
            base_color: color3(rgb_override, [0.56, 0.54, 0.50]),
            roughness: 0.88,
            metallic: 0.0,
            style: MaterialStyle::Stone,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else if lower.contains("siding") || lower.contains("lap") || lower.contains("board") {
        MaterialDef {
            name: finish.to_string(),
            base_color: color3(rgb_override, [0.64, 0.68, 0.65]),
            roughness: 0.78,
            metallic: 0.0,
            style: MaterialStyle::Siding,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else if lower.contains("tile") {
        MaterialDef {
            name: finish.to_string(),
            base_color: color3(rgb_override, [0.85, 0.84, 0.80]),
            roughness: 0.42,
            metallic: 0.0,
            style: MaterialStyle::Tile,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else if lower.contains("wood") || lower.contains("cedar") {
        MaterialDef {
            name: finish.to_string(),
            base_color: color3(rgb_override, [0.58, 0.41, 0.27]),
            roughness: 0.68,
            metallic: 0.0,
            style: MaterialStyle::Wood,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else if lower.contains("stucco") {
        MaterialDef {
            name: finish.to_string(),
            base_color: color3(rgb_override, [0.87, 0.83, 0.76]),
            roughness: 0.88,
            metallic: 0.0,
            style: MaterialStyle::Solid,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else {
        MaterialDef {
            name: if finish.is_empty() {
                "Drywall".to_string()
            } else {
                finish.to_string()
            },
            base_color: color3(rgb_override, [0.91, 0.89, 0.85]),
            roughness: 0.82,
            metallic: 0.0,
            style: MaterialStyle::Solid,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    }
}

/// Resolve a room floor material from `floor_pattern`, `rotation_deg`, and `scale`.
pub fn floor_material(pattern: &str, rotation_deg: f64, scale: f64) -> MaterialDef {
    let lower = pattern.trim().to_lowercase();
    let (base, style, rough) = if lower.contains("wood")
        || lower.contains("plank")
        || lower.contains("lvp")
        || lower.contains("herringbone")
        || lower.contains("chevron")
    {
        ([0.63, 0.46, 0.30, 1.0], MaterialStyle::Wood, 0.56)
    } else if lower.contains("tile") || lower.contains("hex") || lower.contains("basket") {
        ([0.82, 0.80, 0.76, 1.0], MaterialStyle::Tile, 0.42)
    } else if lower.contains("carpet") {
        ([0.74, 0.72, 0.68, 1.0], MaterialStyle::Solid, 0.94)
    } else if lower.contains("concrete") {
        ([0.62, 0.62, 0.60, 1.0], MaterialStyle::Stone, 0.88)
    } else {
        ([0.76, 0.69, 0.58, 1.0], MaterialStyle::Wood, 0.65)
    };
    MaterialDef {
        name: format!("Floor:{pattern}"),
        base_color: base,
        roughness: rough,
        metallic: 0.0,
        style,
        pattern_scale: (scale as f32).clamp(0.25, 4.0),
        pattern_rotation_deg: rotation_deg as f32,
        transparent: false,
    }
}

/// Ceiling surface material (soft matte architectural white).
pub fn ceiling_material() -> MaterialDef {
    MaterialDef {
        name: "Ceiling".to_string(),
        base_color: [0.94, 0.93, 0.91, 1.0],
        roughness: 0.90,
        metallic: 0.0,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Roof covering material from `RoofIR.material`.
pub fn roof_material(material: &str) -> MaterialDef {
    let lower = material.trim().to_lowercase();
    if lower.contains("metal") || lower.contains("standing") {
        MaterialDef {
            name: material.to_string(),
            base_color: [0.33, 0.37, 0.40, 1.0],
            roughness: 0.38,
            metallic: 0.65,
            style: MaterialStyle::Siding,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else if lower.contains("tile") || lower.contains("clay") {
        MaterialDef {
            name: material.to_string(),
            base_color: [0.68, 0.36, 0.24, 1.0],
            roughness: 0.68,
            metallic: 0.0,
            style: MaterialStyle::Shingle,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else {
        MaterialDef {
            name: material.to_string(),
            base_color: [0.27, 0.28, 0.30, 1.0],
            roughness: 0.88,
            metallic: 0.0,
            style: MaterialStyle::Shingle,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    }
}

/// Poured concrete foundation footer material.
pub fn concrete_material() -> MaterialDef {
    MaterialDef {
        name: "Concrete".to_string(),
        base_color: [0.56, 0.56, 0.54, 1.0],
        roughness: 0.90,
        metallic: 0.0,
        style: MaterialStyle::Stone,
        pattern_scale: 1.2,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Trim, casing, and painted baseboard material.
pub fn trim_material() -> MaterialDef {
    MaterialDef {
        name: "Trim".to_string(),
        base_color: [0.95, 0.94, 0.91, 1.0],
        roughness: 0.45,
        metallic: 0.0,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Door panel wood/painted finish.
pub fn door_leaf_material(style: &str) -> MaterialDef {
    let lower = style.to_lowercase();
    if lower.contains("garage") {
        MaterialDef {
            name: "GarageDoor".to_string(),
            base_color: [0.89, 0.88, 0.85, 1.0],
            roughness: 0.50,
            metallic: 0.15,
            style: MaterialStyle::Solid,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    } else {
        MaterialDef {
            name: "DoorLeaf".to_string(),
            base_color: [0.86, 0.82, 0.76, 1.0],
            roughness: 0.55,
            metallic: 0.0,
            style: MaterialStyle::Solid,
            pattern_scale: 1.0,
            pattern_rotation_deg: 0.0,
            transparent: false,
        }
    }
}

/// Architectural translucent glass pane material.
pub fn glass_material() -> MaterialDef {
    MaterialDef {
        name: "Glass".to_string(),
        base_color: [0.58, 0.78, 0.88, 0.36],
        roughness: 0.08,
        metallic: 0.10,
        style: MaterialStyle::Glass,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: true,
    }
}

/// Warm oak tread material for stairs.
pub fn stair_tread_material() -> MaterialDef {
    MaterialDef {
        name: "StairTread".to_string(),
        base_color: [0.58, 0.40, 0.24, 1.0],
        roughness: 0.52,
        metallic: 0.0,
        style: MaterialStyle::Wood,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Dark architectural bronze/iron railing metal.
pub fn railing_material() -> MaterialDef {
    MaterialDef {
        name: "RailingMetal".to_string(),
        base_color: [0.20, 0.21, 0.23, 1.0],
        roughness: 0.35,
        metallic: 0.75,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Cabinet/fixture body material with optional custom RGB tint.
pub fn fixture_material(symbol_type: &str, rgb_override: Option<[f64; 3]>) -> MaterialDef {
    let lower = symbol_type.to_lowercase();
    let default_col = if lower.contains("fridge")
        || lower.contains("range")
        || lower.contains("oven")
        || lower.contains("dishwasher")
        || lower.contains("microwave")
    {
        [0.72, 0.74, 0.76]
    } else if lower.contains("toilet")
        || lower.contains("tub")
        || lower.contains("sink")
        || lower.contains("shower")
    {
        [0.95, 0.96, 0.97]
    } else {
        [0.82, 0.80, 0.76]
    };
    let metallic = if lower.contains("fridge") || lower.contains("range") {
        0.55
    } else {
        0.0
    };
    MaterialDef {
        name: format!("Fixture:{symbol_type}"),
        base_color: color3(rgb_override, default_col),
        roughness: if metallic > 0.1 { 0.35 } else { 0.55 },
        metallic,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Countertop slab material.
pub fn countertop_material(name: &str, rgb_override: Option<[f64; 3]>) -> MaterialDef {
    let lower = name.to_lowercase();
    let default_col = if lower.contains("granite") {
        [0.44, 0.43, 0.42]
    } else if lower.contains("butcher") || lower.contains("wood") {
        [0.64, 0.46, 0.28]
    } else {
        [0.92, 0.91, 0.89]
    };
    MaterialDef {
        name: format!("Countertop:{name}"),
        base_color: color3(rgb_override, default_col),
        roughness: 0.30,
        metallic: 0.0,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Brushed nickel/bronze cabinet pulls, levers, and hardware handles.
pub fn hardware_material() -> MaterialDef {
    MaterialDef {
        name: "HardwareNickel".to_string(),
        base_color: [0.68, 0.69, 0.71, 1.0],
        roughness: 0.28,
        metallic: 0.85,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Bright chrome faucet, drain, and shower trim material.
pub fn chrome_material() -> MaterialDef {
    MaterialDef {
        name: "Chrome".to_string(),
        base_color: [0.85, 0.87, 0.90, 1.0],
        roughness: 0.14,
        metallic: 0.95,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Glossy vitreous porcelain for toilets, bathtubs, and vanity sinks.
pub fn porcelain_material(rgb_override: Option<[f64; 3]>) -> MaterialDef {
    MaterialDef {
        name: "Porcelain".to_string(),
        base_color: color3(rgb_override, [0.96, 0.96, 0.95]),
        roughness: 0.20,
        metallic: 0.0,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Brushed stainless steel for sinks, ranges, fridges, and range hoods.
pub fn stainless_material(rgb_override: Option<[f64; 3]>) -> MaterialDef {
    MaterialDef {
        name: "StainlessSteel".to_string(),
        base_color: color3(rgb_override, [0.74, 0.76, 0.78]),
        roughness: 0.30,
        metallic: 0.80,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Dark tinted glass/ceramic surface for oven doors, cooktops, TVs, and microwaves.
pub fn appliance_glass_material() -> MaterialDef {
    MaterialDef {
        name: "ApplianceDarkGlass".to_string(),
        base_color: [0.10, 0.11, 0.13, 1.0],
        roughness: 0.12,
        metallic: 0.20,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Soft woven upholstery fabric for sofas, armchairs, and dining cushions.
pub fn upholstery_material(rgb_override: Option<[f64; 3]>) -> MaterialDef {
    MaterialDef {
        name: "Upholstery".to_string(),
        base_color: color3(rgb_override, [0.55, 0.60, 0.64]),
        roughness: 0.90,
        metallic: 0.0,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Warm crisp linen material for mattresses, duvets, and pillows.
pub fn fabric_linen_material() -> MaterialDef {
    MaterialDef {
        name: "BedLinen".to_string(),
        base_color: [0.93, 0.91, 0.88, 1.0],
        roughness: 0.92,
        metallic: 0.0,
        style: MaterialStyle::Solid,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}

/// Natural warm furniture wood for tables, desks, nightstands, dressers, and shelves.
pub fn wood_furniture_material(rgb_override: Option<[f64; 3]>) -> MaterialDef {
    MaterialDef {
        name: "WoodFurniture".to_string(),
        base_color: color3(rgb_override, [0.56, 0.39, 0.25]),
        roughness: 0.56,
        metallic: 0.0,
        style: MaterialStyle::Wood,
        pattern_scale: 1.0,
        pattern_rotation_deg: 0.0,
        transparent: false,
    }
}
