# 阶段二候选接入点（Sway 1.2 / wlroots 0.6.0）

## 1) 输出路径概览（基于当前仓库源码）

- Sway 在 `damage_handle_frame` 中触发逐帧渲染入口。  
  文件：`third_party/sway-1.2/sway/desktop/output.c`
- 真正的合成绘制在 `output_render(...)` 中执行。  
  文件：`third_party/sway-1.2/sway/desktop/render.c`
- 在 `output_render` 末尾会调用：
  1. `wlr_output_render_software_cursors(...)`
  2. `wlr_renderer_end(...)`
  3. `wlr_output_set_damage(...)`
  4. `wlr_output_commit(...)`

这意味着“最终帧形成后、提交前”的窗口就在 `render.c` 的函数尾部附近。

---

## 2) 候选文件与候选函数

### 候选 A（优先）
- 文件：`third_party/sway-1.2/sway/desktop/render.c`
- 函数：`output_render(struct sway_output *output, struct timespec *when, pixman_region32_t *damage)`
- 原因：
  - 已完成场景内容绘制（背景、窗口、层、光标）
  - 即将 `wlr_output_commit`
  - 对应“最终输出帧形成后、提交前”的最小 patch 位置
- 可获取数据：
  - `wlr_output`（分辨率、scale、transform）
  - 当前 damage region
  - renderer 上下文（在 `wlr_renderer_end` 前）

### 候选 B
- 文件：`third_party/sway-1.2/sway/desktop/output.c`
- 函数：`damage_handle_frame(...)`
- 原因：
  - 帧调度与 damage 生命周期在这里
  - 便于控制“更新频率”（例如 5s 更新 JND，5min 更新时间槽）
- 可获取数据：
  - 时间戳、frame 调度状态、是否需要重绘
- 局限：
  - 这里不是最终像素写入点，仍需跳回 `render.c` 做像素操作

### 候选 C（更底层）
- 文件：`third_party/wlroots-0.6.0/types/wlr_output.c`
- 函数：`wlr_output_commit(...)`
- 原因：
  - 全局提交路径，理论上最靠近后端提交
- 局限：
  - 影响范围大，不利于第一版最小改动
  - 不建议阶段二首版直接改 wlroots 核心

---

## 3) Sway 与 wlroots 的职责边界

- Sway：决定“画什么、何时画、按什么层级画”，并在 `output_render` 中调度渲染。
- wlroots：提供输出抽象、renderer 抽象和后端提交（DRM/X11/Wayland 等）。

阶段二第一版建议：先在 **Sway 的 `output_render` 尾部** 验证可写像素模板；稳定后再考虑下沉到 wlroots。

---

## 4) 第一版最优 patch 点

**推荐：`third_party/sway-1.2/sway/desktop/render.c::output_render`**

插入位置建议：
- 在主要 scene 渲染完成后
- 在 `wlr_renderer_end(renderer)` 之前

理由：
- 能保证覆盖最终输出帧
- 代码侵入最小
- 便于逐步替换为真实 `embed` C 实现
