# Codex Task 01

你当前在一个名为 `sway-watermark-project` 的工作区中工作。

请先阅读以下文件：

- `docs/thesis_requirements.md`
- `docs/design_notes.md`
- `docs/papers/Real-time-and-screen-cam-robust-screen-watermarking.pdf`

---

# 当前阶段目标

当前只做 **阶段一：离线算法原型**。

请不要修改以下目录中的源码：

- `third_party/sway-1.2/`
- `third_party/wlroots-0.6/`

当前阶段的全部新增实现都放在：

- `prototype/watermark_core/`

---

# 当前目录结构

请严格基于当前目录结构工作，不要随意重组目录：

- `prototype/watermark_core/payload/`
- `prototype/watermark_core/template_gen/`
- `prototype/watermark_core/embed/`
- `prototype/watermark_core/detect/`
- `prototype/watermark_core/cli/`
- `prototype/watermark_core/tests/`

---

# 第一阶段总目标

请实现一个最小可运行闭环，完成以下流程：

1. 生成 payload bits
2. 生成 `Tm`
3. 生成 `Ta`、`Tb`
4. 生成 `Tw`
5. 将 `Tw` 嵌入输入 RGB 图像
6. 对攻击后图像进行检测
7. 恢复并输出：
   - `device_id`
   - `time_slot`
   - `crc_ok/fail`

---

# 方法约束

请参考论文 **Real-time and screen-cam robust screen watermarking** 的总体思路，
但允许做适当简化。

应尽量保留：

1. 消息模板 + 同步模板结构
2. 分辨率自适应模板
3. 简化 JND 嵌入
4. 同步模板定位
5. 透视校正
6. DFT 域消息恢复

允许简化：

1. 不使用 QR
2. 不嵌入 IP / userID / security level
3. 只做 `device_id + time_slot + crc16`
4. 先只支持单显示器
5. 先不做深度学习方法
6. 若完整复现论文某一步过重，可采用工程替代方案

注意：

- 若采用替代方案，必须在 `prototype/watermark_core/README.md` 中说明
- 不要伪装成“完整复现论文”

---

# 载荷要求

请按以下方式实现 payload：

- `device_id = 0x1A2B3C4D`
- `time_slot = floor((unix_time - T0) / 300)`
- `crc16`

建议位布局：

- `device_id(32)`
- `time_slot(16)`
- `crc16(16)`

总长度约：

- 64 bit

要求：

- 提供打包函数
- 提供解包函数
- 提供 bitstream 表示
- 提供 CRC 校验函数

---

# 语言要求

第一阶段语言不限，但请优先使用最适合快速原型的方法。

推荐优先使用：

- Python

如果你认为其他语言更适合，请先在 README 中写清理由。

注意：

- 第一阶段重点是快速验证闭环
- 第二阶段实时嵌入模块需要迁移为适合集成到 C 项目的实现

---

# 模块任务

## A. payload

位置：

- `prototype/watermark_core/payload/`

任务：

1. 生成 payload
2. 支持输入：
   - `device_id`
   - `unix_time`
   - `T0`
3. 输出 bitstream
4. 支持解析 bitstream
5. 支持 CRC16 校验
6. 提供最小单元测试

---

## B. template_gen

位置：

- `prototype/watermark_core/template_gen/`

任务：

1. 生成 message template `Tm`
2. 生成 sync templates `Ta` 与 `Tb`
3. 组合为 `Tw`
4. 模板要能随输入分辨率自适应
5. 优先参考论文中的 `L1/L2`、`R1/R2` 设计
6. 若第一版无法完整复现，也要保留“消息模板 + 同步模板 + 拼接”的结构

输出要求：

- 可以将模板保存为图像或数组
- 提供最小 demo
- 提供 README 中的参数说明

---

## C. embed

位置：

- `prototype/watermark_core/embed/`

任务：

1. 输入 RGB 图像与 `Tw`
2. 转换到亮度或可嵌入通道
3. 生成简化 JND 或局部强度调制图
4. 按下面公式嵌入：

   `I_lum = bg + Tw * JND * alpha`

5. 输出嵌入后的图像
6. `alpha` 应支持参数化
7. 默认 `alpha` 可设置为 `0.35`

要求：

- 模块接口要尽量清晰
- 后续便于迁移到 C

---

## D. detect

位置：

- `prototype/watermark_core/detect/`

任务：

1. 输入攻击后图像
2. 做预处理
3. 基于同步模板做定位
4. 做透视校正
5. 从校正后的消息区域恢复 bitstream
6. 解析 payload
7. 做 CRC16 校验
8. 输出：
   - `device_id`
   - `time_slot`
   - `crc_ok / fail`

注意：

- 如果完整实现论文中的两轮检测过重，可以先实现简化版
- 但必须至少包含：
  - 同步模板参与定位
  - 透视校正
  - payload 恢复
  - CRC 验证

---

## E. cli

位置：

- `prototype/watermark_core/cli/`

任务：

请提供最小命令行工具或 demo，至少包括：

1. 生成 payload
2. 生成模板
3. 嵌入图像
4. 解码图像

要求：

- README 中必须给出可复制执行的示例命令

---

## F. tests

位置：

- `prototype/watermark_core/tests/`

至少提供以下测试：

1. 原图嵌入后直接恢复 payload
2. 透视变换后恢复 payload
3. JPEG 压缩后恢复 payload

可选测试：

- scaling
- blur
- brightness perturbation
- gamma
- rotation
- crop
- 简化 screen-cam 模拟

如果某项暂时无法通过：

- 不要伪造通过
- 请明确记录失败原因与改进方向

---

# README 要求

请填写：

- `prototype/watermark_core/README.md`

必须包括：

1. 当前实现结构
2. 各模块职责
3. 依赖
4. 安装方式
5. 运行方式
6. demo 说明
7. 测试方式
8. 当前参数
9. 与参考论文相比的简化点
10. 当前限制
11. 第二阶段如何迁移 `embed` 到 C 并接入 Sway/wlroots

---

# 工作风格要求

1. 先追求“最小可运行闭环”
2. 不要一开始就追求完整复现论文所有细节
3. 不要一开始就过度设计
4. 不要修改 third_party 目录
5. 关键函数要写注释
6. 关键参数要集中说明
7. 不确定的地方明确写出假设
8. 所有偏离论文原方法的地方都要写清楚

---

# 完成后的输出要求

阶段一完成后，请给出：

1. 新增文件列表
2. 模块职责说明
3. 关键参数说明
4. 运行命令
5. 测试结果摘要
6. 当前限制
7. 下一步如何进入第二阶段

---

# 第二阶段提示（当前先不要做）

阶段二才会开始：

- 阅读 `third_party/sway-1.2/`
- 阅读 `third_party/wlroots-0.6/`
- 定位最终输出帧路径
- 在 `integration/` 下写集成说明与最小 patch 计划

当前阶段请不要开始第二阶段。