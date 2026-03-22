# watermark_core

本目录用于实现一个面向 **Sway 1.2 / wlroots 0.6** 项目的
**离线屏幕鲁棒水印算法原型**。

当前阶段目标不是直接接入 compositor，
而是先完成一个“最小可运行闭环”：

1. 生成 payload
2. 生成消息模板 `Tm`
3. 生成同步模板 `Ta` / `Tb`
4. 组合得到总模板 `Tw`
5. 将 `Tw` 嵌入输入图像
6. 对攻击后图像执行检测与恢复
7. 输出：
   - `device_id`
   - `time_slot`
   - `crc_ok / fail`

---

# 1. 项目背景

本原型用于验证一个适合硕士论文的小型创新点：

- 将面向 screen-cam 场景的实时鲁棒水印方法迁移到 Wayland / Sway 场景
- 载荷仅保留取证所需的最小信息：
  - 固定设备标识
  - 粗粒度时间信息
- 不追求工业级完整方案
- 优先证明“思路成立、系统可落地、结果可写论文”

参考论文：

- **Real-time and screen-cam robust screen watermarking**

本原型只保留其核心骨架，不要求完整复现全部细节。

---

# 2. 当前阶段范围

当前只做 **阶段一：离线算法原型**。

不修改以下目录：

- `third_party/sway-1.2/`
- `third_party/wlroots-0.6/`

当前目录下实现的内容主要用于：

- 验证 payload 设计
- 验证模板结构 `Tm/Ta/Tb/Tw`
- 验证简化 JND 嵌入
- 验证同步模板定位 + 透视校正 + 消息恢复
- 为后续把 `embed` 模块迁移到 C 并接入 Sway 做准备

---

# 3. 目录结构

当前建议目录结构如下：

- `payload/`
  - `core.py`：payload 打包、解包、bitstream、CRC16
- `template_gen/`
  - `core.py`：生成 `Tm`、`Ta`、`Tb`、`Tw`
- `embed/`
  - `core.py`：读取/写入 PPM，简化 JND，嵌入 `Tw`
- `detect/`
  - `core.py`：同步点检测、透视校正、消息恢复、CRC 校验
- `cli/`
  - `main.py`：最小命令行 demo
- `tests/`
  - `test_payload.py`：payload 基础测试
  - `test_pipeline.py`：direct/perspective/jpeg-like 闭环测试

---

# 4. 载荷设计

当前采用固定长度 bitstream，不使用 QR。

建议载荷格式：

`payload = device_id(32) || time_slot(16) || crc16(16)`

其中：

- `device_id = 0x1A2B3C4D`
- `time_slot = floor((unix_time - T0) / 300)`
- `T0` 默认值：`2025-01-01 00:00:00 UTC`

说明：

- `device_id` 固定，用于设备归因
- `time_slot` 为 5 分钟粒度的时间槽
- `crc16`（CCITT）用于恢复结果校验
- 总长度 64 bit

---

# 5. 方法骨架

本原型保留论文主骨架，但采用工程化轻量实现：

1. 生成消息模板 `Tm`
2. 生成同步模板 `Ta`
3. 生成同步模板 `Tb`
4. 组合为总模板 `Tw`
5. 通过简化 JND 将 `Tw` 嵌入输入图像
6. 在检测端利用同步模板进行定位
7. 进行透视校正
8. 在简化 DFT 投影域恢复消息位
9. 解析 payload 并做 CRC 校验

---

# 6. 与参考论文相比的简化点

1. **不使用 QR**：固定 64bit bitstream。
2. **不嵌入长消息**：仅 `device_id + time_slot + crc16`。
3. **同步模板简化**：采用棋盘 marker（Ta/Tb）代替论文更复杂的同步设计。
4. **消息恢复简化但向频域靠拢**：当前实现为“块内余弦匹配（近似频域判决）”，仍非论文完整版 DFT 流程。
5. **JND 简化**：局部亮度 + 梯度调制，不声称完整复现论文视觉模型。
6. **图像 IO 简化**：当前内置 PPM（P6/P3）读写，便于无第三方依赖运行。

> 以上简化用于优先实现“最小闭环”。对鲁棒性影响：在强噪声、重压缩、强模糊、严重几何失真下性能会明显下降。

---

# 7. 参数建议

默认参数：

- `device_id = 0x1A2B3C4D`
- `alpha = 0.35`
- `T0 = 2025-01-01T00:00:00Z`
- `time_slot = floor((unix_time - T0) / 300)`

模板自适应参数（与分辨率 `M x N` 相关）：

- `L1 = max(64, floor(0.47 * min(M, N)))`（主 ROI 边长）
- `L2 = max(11, floor(0.06 * min(M, N)) 且为奇数)`（同步 marker 尺寸）

---

# 8. 嵌入策略

嵌入公式：

`I_lum = bg + Tw * JND * alpha`

实现说明：

- `bg`：当前像素亮度
- `Tw`：组合模板
- `JND`：简化局部调制图（亮度 + 梯度）
- `alpha`：嵌入强度（默认 0.35）

---

# 9. 检测策略

检测端流程：

1. 输入攻击后图像
2. 提取亮度
3. 通过四个角点专用 marker 的相关性+NMS 生成候选
4. 对候选组合做几何筛选（面积/重投影误差）并估计透视四边形
5. 透视校正到 canonical ROI 后，用块内余弦匹配恢复 64 bit（阶段一简化）
6. 解析 payload
7. CRC16 校验并输出结果

---

# 10. 当前实现要求

已实现：

- 模块边界清晰（payload/template/embed/detect/cli/tests）
- 参数集中在代码默认值 + CLI 参数
- 关键简化点有说明

未实现：

- 完整论文双轮定位
- 深度学习恢复
- 多显示器/多设备联合同步

---

# 11. 运行方式

## 11.1 环境

当前实现无第三方 Python 依赖，使用标准库即可运行（测试使用 `pytest`）。

## 11.2 生成 payload

```bash
PYTHONPATH=prototype python -m watermark_core.cli.main payload --unix-time 1735689600
```

## 11.3 生成模板元信息

```bash
PYTHONPATH=prototype python -m watermark_core.cli.main template --width 256 --height 256 --bits 0101010101010101010101010101010101010101010101010101010101010101
```

## 11.4 嵌入图像（输入需为 PPM）

```bash
PYTHONPATH=prototype python -m watermark_core.cli.main embed --input prototype/samples/input.ppm --output prototype/samples/wm.ppm --unix-time 1735689600 --alpha 0.35
```

## 11.5 解码图像

```bash
PYTHONPATH=prototype python -m watermark_core.cli.main detect --input prototype/samples/wm.ppm --unix-time 1735689600
```

---

# 12. 测试目标

当前测试覆盖：

1. 原图嵌入后直接恢复 payload
2. 轻度透视变换后恢复 payload（strength <= 0.03）
3. JPEG-like 量化压缩后恢复 payload（当前测试条件：block=8, q=12）
4. 中等透视（strength=0.05）当前仍标记 xfail

运行：

```bash
PYTHONPATH=prototype pytest -q prototype/watermark_core/tests
```

---

# 13. 当前限制

1. 仅为离线原型，不是 compositor 集成版本。
2. 当前同步检测是简化相关搜索，复杂场景易误检。
3. 当前仅支持 PPM 输入输出（便于零依赖）。
4. 当前 attack 仿真为轻量实现，不等同真实手机拍摄 pipeline。
5. 未做性能优化（纯 Python，非实时）。
6. 当前未完整实现论文 DFT 消息恢复，属于工程化替代。
7. 当前“轻度透视”可稳定恢复；中等透视(0.05)仍有失败样本，测试中保留 xfail。

---

# 14. 下一阶段计划

当阶段一完成后，进入阶段二：

1. 分析 `third_party/sway-1.2/` 和 `third_party/wlroots-0.6/` 输出路径。
2. 确定“最终输出帧形成后、提交前”的最小 patch 点。
3. 做最小验证 patch（亮度微扰或棋盘模板写入）。
4. 再迁移 `embed` 为 C 并接入 compositor。

---

# 15. 迁移到 C / Sway 的方向

- `payload`
  - 建议迁移为 C（时间槽计算 + CRC16 很轻量）。
- `template_gen`
  - 可离线预生成，也可 compositor 启动时生成并缓存。
- `embed`
  - 必须迁移为 C，做每帧执行。
- `detect`
  - 保持离线 Python 工具，用于取证分析。

更新频率建议：

- payload：每 5 分钟更新一次（time_slot 边界）
- JND：每 5 秒或场景变化时更新一次
- 每帧：使用缓存模板进行快速嵌入

---

# 16. 给 Codex 的额外要求

已按“最小可运行闭环”实现，不追求第一版完整复现论文全部细节。

如果后续增强鲁棒性，建议优先补强：

1. 更稳健的同步定位（多尺度 + RANSAC）
2. 更接近论文的频域模板与检测
3. 更真实的 screen-cam 攻击仿真
4. 参数扫描与 BER/PSNR 评估脚本
