//! GLSL 330 Core shader sources for directional shadows, sky/ground, and stylized PBR surfaces.

pub const SHADOW_VERT: &str = r#"#version 330 core
layout (location = 0) in vec3 a_pos;
uniform mat4 u_light_vp;
uniform mat4 u_model;

void main() {
    gl_Position = u_light_vp * u_model * vec4(a_pos, 1.0);
}
"#;

pub const SHADOW_FRAG: &str = r#"#version 330 core
void main() {
}
"#;

pub const SKY_VERT: &str = r#"#version 330 core
out vec2 v_ndc;

void main() {
    const vec2 POS[3] = vec2[3](
        vec2(-1.0, -1.0),
        vec2( 3.0, -1.0),
        vec2(-1.0,  3.0)
    );
    v_ndc = POS[gl_VertexID];
    gl_Position = vec4(v_ndc, 0.9999, 1.0);
}
"#;

pub const SKY_FRAG: &str = r#"#version 330 core
in vec2 v_ndc;
layout (location = 0) out vec4 frag_color;
layout (location = 1) out vec4 frag_normal;

uniform mat4 u_inv_vp;
uniform vec3 u_cam_pos;
uniform vec3 u_sun_dir;
uniform int u_render_style;

void main() {
    vec4 near_w = u_inv_vp * vec4(v_ndc, -1.0, 1.0);
    vec4 far_w  = u_inv_vp * vec4(v_ndc,  1.0, 1.0);
    vec3 ray = normalize(far_w.xyz / far_w.w - near_w.xyz / near_w.w);
    frag_normal = vec4(0.5, 0.5, 0.5, 0.0);

    if (ray.z >= -0.002) {
        float h = clamp(ray.z, 0.0, 1.0);
        vec3 zenith = (u_render_style == 2) ? vec3(0.11, 0.22, 0.38) : vec3(0.46, 0.67, 0.89);
        vec3 horizon = (u_render_style == 2) ? vec3(0.16, 0.31, 0.50) : vec3(0.89, 0.91, 0.93);
        vec3 col = mix(horizon, zenith, pow(h, 0.55));
        float sun_dot = max(dot(ray, normalize(u_sun_dir)), 0.0);
        col += vec3(1.0, 0.93, 0.78) * pow(sun_dot, 64.0) * 0.45;
        frag_color = vec4(col, 1.0);
    } else {
        float t = -u_cam_pos.z / min(ray.z, -0.002);
        vec2 hit = u_cam_pos.xy + ray.xy * min(t, 250.0);
        vec3 base_g = (u_render_style == 2)
            ? vec3(0.14, 0.26, 0.43)
            : (u_render_style == 1 ? vec3(0.88, 0.87, 0.84) : vec3(0.76, 0.78, 0.72));
        vec2 grid = abs(fract(hit - 0.5) - 0.5) / max(fwidth(hit), vec2(0.001));
        float line = 1.0 - min(min(grid.x, grid.y), 1.0);
        float fade = exp(-length(hit - u_cam_pos.xy) * 0.025);
        vec3 col = mix(base_g, base_g * 0.84, line * 0.35 * fade);
        vec3 horizon = (u_render_style == 2) ? vec3(0.16, 0.31, 0.50) : vec3(0.89, 0.91, 0.93);
        col = mix(horizon, col, fade);
        frag_color = vec4(col, 1.0);
    }
}
"#;

pub const SCENE_VERT: &str = r#"#version 330 core
layout (location = 0) in vec3 a_pos;
layout (location = 1) in vec3 a_normal;
layout (location = 2) in vec2 a_uv;

uniform mat4 u_vp;
uniform mat4 u_light_vp;
uniform mat4 u_model;

out vec3 v_world_pos;
out vec3 v_world_normal;
out vec2 v_uv;
out vec4 v_light_pos;

void main() {
    vec4 world_pos = u_model * vec4(a_pos, 1.0);
    v_world_pos = world_pos.xyz;
    v_world_normal = normalize(mat3(u_model) * a_normal);
    v_uv = a_uv;
    v_light_pos = u_light_vp * world_pos;
    gl_Position = u_vp * world_pos;
}
"#;

pub const SCENE_FRAG: &str = r#"#version 330 core
in vec3 v_world_pos;
in vec3 v_world_normal;
in vec2 v_uv;
in vec4 v_light_pos;

layout (location = 0) out vec4 frag_color;
layout (location = 1) out vec4 frag_normal;

uniform sampler2D u_shadow_map;
uniform vec3 u_cam_pos;
uniform vec3 u_sun_dir;
uniform vec4 u_base_color;
uniform float u_roughness;
uniform float u_metallic;
uniform int u_mat_style;
uniform float u_pattern_scale;
uniform float u_pattern_rot_deg;
uniform int u_render_style;
uniform float u_alpha_override;
uniform int u_highlight_mode;

float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

vec2 rotate2d(vec2 p, float deg) {
    float r = radians(deg);
    float c = cos(r);
    float s = sin(r);
    return vec2(c * p.x - s * p.y, s * p.x + c * p.y);
}

vec3 procedural_albedo(vec3 base, vec2 uv, vec3 n) {
    if (u_render_style == 1) {
        return vec3(0.93, 0.91, 0.87);
    }
    if (u_render_style == 2) {
        return vec3(0.95, 0.97, 0.99);
    }
    vec2 p = rotate2d(uv, u_pattern_rot_deg) / max(u_pattern_scale, 0.1);
    if (u_mat_style == 1) {
        // Wood planks & warm grain
        float plank_w = 0.15;
        float row = floor(p.y / plank_w);
        float px = fract((p.x + row * 0.37) * 0.85);
        float py = fract(p.y / plank_w);
        float seam = smoothstep(0.0, 0.03, py) * smoothstep(1.0, 0.97, py) * smoothstep(0.0, 0.015, px);
        float tint = 0.92 + 0.14 * hash21(vec2(floor((p.x + row * 0.37) * 0.85), row));
        float grain = 0.96 + 0.04 * sin(p.x * 28.0 + sin(p.y * 42.0) * 1.5);
        return base * tint * grain * mix(0.68, 1.0, seam);
    } else if (u_mat_style == 2) {
        // Architectural tile grid with clean grout lines
        vec2 g = fract(p / 0.35);
        float gx = smoothstep(0.0, 0.04, g.x) * smoothstep(1.0, 0.96, g.x);
        float gy = smoothstep(0.0, 0.04, g.y) * smoothstep(1.0, 0.96, g.y);
        float tile_var = 0.95 + 0.08 * hash21(floor(p / 0.35));
        return mix(vec3(0.76, 0.75, 0.72), base * tile_var, gx * gy);
    } else if (u_mat_style == 3) {
        // Running-bond brick
        float bh = 0.075;
        float bw = 0.22;
        float row = floor(p.y / bh);
        float xoff = mod(row, 2.0) * (bw * 0.5);
        vec2 b = vec2(fract((p.x + xoff) / bw), fract(p.y / bh));
        float mortar = smoothstep(0.0, 0.08, b.x) * smoothstep(0.0, 0.12, b.y);
        float shade = 0.86 + 0.24 * hash21(vec2(floor((p.x + xoff) / bw), row));
        return mix(vec3(0.78, 0.76, 0.72), base * shade, mortar);
    } else if (u_mat_style == 4) {
        // Lap siding horizontal courses
        float course = fract(v_world_pos.z / 0.16);
        float shadow = mix(0.76, 1.04, smoothstep(0.0, 0.15, course));
        return base * shadow;
    } else if (u_mat_style == 5 || u_mat_style == 6) {
        // Stone / Roof shingles subtle variation
        float course = fract((p.y + v_world_pos.z) * 3.5);
        float nval = 0.91 + 0.14 * hash21(floor(p * 4.5 + abs(n.xy) * 2.0));
        return base * nval * mix(0.84, 1.0, smoothstep(0.0, 0.12, course));
    }
    return base * (0.985 + 0.025 * hash21(floor(p * 12.0)));
}

float calc_shadow(vec4 light_pos, vec3 n, vec3 l) {
    vec3 proj = light_pos.xyz / max(light_pos.w, 0.0001);
    proj = proj * 0.5 + 0.5;
    if (proj.z > 1.0 || proj.x < 0.0 || proj.x > 1.0 || proj.y < 0.0 || proj.y > 1.0) {
        return 0.0;
    }
    float bias = max(0.0018 * (1.0 - max(dot(n, l), 0.0)), 0.0005);
    vec2 texel = 1.0 / vec2(textureSize(u_shadow_map, 0));
    float shadow = 0.0;
    for (int x = -1; x <= 1; ++x) {
        for (int y = -1; y <= 1; ++y) {
            float d = texture(u_shadow_map, proj.xy + vec2(x, y) * texel).r;
            shadow += (proj.z - bias > d) ? 1.0 : 0.0;
        }
    }
    return shadow / 9.0;
}

void main() {
    vec3 n = normalize(v_world_normal);
    if (!gl_FrontFacing) {
        n = -n;
    }
    vec3 v = normalize(u_cam_pos - v_world_pos);
    vec3 l = normalize(u_sun_dir);

    float alpha = (u_alpha_override < 0.99) ? u_alpha_override : u_base_color.a;
    float rim = pow(1.0 - max(dot(n, v), 0.0), 2.2);
    if (u_mat_style == 7 || alpha < 0.99) {
        float fresnel = pow(1.0 - max(dot(n, v), 0.0), 3.0);
        vec3 glass_col = mix(u_base_color.rgb, vec3(0.84, 0.92, 0.98), fresnel * 0.65);
        float spec = pow(max(dot(n, normalize(l + v)), 0.0), 48.0) * 0.55;
        vec3 tinted = glass_col + vec3(spec);
        if (u_highlight_mode == 2) {
            tinted = mix(tinted, vec3(0.98, 0.56, 0.14), 0.25 + 0.45 * rim);
        } else if (u_highlight_mode == 1) {
            tinted = mix(tinted, vec3(0.24, 0.62, 0.98), 0.18 + 0.32 * rim);
        }
        frag_color = vec4(tinted, clamp(alpha + fresnel * 0.30, 0.15, 0.85));
        frag_normal = vec4(0.5, 0.5, 0.5, 0.0);
        return;
    }

    vec3 albedo = procedural_albedo(u_base_color.rgb, v_uv, n);

    // Subtle vertical corner ambient darkening + crisp screen-space crease ink lines
    float ndotl = max(dot(n, l), 0.0);
    float shadow = (u_render_style == 2) ? 0.0 : calc_shadow(v_light_pos, n, l);
    vec3 hemi = mix(vec3(0.32, 0.34, 0.38), vec3(0.56, 0.62, 0.70), n.z * 0.5 + 0.5);
    vec3 sun_col = vec3(1.00, 0.95, 0.86) * 0.82;
    vec3 h_vec = normalize(l + v);
    float shininess = mix(8.0, 96.0, 1.0 - u_roughness);
    float spec = pow(max(dot(n, h_vec), 0.0), shininess) * mix(0.04, 0.45, 1.0 - u_roughness + u_metallic);

    vec3 lit = albedo * (hemi * 0.72 + sun_col * ndotl * (1.0 - shadow * 0.68)) + vec3(spec) * (1.0 - shadow);

    // Edge/crease accent via derivative discontinuity of normal
    vec3 dnx = dFdx(n);
    vec3 dny = dFdy(n);
    float crease = clamp(length(dnx) + length(dny), 0.0, 1.0);
    float edge_strength = (u_render_style == 2) ? 0.80 : (u_render_style == 1 ? 0.42 : 0.22);
    vec3 ink = (u_render_style == 2) ? vec3(0.10, 0.22, 0.42) : vec3(0.15, 0.14, 0.13);
    lit = mix(lit, ink, smoothstep(0.18, 0.75, crease) * edge_strength);

    if (u_highlight_mode == 2) {
        lit = mix(lit, vec3(0.98, 0.56, 0.14), 0.18 + 0.52 * rim);
    } else if (u_highlight_mode == 1) {
        lit = mix(lit, vec3(0.24, 0.62, 0.98), 0.12 + 0.35 * rim);
    }

    frag_color = vec4(lit, 1.0);
    frag_normal = vec4(normalize(n) * 0.5 + 0.5, 1.0);
}
"#;

pub const POST_VERT: &str = r#"#version 330 core
out vec2 v_uv;

void main() {
    const vec2 POS[3] = vec2[3](
        vec2(-1.0, -1.0),
        vec2( 3.0, -1.0),
        vec2(-1.0,  3.0)
    );
    vec2 p = POS[gl_VertexID];
    v_uv = p * 0.5 + 0.5;
    gl_Position = vec4(p, 0.0, 1.0);
}
"#;

pub const SSAO_FRAG: &str = r#"#version 330 core
in vec2 v_uv;
out float frag_ao;

uniform sampler2D u_depth_tex;
uniform sampler2D u_normal_tex;
uniform mat4 u_vp;
uniform mat4 u_inv_vp;
uniform float u_radius_m;
uniform float u_bias_m;

const vec3 KERNEL[16] = vec3[16](
    vec3( 0.04,  0.03, 0.12),
    vec3(-0.08,  0.06, 0.18),
    vec3( 0.11, -0.09, 0.22),
    vec3(-0.14, -0.10, 0.26),
    vec3( 0.21,  0.04, 0.20),
    vec3(-0.05,  0.24, 0.24),
    vec3( 0.06, -0.26, 0.28),
    vec3(-0.27,  0.12, 0.31),
    vec3( 0.32, -0.18, 0.35),
    vec3(-0.18, -0.34, 0.38),
    vec3( 0.38,  0.25, 0.42),
    vec3(-0.36,  0.32, 0.45),
    vec3( 0.12,  0.48, 0.48),
    vec3(-0.46, -0.22, 0.52),
    vec3( 0.52, -0.35, 0.55),
    vec3(-0.28,  0.56, 0.62)
);

vec3 world_from_uv_depth(vec2 uv, float depth) {
    vec4 clip = vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 world = u_inv_vp * clip;
    return world.xyz / max(abs(world.w), 1e-5);
}

void main() {
    vec4 n_sample = texture(u_normal_tex, v_uv);
    if (n_sample.a < 0.5) {
        frag_ao = 1.0;
        return;
    }
    float center_depth = texture(u_depth_tex, v_uv).r;
    if (center_depth >= 0.9999) {
        frag_ao = 1.0;
        return;
    }

    vec3 pos = world_from_uv_depth(v_uv, center_depth);
    vec3 n = normalize(n_sample.xyz * 2.0 - 1.0);
    vec3 helper = (abs(n.z) < 0.9) ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 t0 = normalize(cross(helper, n));
    vec3 b0 = cross(n, t0);

    float angle = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) * 6.2831853;
    float ca = cos(angle);
    float sa = sin(angle);
    vec3 tangent = t0 * ca + b0 * sa;
    vec3 bitangent = -t0 * sa + b0 * ca;
    mat3 tbn = mat3(tangent, bitangent, n);

    float occlusion = 0.0;
    for (int i = 0; i < 16; ++i) {
        vec3 sample_pos = pos + (tbn * KERNEL[i]) * u_radius_m;
        vec4 offset_clip = u_vp * vec4(sample_pos, 1.0);
        vec3 offset_ndc = offset_clip.xyz / max(abs(offset_clip.w), 1e-5);
        vec2 sample_uv = offset_ndc.xy * 0.5 + 0.5;
        if (sample_uv.x < 0.0 || sample_uv.x > 1.0 || sample_uv.y < 0.0 || sample_uv.y > 1.0) {
            continue;
        }
        float sample_depth = texture(u_depth_tex, sample_uv).r;
        if (sample_depth >= 0.9999) {
            continue;
        }
        vec3 occ_pos = world_from_uv_depth(sample_uv, sample_depth);
        vec3 diff = occ_pos - pos;
        float dist_to_occ = length(diff);
        float normal_proj = dot(diff, n);
        float range_check = 1.0 - smoothstep(u_radius_m * 0.35, u_radius_m * 1.15, dist_to_occ);
        if (normal_proj > u_bias_m && dist_to_occ < u_radius_m) {
            occlusion += range_check;
        }
    }

    frag_ao = clamp(1.0 - (occlusion / 16.0) * 1.35, 0.18, 1.0);
}
"#;

pub const SSAO_BLUR_FRAG: &str = r#"#version 330 core
in vec2 v_uv;
out float frag_ao;

uniform sampler2D u_ssao_tex;
uniform sampler2D u_depth_tex;
uniform vec2 u_texel_size;

void main() {
    float center_ao = texture(u_ssao_tex, v_uv).r;
    float center_d = texture(u_depth_tex, v_uv).r;
    float sum = 0.0;
    float w_sum = 0.0;
    for (int x = -1; x <= 1; ++x) {
        for (int y = -1; y <= 1; ++y) {
            vec2 suv = clamp(v_uv + vec2(float(x), float(y)) * u_texel_size, vec2(0.0), vec2(1.0));
            float ao = texture(u_ssao_tex, suv).r;
            float d = texture(u_depth_tex, suv).r;
            float w = exp(-abs(d - center_d) * 450.0);
            sum += ao * w;
            w_sum += w;
        }
    }
    frag_ao = (w_sum > 1e-4) ? (sum / w_sum) : center_ao;
}
"#;

pub const COMPOSITE_FRAG: &str = r#"#version 330 core
in vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_color_tex;
uniform sampler2D u_ssao_tex;
uniform sampler2D u_normal_tex;
uniform sampler2D u_depth_tex;
uniform vec2 u_texel_size;
uniform int u_render_style;
uniform int u_ssao_enabled;

void main() {
    vec4 base = texture(u_color_tex, v_uv);
    vec4 n_center = texture(u_normal_tex, v_uv);
    vec3 col = base.rgb;

    if (n_center.a > 0.5) {
        if (u_ssao_enabled != 0 && u_render_style != 3) {
            float ao = texture(u_ssao_tex, v_uv).r;
            float strength = (u_render_style == 1) ? 1.0 : (u_render_style == 2 ? 0.65 : 0.85);
            col *= mix(1.0, ao, strength);
        }

        // Screen-space normal + depth crease silhouette lines
        float d_c = texture(u_depth_tex, v_uv).r;
        vec3 nc = n_center.xyz * 2.0 - 1.0;
        float norm_edge = 0.0;
        float depth_edge = 0.0;
        const vec2 OFF[4] = vec2[4](
            vec2( 1.0,  0.0),
            vec2(-1.0,  0.0),
            vec2( 0.0,  1.0),
            vec2( 0.0, -1.0)
        );
        for (int i = 0; i < 4; ++i) {
            vec2 suv = clamp(v_uv + OFF[i] * u_texel_size, vec2(0.0), vec2(1.0));
            vec4 n_s = texture(u_normal_tex, suv);
            float d_s = texture(u_depth_tex, suv).r;
            if (n_s.a > 0.5) {
                vec3 ns = n_s.xyz * 2.0 - 1.0;
                norm_edge = max(norm_edge, 1.0 - max(dot(nc, ns), 0.0));
            } else {
                norm_edge = max(norm_edge, 0.8);
            }
            depth_edge = max(depth_edge, abs(d_s - d_c) / max(1.0 - d_c, 0.002));
        }
        float edge = clamp(
            smoothstep(0.22, 0.68, norm_edge) * 0.85 + smoothstep(0.035, 0.14, depth_edge),
            0.0,
            1.0
        );
        float ink_strength = (u_render_style == 2) ? 0.78 : (u_render_style == 1 ? 0.38 : 0.18);
        vec3 ink_col = (u_render_style == 2) ? vec3(0.08, 0.18, 0.36) : vec3(0.14, 0.13, 0.12);
        col = mix(col, ink_col, edge * ink_strength);
    }

    // Gentle highlight compression so bright sunlight plaster stays nuanced
    col = col / (vec3(1.0) + max(col - vec3(0.92), vec3(0.0)) * 0.35);
    frag_color = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"#;
