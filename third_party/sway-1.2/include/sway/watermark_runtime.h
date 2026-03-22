#ifndef _SWAY_WATERMARK_RUNTIME_H
#define _SWAY_WATERMARK_RUNTIME_H

#include <pixman.h>

struct sway_output;

void watermark_runtime_apply(struct sway_output *output,
	pixman_region32_t *damage);

#endif
