# 阶段二最小验证 patch 设计说明

## 拟修改文件（第一版）

> 当前提交先把验证代码放在 `integration/watermark_runtime/`，先不直接改 third_party 源码。

后续真实接入时目标文件：
- `third_party/sway-1.2/sway/desktop/render.c`

## 修改目的

验证命题：
- 在“最终输出帧形成后、提交前”能否稳定修改像素内容。

第一版不追求鲁棒模板，只做：
- 轻微亮度偏移
- 或简单棋盘模板覆盖

## 预计新增结构

- `struct watermark_runtime_ctx`（每输出一个）
  - enable 开关
  - alpha
  - checker cell size
  - 上次更新时间

## 预计新增函数

- `wm_runtime_apply_checker_overlay(renderer, output, damage, alpha)`
- `wm_runtime_should_refresh_payload(now)`
- `wm_runtime_update_cached_template(...)`

## 缓存策略（建议）

- payload（device_id/time_slot/crc）每 5 分钟更新一次
- JND map 每 5 秒更新一次（或内容变化触发）
- 每帧仅执行“轻量叠加”

## 风险

1. 性能风险：全屏 per-frame 操作在 4K 下可能超预算。
2. 视觉风险：alpha 过高可见。
3. 兼容风险：不同 backend（DRM/X11/Wayland）表现差异。
4. 维护风险：直接 patch wlroots 核心会放大维护成本。

## 结论

第一版应先验证 patch 点可行性；鲁棒模板与完整 payload 嵌入留给后续迭代。

## 补充：当前运行时开关（环境变量）

- `SWAY_WM_ENABLE=0/1`
- `SWAY_WM_MODE=checker|embed_stub|shader_poc|shader_tw`
- `SWAY_WM_ALPHA=0.0~0.30`
- `SWAY_WM_TW_SCALE=1~64`
- `SWAY_WM_CELL=8~96`
- `SWAY_WM_JND_PERIOD=1~3600`
- `SWAY_WM_DEBUG=0/1`
- `SWAY_WM_FORCE_FULL_DAMAGE=0/1`

## 补充：embed 迁移骨架（已预留）

已在 `watermark_runtime.c` 预留以下数据流骨架：

- 模板缓存：`wm_template_cache`（`tw`）
- 简化强度图缓存：`jnd`
- 嵌入计算：`wm_embed_delta()`
  - `delta = Tw * JND * alpha`
- 更新节奏：
  - per-frame 调用 `watermark_runtime_apply()`
  - `jnd` 按 `SWAY_WM_JND_PERIOD` 低频更新
