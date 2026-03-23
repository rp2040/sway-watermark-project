#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/render/gles2.h>
#include <wlr/types/wlr_box.h>
#include "log.h"
#include "sway/output.h"

struct wm_template_cache {
	int width;
	int height;
	int cell;
	float *tw;   // watermark template cache (stage-2 embed skeleton)
	float *jnd;  // simplified intensity map cache
	bool valid;
};

struct wm_runtime_state {
	bool initialized;
	bool enabled;
	bool debug_log;
	bool use_embed_stub;
	bool use_shader_poc;
	bool use_shader_tw;
	float alpha;
	int checker_cell;
	int jnd_period_frames;
	int frame_idx;
	bool force_full_damage;
	uint32_t device_id;
	int64_t t0_unix;
	uint16_t current_slot;
	uint8_t *tw_template_u8;
	int tw_template_width;
	int tw_template_height;
	struct wm_template_cache cache;
};

static struct wm_runtime_state g_wm_state = {
	.initialized = false,
	.enabled = true,
	.debug_log = false,
	.use_embed_stub = false,
	.use_shader_poc = false,
	.use_shader_tw = false,
	.alpha = 0.03f,
	.checker_cell = 24,
	.jnd_period_frames = 300,
	.frame_idx = 0,
	.force_full_damage = false,
	.device_id = 0x1A2B3C4D,
	.t0_unix = 1767225600, // 2026-01-01T00:00:00Z
	.current_slot = 0,
	.tw_template_u8 = NULL,
	.tw_template_width = 0,
	.tw_template_height = 0,
};

static int clampi(int v, int lo, int hi) {
	if (v < lo) {
		return lo;
	}
	if (v > hi) {
		return hi;
	}
	return v;
}

static float clampf(float v, float lo, float hi) {
	if (v < lo) {
		return lo;
	}
	if (v > hi) {
		return hi;
	}
	return v;
}

static bool env_true(const char *v) {
	return v && (!strcmp(v, "1") || !strcmp(v, "true") || !strcmp(v, "yes"));
}

static uint16_t wm_crc16_ccitt(const uint8_t *data, size_t len) {
	uint16_t crc = 0xFFFF;
	for (size_t i = 0; i < len; ++i) {
		crc ^= (uint16_t)data[i] << 8;
		for (int j = 0; j < 8; ++j) {
			if (crc & 0x8000) {
				crc = (uint16_t)((crc << 1) ^ 0x1021);
			} else {
				crc = (uint16_t)(crc << 1);
			}
		}
	}
	return crc;
}

static uint16_t wm_time_slot_now(const struct wm_runtime_state *st) {
	time_t now = time(NULL);
	if ((int64_t)now <= st->t0_unix) {
		return 0;
	}
	return (uint16_t)(((int64_t)now - st->t0_unix) / 300);
}

static void wm_payload_bits(const struct wm_runtime_state *st,
		uint16_t time_slot, char bits[65]) {
	uint8_t body[6];
	body[0] = (uint8_t)(st->device_id >> 24);
	body[1] = (uint8_t)(st->device_id >> 16);
	body[2] = (uint8_t)(st->device_id >> 8);
	body[3] = (uint8_t)(st->device_id);
	body[4] = (uint8_t)(time_slot >> 8);
	body[5] = (uint8_t)(time_slot);
	uint16_t crc = wm_crc16_ccitt(body, sizeof(body));

	uint64_t payload = ((uint64_t)st->device_id << 32) |
		((uint64_t)time_slot << 16) | crc;
	for (int i = 0; i < 64; ++i) {
		int b = (payload >> (63 - i)) & 1ULL;
		bits[i] = b ? '1' : '0';
	}
	bits[64] = '\0';
}

static float wm_marker_value(int size, int marker_id, int x, int y) {
	int hs = size / 2;
	int dx = x - hs;
	int dy = y - hs;
	float r = sqrtf((float)(dx * dx + dy * dy));
	float ring = ((int)r % 2 == 0) ? 1.0f : -1.0f;
	float chk = (((x + y) & 1) == 0) ? 1.0f : -1.0f;
	float val = 0.55f * ring + 0.45f * chk;
	if (marker_id == 0 && x < hs && y < hs) {
		val += 0.9f;
	} else if (marker_id == 1 && x >= hs && y < hs) {
		val += 0.9f;
	} else if (marker_id == 2 && x >= hs && y >= hs) {
		val += 0.9f;
	} else if (marker_id == 3 && x < hs && y >= hs) {
		val += 0.9f;
	}
	return val;
}

static void wm_build_real_tw_template(struct wm_runtime_state *st,
		int width, int height, uint16_t time_slot) {
	if (width <= 0 || height <= 0) {
		return;
	}
	size_t n = (size_t)width * (size_t)height;
	float *tm = calloc(n, sizeof(float));
	float *ta = calloc(n, sizeof(float));
	float *tb = calloc(n, sizeof(float));
	if (!tm || !ta || !tb) {
		free(tm); free(ta); free(tb);
		return;
	}

	char bits[65];
	wm_payload_bits(st, time_slot, bits);

	int m = width < height ? width : height;
	int l1 = (int)(0.47f * (float)m);
	if (l1 < 64) {
		l1 = 64;
	}
	int l2 = ((int)(0.06f * (float)m)) | 1;
	if (l2 < 11) {
		l2 = 11;
	}
	int cx = width / 2, cy = height / 2;
	int half = l1 / 2;
	int x0 = cx - half, y0 = cy - half;

	int inner = (int)(l1 * 0.72f);
	int inner_x0 = x0 + (l1 - inner) / 2;
	int inner_y0 = y0 + (l1 - inner) / 2;
	int cell = inner / 8;
	if (cell < 6) {
		cell = 6;
	}

	int idx = 0;
	for (int gy = 0; gy < 8; ++gy) {
		for (int gx = 0; gx < 8; ++gx) {
			float sign = (bits[idx++] == '1') ? 1.0f : -1.0f;
			int bx = inner_x0 + gx * cell;
			int by = inner_y0 + gy * cell;
			for (int yy = 0; yy < cell; ++yy) {
				for (int xx = 0; xx < cell; ++xx) {
					int x = bx + xx, y = by + yy;
					if (x < 0 || x >= width || y < 0 || y >= height) {
						continue;
					}
					float carrier = 0.6f * cosf(2.0f * 3.1415926535f * (float)xx / (float)cell) +
						0.4f * cosf(2.0f * 3.1415926535f * (float)yy / (float)cell);
					tm[(size_t)y * (size_t)width + (size_t)x] += sign * carrier;
				}
			}
		}
	}

	float max_abs = 1e-6f;
	for (size_t i = 0; i < n; ++i) {
		float a = fabsf(tm[i]);
		if (a > max_abs) {
			max_abs = a;
		}
	}
	for (size_t i = 0; i < n; ++i) {
		tm[i] /= max_abs;
	}

	int s = l2;
	int offs = s / 2 + 3;
	int corners[4][2] = {
		{x0 + offs, y0 + offs},
		{x0 + l1 - offs - 1, y0 + offs},
		{x0 + l1 - offs - 1, y0 + l1 - offs - 1},
		{x0 + offs, y0 + l1 - offs - 1},
	};

	for (int i = 0; i < 4; ++i) {
		float marker_max = 1e-6f;
		float *marker = calloc((size_t)s * (size_t)s, sizeof(float));
		if (!marker) {
			continue;
		}
		for (int yy = 0; yy < s; ++yy) {
			for (int xx = 0; xx < s; ++xx) {
				float v = wm_marker_value(s, i, xx, yy);
				marker[yy * s + xx] = v;
				if (fabsf(v) > marker_max) {
					marker_max = fabsf(v);
				}
			}
		}
		for (int yy = 0; yy < s; ++yy) {
			for (int xx = 0; xx < s; ++xx) {
				float v = marker[yy * s + xx] / marker_max;
				int x = corners[i][0] + xx - s / 2;
				int y = corners[i][1] + yy - s / 2;
				if (x < 0 || x >= width || y < 0 || y >= height) {
					continue;
				}
				size_t p = (size_t)y * (size_t)width + (size_t)x;
				if ((i & 1) == 0) {
					ta[p] = v;
				} else {
					tb[p] = v;
				}
			}
		}
		free(marker);
	}

	uint8_t *out = realloc(st->tw_template_u8, n);
	if (!out) {
		free(tm); free(ta); free(tb);
		return;
	}
	st->tw_template_u8 = out;
	for (size_t i = 0; i < n; ++i) {
		float tw = 0.72f * tm[i] + 0.16f * ta[i] + 0.12f * tb[i];
		float normalized = tw * 0.5f + 0.5f;
		if (normalized < 0.0f) normalized = 0.0f;
		if (normalized > 1.0f) normalized = 1.0f;
		st->tw_template_u8[i] = (uint8_t)(normalized * 255.0f);
	}
	st->tw_template_width = width;
	st->tw_template_height = height;
	st->current_slot = time_slot;

	free(tm); free(ta); free(tb);
}

static void wm_runtime_init_once(void) {
	if (g_wm_state.initialized) {
		return;
	}
	g_wm_state.initialized = true;

	const char *enable = getenv("SWAY_WM_ENABLE");
	if (enable) {
		g_wm_state.enabled = env_true(enable);
	}

	g_wm_state.debug_log = env_true(getenv("SWAY_WM_DEBUG"));

	const char *mode = getenv("SWAY_WM_MODE");
	if (mode && !strcmp(mode, "embed_stub")) {
		g_wm_state.use_embed_stub = true;
	} else if (mode && !strcmp(mode, "shader_poc")) {
		g_wm_state.use_shader_poc = true;
	} else if (mode && !strcmp(mode, "shader_tw")) {
		g_wm_state.use_shader_tw = true;
	}

	const char *alpha = getenv("SWAY_WM_ALPHA");
	if (alpha) {
		g_wm_state.alpha = clampf(strtof(alpha, NULL), 0.0f, 0.30f);
	}
	const char *cell = getenv("SWAY_WM_CELL");
	if (cell) {
		g_wm_state.checker_cell = clampi(atoi(cell), 8, 96);
	}

	const char *period = getenv("SWAY_WM_JND_PERIOD");
	if (period) {
		g_wm_state.jnd_period_frames = clampi(atoi(period), 1, 3600);
	}

	const char *force = getenv("SWAY_WM_FORCE_FULL_DAMAGE");
	if (force) {
		g_wm_state.force_full_damage = env_true(force);
	}

	if (g_wm_state.debug_log) {
		sway_log(SWAY_INFO,
			"wm_runtime init: enabled=%d mode=%s alpha=%.3f cell=%d jnd_period=%d force_full=%d",
			g_wm_state.enabled,
			g_wm_state.use_shader_tw ? "shader_tw" :
				(g_wm_state.use_shader_poc ? "shader_poc" :
				(g_wm_state.use_embed_stub ? "embed_stub" : "checker")),
			g_wm_state.alpha,
			g_wm_state.checker_cell,
			g_wm_state.jnd_period_frames,
			g_wm_state.force_full_damage);
	}
}

static void wm_cache_free(struct wm_template_cache *c) {
	free(c->tw);
	free(c->jnd);
	memset(c, 0, sizeof(*c));
}

static void wm_cache_rebuild(struct wm_template_cache *c, int width, int height, int cell) {
	if (c->valid && c->width == width && c->height == height && c->cell == cell) {
		return;
	}

	wm_cache_free(c);
	c->width = width;
	c->height = height;
	c->cell = cell;

	size_t n = (size_t)width * (size_t)height;
	c->tw = calloc(n, sizeof(float));
	c->jnd = calloc(n, sizeof(float));
	if (!c->tw || !c->jnd) {
		wm_cache_free(c);
		return;
	}

	// Template skeleton: deterministic low-frequency pattern (placeholder for Tw cache).
	for (int y = 0; y < height; ++y) {
		for (int x = 0; x < width; ++x) {
			size_t idx = (size_t)y * (size_t)width + (size_t)x;
			float phase_x = 2.0f * 3.1415926535f * (float)x / (float)(cell * 2);
			float phase_y = 2.0f * 3.1415926535f * (float)y / (float)(cell * 2);
			c->tw[idx] = 0.6f * cosf(phase_x) + 0.4f * cosf(phase_y);
			c->jnd[idx] = 1.0f; // initialized; refreshed in periodic update
		}
	}

	c->valid = true;
}

static void wm_refresh_simple_jnd(struct wm_template_cache *c, int frame_idx) {
	if (!c->valid || !c->jnd) {
		return;
	}

	// simplified jnd map placeholder (time-varying weak modulation)
	float t = (float)(frame_idx % 600) / 600.0f;
	for (int y = 0; y < c->height; ++y) {
		for (int x = 0; x < c->width; ++x) {
			size_t idx = (size_t)y * (size_t)c->width + (size_t)x;
			float v = 0.85f + 0.15f * sinf(2.0f * 3.1415926535f * (t + (float)x / (float)c->width));
			c->jnd[idx] = clampf(v, 0.60f, 1.20f);
		}
	}
}

// Embed skeleton interface for stage-2 migration:
// I_lum = bg + Tw * JND * alpha
static float wm_embed_delta(const struct wm_template_cache *c, int x, int y, float alpha) {
	if (!c->valid || !c->tw || !c->jnd) {
		return 0.0f;
	}
	size_t idx = (size_t)y * (size_t)c->width + (size_t)x;
	return c->tw[idx] * c->jnd[idx] * alpha;
}

static void wm_apply_checker(struct wlr_renderer *renderer,
		struct wlr_output *wlr_output, float alpha, int step) {
	struct wlr_box box = {0};
	for (int y = 0; y < wlr_output->height; y += step) {
		for (int x = 0; x < wlr_output->width; x += step) {
			if ((((x / step) + (y / step)) & 1) == 0) {
				continue;
			}
			box.x = x;
			box.y = y;
			box.width = step;
			box.height = step;

			float color[4] = {alpha, alpha, alpha, alpha};
			wlr_render_rect(renderer, &box, color, wlr_output->transform_matrix);
		}
	}
}

static void wm_apply_embed_stub(struct wlr_renderer *renderer,
		struct wlr_output *wlr_output, struct wm_runtime_state *st) {
	int step = st->checker_cell;
	wm_cache_rebuild(&st->cache, wlr_output->width, wlr_output->height, step);
	if (!st->cache.valid) {
		return;
	}

	if (st->frame_idx % st->jnd_period_frames == 0) {
		wm_refresh_simple_jnd(&st->cache, st->frame_idx);
	}

	// Minimal visual proxy for embed path: block-wise render using cached Tw/JND/alpha.
	struct wlr_box box = {0};
	for (int y = 0; y < wlr_output->height; y += step) {
		for (int x = 0; x < wlr_output->width; x += step) {
			float delta = wm_embed_delta(&st->cache, x, y, st->alpha);
			if (fabsf(delta) < 0.005f) {
				continue;
			}
			float a = clampf(fabsf(delta), 0.0f, 0.08f);
			box.x = x;
			box.y = y;
			box.width = step;
			box.height = step;
			float color[4] = {a, a, a, a};
			wlr_render_rect(renderer, &box, color, wlr_output->transform_matrix);
		}
	}
}

// Stage-2 runtime hook: minimal patch + embed migration skeleton.
void watermark_runtime_apply(struct sway_output *output,
		pixman_region32_t *damage) {
	wm_runtime_init_once();
	if (!g_wm_state.enabled || !output || !output->wlr_output) {
		return;
	}

	struct wlr_output *wlr_output = output->wlr_output;
	struct wlr_renderer *renderer = wlr_backend_get_renderer(wlr_output->backend);
	if (!renderer) {
		return;
	}

	if (g_wm_state.force_full_damage) {
		output_damage_whole(output);
		if (damage) {
			pixman_region32_union_rect(damage, damage, 0, 0,
				wlr_output->width, wlr_output->height);
		}
	}

	// Ensure overlay is not clipped by previously set damage scissor rectangles.
	wlr_renderer_scissor(renderer, NULL);

	float phase = (float)g_wm_state.frame_idx * 0.05f;
	float freq = 32.0f;
	bool use_shader = g_wm_state.use_shader_poc || g_wm_state.use_shader_tw;
	bool use_tw = g_wm_state.use_shader_tw;
	bool use_jnd = g_wm_state.use_shader_tw;

	if (g_wm_state.use_shader_tw) {
		uint16_t slot = wm_time_slot_now(&g_wm_state);
		if (g_wm_state.tw_template_u8 == NULL ||
				g_wm_state.tw_template_width != wlr_output->width ||
				g_wm_state.tw_template_height != wlr_output->height ||
				g_wm_state.current_slot != slot) {
			wm_build_real_tw_template(&g_wm_state, wlr_output->width,
				wlr_output->height, slot);
		}
		if (g_wm_state.tw_template_u8) {
			wlr_gles2_renderer_set_watermark_template(renderer,
				g_wm_state.tw_template_u8,
				(uint32_t)g_wm_state.tw_template_width,
				(uint32_t)g_wm_state.tw_template_height);
		}
	}

	wlr_gles2_renderer_set_watermark(renderer, use_shader,
		g_wm_state.alpha, phase, freq, use_tw, use_jnd);

	int step = clampi(g_wm_state.checker_cell, 8, 96);
	if (g_wm_state.use_shader_poc || g_wm_state.use_shader_tw) {
		// shader_* modes: fragment modulation is injected in wlroots gles2 shaders.
	} else if (g_wm_state.use_embed_stub) {
		wm_apply_embed_stub(renderer, wlr_output, &g_wm_state);
	} else {
		wm_apply_checker(renderer, wlr_output, g_wm_state.alpha, step);
	}

	if (damage) {
		pixman_region32_union_rect(damage, damage, 0, 0,
			wlr_output->width, wlr_output->height);
	}

	if (g_wm_state.debug_log && (g_wm_state.frame_idx % 120 == 0)) {
		sway_log(SWAY_DEBUG,
			"wm_runtime_apply frame=%d mode=%s output=%dx%d alpha=%.3f force_full=%d",
			g_wm_state.frame_idx,
			g_wm_state.use_shader_tw ? "shader_tw" :
				(g_wm_state.use_shader_poc ? "shader_poc" :
				(g_wm_state.use_embed_stub ? "embed_stub" : "checker")),
			wlr_output->width, wlr_output->height, g_wm_state.alpha,
			g_wm_state.force_full_damage);
	}

	g_wm_state.frame_idx++;
}
