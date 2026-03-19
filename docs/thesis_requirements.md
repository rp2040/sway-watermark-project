# 项目目标

本项目用于实现一个面向 **Sway 1.2 / wlroots 0.6** 的实时屏幕鲁棒水印原型，
目标场景是 **手机拍屏 / 相机翻拍后的取证恢复**。

该项目服务于硕士论文中的一个创新点，因此要求：

- 能落地实现
- 结构清晰
- 便于论文描述
- 不追求工业级完整产品
- 控制实现范围，优先完成“最小可运行闭环”

---

# 研究目标

实现一个系统，使得：

1. 在屏幕最终显示内容中嵌入不可见鲁棒水印
2. 水印包含固定设备标识和变化时间信息
3. 当屏幕被手机拍照后，可以从照片中恢复：
   - `device_id`
   - `time_slot`
   - `crc 校验结果`

---

# 最小可运行目标

## 第一阶段：离线算法原型

先不修改 Sway 或 wlroots，只完成以下闭环：

1. 生成载荷 `payload`
2. 生成消息模板 `Tm`
3. 生成同步模板 `Ta`、`Tb`
4. 组合得到总模板 `Tw`
5. 将 `Tw` 嵌入输入图像
6. 对攻击后图像执行检测与恢复
7. 输出 `device_id`、`time_slot`、`crc_ok/fail`

## 第二阶段：Sway/wlroots 集成

在第一阶段跑通后，再分析并接入：

1. 找到 Sway 1.2 / wlroots 0.6 中最终输出帧的形成路径
2. 找到适合插入实时水印的位置
3. 先做最小验证 patch
4. 再将实时嵌入模块迁移为适合集成到 C 项目的实现

---

# 载荷要求

载荷设计采用固定字段与变化字段结合的方式：

- `device_id = 0x1A2B3C4D`
- `time_slot = floor((unix_time - T0) / 300)`
- `crc16`

建议位布局：

- `device_id`: 32 bit
- `time_slot`: 16 bit
- `crc16`: 16 bit

总长度约为：

- 64 bit

说明：

- `device_id` 固定，用于标识设备
- `time_slot` 变化，用于反映粗粒度偷拍时间
- 时间粒度为 5 分钟，足够用于取证
- 不要求秒级精度
- 不使用 QR，改用固定长度 bitstream

---

# 方法要求

总体方法参考论文 **Real-time and screen-cam robust screen watermarking**，但允许轻量化简化。

## 应尽量保留的骨架

1. 预生成 watermark template
2. watermark template 包含：
   - message watermark template (`Tm`)
   - synchronization watermark templates (`Ta`, `Tb`)
3. 模板分辨率自适应
4. 通过简化 JND 控制嵌入强度
5. 在最终待显示内容中进行嵌入
6. 检测端基于同步模板进行定位
7. 执行透视校正
8. 在 DFT 域恢复消息

## 允许简化的部分

1. 不使用 QR
2. 不嵌入 IP、userID、安全等级等长消息
3. 只做 `device_id + time_slot + crc16`
4. 先只考虑单显示器
5. 先不做深度学习方法
6. 若完整复现论文某一步过重，可做工程替代，但必须写清楚

---

# 工程约束

1. 第一阶段不要修改：
   - `third_party/sway-1.2/`
   - `third_party/wlroots-0.6/`

2. 第一阶段新增代码仅放在：
   - `prototype/watermark_core/`

3. 第二阶段进行集成分析时：
   - 尽量少改 third_party 源码
   - 不做大规模重构
   - 优先找到“最终输出帧形成后、提交前”的最小 patch 点

4. 实时嵌入模块最终应适合以 **C** 语言形式接入 compositor

---

# 目录约定

当前目录结构如下：

- `docs/`：需求文档、设计说明、任务说明、参考论文
- `third_party/`：Sway 1.2 与 wlroots 0.6 源码
- `prototype/watermark_core/`：离线原型实现
- `integration/`：第二阶段集成分析与 patch 说明
- `experiments/`：实验样本、攻击模拟与结果

---

# 对 Codex 的总体要求

请优先追求：

- 最小可运行闭环
- 模块边界清晰
- 接口清晰
- 代码可读
- 文档可直接用于论文整理

请不要：

- 一开始就完整复现论文所有细节
- 一开始就大范围修改 Sway / wlroots
- 一开始就引入深度学习模型
- 一开始就追求多平台支持

---

# 期望的阶段性结果

## 阶段一完成后，应至少具备：

1. 可生成 payload
2. 可生成 `Tm / Ta / Tb / Tw`
3. 可将水印嵌入图像
4. 可从数字攻击图像中恢复 payload
5. 至少对以下攻击做基本测试：
   - perspective transform
   - JPEG compression
   - scaling / blur / brightness perturbation（至少部分）

## 阶段二完成后，应至少具备：

1. 能定位 Sway/wlroots 中可插入嵌入模块的位置
2. 能做最小 patch 验证最终输出帧像素可修改
3. 能给出 embed 模块迁移到 C 的清晰方案

---

# 成果边界

本项目不是完整商业系统，而是面向论文原型验证。

因此：

- 优先证明“思路成立”
- 优先证明“可以在 Sway 场景中落地”
- 优先证明“device_id + time_slot 可以恢复”
- 不要求一开始就做到最优鲁棒性