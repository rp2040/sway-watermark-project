# integration

本目录记录阶段二（Sway/wlroots 集成）的分析与最小验证实现。

## 1. 思路总览

- 阶段一：Python 离线闭环（payload/template/embed/detect）
- 阶段二：定位真实渲染路径，验证 compositor 中可插入嵌入点

当前建议接入点：
- `sway/desktop/render.c::output_render` 的末尾（`wlr_renderer_end` 之前）

## 2. 阶段一到阶段二映射

- `payload`（Python） -> C 版轻量模块（time_slot + crc16）
- `template_gen`（Python） -> 离线预生成或启动时生成缓存
- `embed`（Python） -> C 版每帧执行核心（必须迁移）
- `detect`（Python） -> 继续离线取证工具（不进 compositor）

## 3. 哪些模块迁移为 C

必须迁移：
- embed

建议迁移：
- payload（计算量小，迁移成本低）

可暂不迁移：
- detect（离线分析）

## 4. watermark_runtime 最小验证说明

`integration/watermark_runtime/minimal_runtime_patch_example.c` 提供一个“验证 patch 模板”：
- 目标：验证像素可改写
- 内容：在最终帧叠加轻微棋盘亮度扰动
- 注意：**不是最终鲁棒水印实现**

## 5. 更新频率建议

- payload：每 5 分钟（time_slot 边界）
- JND：每 5 秒（或内容剧烈变化时）
- 每帧：使用缓存模板执行快速叠加

## 6. 下一步

1. 把最小 patch 挂到 `output_render` 尾部做实际编译验证。
2. 把阶段一 `embed` 迁移成 C 函数接口（输入 luminance + cached template + alpha）。
3. 增加开关参数（sway config / 环境变量）控制启停与强度。

## 7. 编译与运行验证（最小可执行方案）

### 7.1 编译（Sway 1.2 源码树）

```bash
cd third_party/sway-1.2
meson setup build-stage2 --buildtype=debugoptimized
ninja -C build-stage2
```

### 7.2 运行（建议先验证 checker）

```bash
SWAY_WM_ENABLE=1 \
SWAY_WM_MODE=checker \
SWAY_WM_ALPHA=0.03 \
SWAY_WM_CELL=24 \
SWAY_WM_DEBUG=1 \
SWAY_WM_FORCE_FULL_DAMAGE=1 \
./build-stage2/sway -c /path/to/sway/config
```

### 7.3 判定 patch 生效

满足任一即可认为 patch 点生效：

1. 视觉上出现极轻微棋盘亮度扰动（大面积纯色背景更易观察）；
2. 日志中周期性出现 `wm_runtime_apply ...`；
3. 修改 `SWAY_WM_ALPHA`（如 0.01/0.08）后可见强度随参数变化。
4. 打开 `SWAY_WM_FORCE_FULL_DAMAGE=1` 后，图案不再仅跟随活动 damage 区闪烁。

### 7.4 embed 骨架验证

```bash
SWAY_WM_ENABLE=1 \
SWAY_WM_MODE=embed_stub \
SWAY_WM_ALPHA=0.03 \
SWAY_WM_JND_PERIOD=300 \
SWAY_WM_DEBUG=1 \
SWAY_WM_FORCE_FULL_DAMAGE=1 \
./build-stage2/sway -c /path/to/sway/config
```

`embed_stub` 仍是最小骨架，不是完整鲁棒水印实现。


### 7.5 wlroots shader PoC 运行

```bash
SWAY_WM_ENABLE=1 \
SWAY_WM_MODE=shader_poc \
SWAY_WM_ALPHA=0.03 \
SWAY_WM_DEBUG=1 \
SWAY_WM_FORCE_FULL_DAMAGE=1 \
./build-stage2/sway -c /path/to/sway/config
```

该模式不走 `wlr_render_rect` 覆盖，而是通过 wlroots gles2 texture fragment shader 做片元级亮度调制 PoC。

### 7.6 wlroots shader_tw（最小 Tw 驱动）运行

```bash
SWAY_WM_ENABLE=1 \
SWAY_WM_MODE=shader_tw \
SWAY_WM_ALPHA=0.03 \
SWAY_WM_DEBUG=1 \
SWAY_WM_FORCE_FULL_DAMAGE=1 \
./build-stage2/sway -c /path/to/sway/config
```

`shader_tw` 会按输出分辨率一比一采样 Tw 纹理并做简化 JND 调制，不再通过 `TW_SCALE` 做重复/缩放采样。

## 8. 端到端最小闭环实验（runtime 注入 -> 手机拍照 -> detect）

1. 运行 `shader_tw` 模式并保持静态测试画面（全屏窗口/高对比内容）。  
2. 用手机对屏幕拍照，保存为原图（建议关闭美颜/AI 增强）。  
3. 将照片转换为 PPM（若 detect 当前只支持 PPM）。  
4. 使用 `prototype/watermark_core` 的 detect 命令进行恢复：  

```bash
PYTHONPATH=prototype python -m watermark_core.cli.main detect \
  --input /path/to/photo.ppm \
  --unix-time <拍摄时刻unix时间>
```

5. 成功判据：  
   - `device_id == 0x1A2B3C4D`  
   - `time_slot` 与拍摄时刻对应 5 分钟槽一致或相邻  
   - `crc_ok == true`
