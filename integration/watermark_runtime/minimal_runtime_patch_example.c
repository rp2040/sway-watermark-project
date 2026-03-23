/*
 * Minimal runtime watermark patch example (stage-2 validation only).
 *
 * This file is intentionally standalone and NOT wired into third_party code yet.
 * Purpose: demonstrate what to insert near sway/desktop/render.c::output_render
 * before wlr_renderer_end(renderer).
 */

#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_box.h>

void wm_runtime_apply_checker_overlay(struct wlr_renderer *renderer,
        struct wlr_output *output, float alpha, int cell) {
    if (!renderer || !output || alpha <= 0.0f || cell <= 1) {
        return;
    }

    int width = output->width;
    int height = output->height;
    struct wlr_box box = {0};

    for (int y = 0; y < height; y += cell) {
        for (int x = 0; x < width; x += cell) {
            int on = ((x / cell) + (y / cell)) & 1;
            if (!on) {
                continue;
            }
            box.x = x;
            box.y = y;
            box.width = cell;
            box.height = cell;

            float color[4] = {alpha, alpha, alpha, alpha};
            wlr_render_rect(renderer, &box, color, output->transform_matrix);
        }
    }
}
