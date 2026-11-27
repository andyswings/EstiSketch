use estisketch_3d_core::SceneSummary;
pub use glow;

/// Lightweight Phase 0 status metadata for the future OpenGL 3.3 Core renderer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RendererStatus {
    pub backend: &'static str,
    pub viewport_width: u32,
    pub viewport_height: u32,
    pub entity_count: usize,
}

#[derive(Debug, Clone)]
pub struct GlRenderer {
    viewport_width: u32,
    viewport_height: u32,
    last_entity_count: usize,
}

impl Default for GlRenderer {
    fn default() -> Self {
        Self::new(1, 1)
    }
}

impl GlRenderer {
    pub fn new(viewport_width: u32, viewport_height: u32) -> Self {
        Self {
            viewport_width: viewport_width.max(1),
            viewport_height: viewport_height.max(1),
            last_entity_count: 0,
        }
    }

    pub fn resize(&mut self, width: u32, height: u32) {
        self.viewport_width = width.max(1);
        self.viewport_height = height.max(1);
    }

    pub fn sync_summary(&mut self, summary: &SceneSummary) {
        self.last_entity_count = summary.total_entities;
    }

    pub fn status(&self) -> RendererStatus {
        RendererStatus {
            backend: concat!("glow-", env!("CARGO_PKG_VERSION")),
            viewport_width: self.viewport_width,
            viewport_height: self.viewport_height,
            entity_count: self.last_entity_count,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renderer_resize_clamps_non_zero() {
        let mut r = GlRenderer::new(0, 0);
        assert_eq!(r.status().viewport_width, 1);
        r.resize(1280, 720);
        assert_eq!(r.status().viewport_width, 1280);
        assert_eq!(r.status().viewport_height, 720);
    }
}
