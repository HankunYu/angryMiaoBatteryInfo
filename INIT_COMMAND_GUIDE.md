# 怒喵鼠标初始化命令获取指南

## 问题描述

在没有怒喵软件运行的情况下，直接读取 Report 0x3F 无法获取正确的电池数据。这是因为设备需要特定的初始化命令来启用电池报告功能。

## 解决方案概览

有三种方法来找出正确的初始化命令：

1. **方法A**: 尝试常见的初始化命令（快速，但可能不成功）
2. **方法B**: 监控设备状态变化（无需额外软件）
3. **方法C**: 使用USB抓包工具（最可靠）

---

## 方法A: 自动测试常见命令

使用提供的测试脚本来尝试常见的HID初始化模式。

### 步骤

```bash
# 1. 确保怒喵软件已关闭
# 2. 运行测试脚本
python test_init_commands.py
```

### 脚本会做什么

- 尝试20+种常见的HID初始化命令
- 自动检测哪些命令能让设备返回有效的电池数据
- 输出可直接使用的命令格式

### 示例输出

```
✓ 找到 1 个有效命令:

  - 电池报告请求 - Report 0x3F (扩展)
    命令: 3F 01 00
    使用方法: --send "3F 01 00"
```

### 使用找到的命令

```bash
python probe_mouse_battery.py \
  --path "\\?\HID#VID_3151&PID_5007&MI_02#8&512c24e&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}" \
  --send "3F 01 00" \
  --scan 0x3F \
  --feature-length 64 \
  --poll 1
```

---

## 方法B: 监控设备状态变化

如果方法A没有成功，使用监控工具来观察怒喵软件对设备做了什么。

### 模式1: 持续监控（推荐）

```bash
# 1. 启动监控（怒喵软件关闭状态）
python capture_hid_traffic.py --mode monitor --interval 0.5

# 2. 观察初始状态的数据输出
# 3. 打开怒喵软件
# 4. 观察数据变化

# 按 Ctrl+C 停止
```

### 监控输出示例

```
[轮询 #5] 14:23:15
----------------------------------------------------------------------

🔄 Report 0x3F 数据已改变!
   旧: 00 00 00 00 00 00 00 00 ...
   新: D6 00 01 10 00 00 00 29 ...
      byte[0]: 0x00 → 0xD6 (0 → 214)
      byte[2]: 0x00 → 0x01 (0 → 1)
      byte[3]: 0x00 → 0x10 (0 → 16)    ← 这是电量!
      byte[7]: 0x00 → 0x29 (0 → 41)
```

### 模式2: 快照对比

```bash
# 1. 运行快照工具
python capture_hid_traffic.py --mode snapshot --snapshots 5 --interval 3

# 2. 前3个快照: 保持怒喵软件关闭
# 3. 打开怒喵软件
# 4. 后2个快照: 观察数据

# 脚本会自动对比第一个和最后一个快照
```

### 分析结果

监控到变化后，这表明：
- 怒喵软件发送了某个初始化命令
- 设备的报告数据从无效变为有效

**下一步**: 需要知道软件发送的具体命令 → 使用方法C

---

## 方法C: USB抓包（最可靠）

使用专业工具捕获怒喵软件与设备之间的实际通信。

### Windows 平台 - 使用 USBPcap + Wireshark

#### 1. 安装工具

- **USBPcap**: https://desowin.org/usbpcap/
- **Wireshark**: https://www.wireshark.org/

#### 2. 开始捕获

```
1. 打开 Wireshark
2. 选择 USBPcap 接口（对应你的USB总线）
3. 点击 "开始捕获"
4. 打开怒喵软件
5. 等待几秒
6. 停止捕获
```

#### 3. 过滤HID报告

在Wireshark过滤器中输入：

```
usb.bmRequestType == 0x21
```

这会显示所有 "SET_REPORT" (主机→设备) 的请求。

#### 4. 查找初始化命令

查找捕获中最早的几个数据包，特别是：
- **Report Type**: Feature (0x03)
- **Report ID**: 可能是 0x3F 或其他
- **Data**: 命令的实际字节

#### 5. 提取命令

假设你看到这样的数据包：

```
URB_FUNCTION_CLASS_INTERFACE (0x001b)
  bmRequestType: 0x21 (Host to Device, Class, Interface)
  bRequest: SET_REPORT (0x09)
  wValue: 0x03xx (Feature Report, Report ID = xx)
  wLength: 3
  Data: 3F 01 00
```

这意味着命令是: `3F 01 00`

#### 6. 测试命令

```bash
python probe_mouse_battery.py \
  --path "你的设备路径" \
  --send "3F 01 00" \
  --scan 0x3F \
  --feature-length 64
```

### Linux 平台 - 使用 usbmon

```bash
# 1. 加载 usbmon 模块
sudo modprobe usbmon

# 2. 找到USB总线号
lsusb | grep 3151:5007
# 输出: Bus 001 Device 005: ID 3151:5007

# 3. 使用 tcpdump 捕获
sudo tcpdump -i usbmon1 -w usb_capture.pcap

# 4. 打开怒喵软件

# 5. 停止捕获 (Ctrl+C)

# 6. 使用 Wireshark 分析 usb_capture.pcap
```

---

## 常见的初始化命令模式

基于HID设备的经验，初始化命令通常符合以下模式：

### 1. 简单唤醒命令
```
01 00 00        # 唤醒设备
02 00 00        # 复位
04 00 00        # 启用
```

### 2. 报告请求
```
3F 00 00        # 请求 Report 0x3F
3F 01 00        # 请求 Report 0x3F (扩展)
3F 01 01        # 启用持续报告
```

### 3. 模式切换
```
10 01 00        # 切换到模式1
11 01 00        # 启用功能模式
20 01 00        # 启用高级特性
```

### 4. HID++ 协议（如果是Logitech兼容）
```
10 00 00 00                    # Short message
11 00 1D 10 00 00 00           # Long message - Battery status
```

---

## 多命令序列

有些设备需要多个命令按顺序执行：

```bash
# 例如: 先唤醒，再请求电池
python probe_mouse_battery.py \
  --path "设备路径" \
  --send "01 00 00" \
  --send "3F 01 00" \
  --scan 0x3F \
  --feature-length 64
```

你的脚本支持多个 `--send` 参数，它们会按顺序执行。

---

## 调试技巧

### 1. 增加详细输出

```bash
python probe_mouse_battery.py \
  --path "设备路径" \
  --send "命令" \
  --scan 0x3F \
  --feature-length 64 \
  --tries 5          # 多次尝试
  --poll 1           # 持续监控
```

### 2. 扫描所有报告

```bash
python probe_mouse_battery.py \
  --path "设备路径" \
  --scan 0xFF        # 扫描所有 0x00-0xFF
  --feature-length 64
```

### 3. 测试不同的特征长度

```bash
# HID设备的特征长度通常是: 8, 16, 32, 64
python probe_mouse_battery.py \
  --path "设备路径" \
  --scan 0x3F \
  --feature-length 32   # 尝试不同的长度
```

---

## 示例工作流程

### 完整的命令发现流程

```bash
# 步骤1: 尝试自动测试
python test_init_commands.py

# 如果成功 → 跳到步骤4
# 如果失败 → 继续步骤2

# 步骤2: 监控设备变化
python capture_hid_traffic.py --mode monitor

# 打开怒喵软件，观察哪些Report变化了

# 步骤3: USB抓包
# 使用 USBPcap + Wireshark 捕获实际命令

# 步骤4: 验证命令
python probe_mouse_battery.py \
  --path "设备路径" \
  --send "发现的命令" \
  --scan 0x3F \
  --feature-length 64 \
  --poll 1

# 步骤5: 创建便捷脚本
# 见下方 "自动化脚本"
```

---

## 自动化脚本

找到正确命令后，创建一个便捷脚本：

### `get_battery.sh` (Linux/WSL)
```bash
#!/bin/bash
python probe_mouse_battery.py \
  --path "\\?\HID#VID_3151&PID_5007&MI_02#8&512c24e&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}" \
  --send "3F 01 00" \
  --scan 0x3F \
  --feature-length 64 \
  --tries 3 \
  --quiet-errors
```

### `get_battery.bat` (Windows)
```batch
@echo off
python probe_mouse_battery.py ^
  --path "\\?\HID#VID_3151&PID_5007&MI_02#8&512c24e&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}" ^
  --send "3F 01 00" ^
  --scan 0x3F ^
  --feature-length 64 ^
  --tries 3 ^
  --quiet-errors
```

### `monitor_battery.py` (持续监控)
```python
#!/usr/bin/env python3
import subprocess
import time
import re

DEVICE_PATH = r"\\?\HID#VID_3151&PID_5007&MI_02#8&512c24e&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"
INIT_COMMAND = "3F 01 00"

while True:
    result = subprocess.run([
        "python", "probe_mouse_battery.py",
        "--path", DEVICE_PATH,
        "--send", INIT_COMMAND,
        "--scan", "0x3F",
        "--feature-length", "64",
        "--quiet-errors"
    ], capture_output=True, text=True)

    # 解析电量
    match = re.search(r'byte3=(\d+)%', result.stdout)
    if match:
        battery = match.group(1)
        print(f"{time.strftime('%H:%M:%S')} - 电池: {battery}%")

    time.sleep(60)  # 每分钟检查一次
```

---

## 常见问题

### Q: 为什么监控脚本看到数据变化，但没有捕获到发送的命令？

A: 监控脚本只能读取设备的输出，无法捕获主机发送的命令。需要使用USBPcap来捕获双向通信。

### Q: USBPcap显示很多数据包，如何找到初始化命令？

A:
1. 按时间排序，查看最早的几个包
2. 过滤 `usb.bmRequestType == 0x21`（主机→设备）
3. 查找 `SET_REPORT` 类型的请求
4. 关注 Report ID 为 0x3F 或接近的值

### Q: 尝试了所有命令都不行？

A: 可能的原因：
1. 设备需要多个命令序列
2. 命令中包含动态数据（如校验和、时间戳）
3. 需要特定的USB接口（MI_00, MI_01 等）
4. 设备使用了加密或签名

### Q: 如何判断命令是否成功？

A: 观察 byte3 的值：
- 成功: byte3 在 1-100 范围内（电量百分比）
- 失败: byte3 为 0 或随机值

---

## 参考资源

- **HID规范**: https://www.usb.org/hid
- **USBPcap文档**: https://desowin.org/usbpcap/tour.html
- **Wireshark HID分析**: https://wiki.wireshark.org/USB
- **Python hidapi**: https://github.com/trezor/cython-hidapi

---

## 反馈与改进

如果你成功找到了初始化命令，欢迎分享！可以添加到 `test_init_commands.py` 中供其他用户参考。

```python
# 在 test_init_commands.py 中添加:
("怒喵鼠标 - 电池初始化", bytes([0x??])),
```
