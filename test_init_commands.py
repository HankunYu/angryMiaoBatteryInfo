#!/usr/bin/env python3
"""
测试不同的初始化命令以找出正确的设备唤醒序列
"""

import hid
import time
import sys

# 你的设备路径
DEVICE_PATH = b"\\\\?\\HID#VID_3151&PID_5007&MI_02#8&512c24e&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"

# 常见的HID初始化命令模式
INIT_COMMANDS = [
    # 格式: (描述, 命令字节)
    ("唤醒命令 - 0x01", bytes([0x01, 0x00, 0x00])),
    ("唤醒命令 - 0x02", bytes([0x02, 0x00, 0x00])),
    ("唤醒命令 - 0x04", bytes([0x04, 0x00, 0x00])),
    ("唤醒命令 - 0x05", bytes([0x05, 0x00, 0x00])),
    ("唤醒命令 - 0x06", bytes([0x06, 0x00, 0x00])),

    # 电池报告请求
    ("电池报告请求 - Report 0x3F", bytes([0x3F, 0x00, 0x00])),
    ("电池报告请求 - Report 0x3F (扩展)", bytes([0x3F, 0x01, 0x00])),

    # 设备模式切换
    ("模式切换 - 0x10", bytes([0x10, 0x01, 0x00])),
    ("模式切换 - 0x11", bytes([0x11, 0x01, 0x00])),

    # 特征启用
    ("启用特征 - 0x20", bytes([0x20, 0x01, 0x00])),
    ("启用特征 - 0x21", bytes([0x21, 0x01, 0x00])),

    # HID++协议常见命令 (Logitech风格)
    ("HID++ Short - Get Register", bytes([0x10, 0x00, 0x00, 0x00])),
    ("HID++ Long - Get Battery", bytes([0x11, 0x00, 0x1D, 0x10, 0x00, 0x00, 0x00])),
]


def format_bytes(data):
    """格式化字节为十六进制字符串"""
    return ' '.join(f"{b:02X}" for b in data)


def test_command(dev, description, command, target_report_id=0x3F, feature_length=64):
    """
    测试单个初始化命令

    Args:
        dev: HID设备对象
        description: 命令描述
        command: 要发送的命令字节
        target_report_id: 目标报告ID
        feature_length: 特征报告长度

    Returns:
        bool: 是否成功获取有效数据
    """
    print(f"\n{'='*60}")
    print(f"测试: {description}")
    print(f"命令: {format_bytes(command)}")
    print(f"{'='*60}")

    try:
        # 发送初始化命令
        written = dev.send_feature_report(command)
        print(f"✓ 已发送 {written} 字节")

        # 等待设备处理
        time.sleep(0.1)

        # 尝试读取目标报告
        print(f"\n尝试读取 Report 0x{target_report_id:02X}...")

        for attempt in range(3):
            try:
                data = dev.get_feature_report(target_report_id, feature_length + 1)

                if data and len(data) > 1:
                    report_id = data[0]
                    payload = data[1:]

                    print(f"\n✓ 成功! 尝试 {attempt + 1}:")
                    print(f"  Report ID: 0x{report_id:02X}")
                    print(f"  Payload ({len(payload)}B): {format_bytes(payload)}")

                    # 检查 byte3 是否像电量值
                    if len(payload) >= 4:
                        battery_level = payload[3]
                        print(f"  >>> byte3 = {battery_level} (可能的电量: {battery_level}%)")

                        # 如果byte3在合理的电量范围内，认为成功
                        if 0 < battery_level <= 100:
                            print(f"\n🎉 找到有效命令! 电量: {battery_level}%")
                            return True

            except OSError as e:
                print(f"  尝试 {attempt + 1} 失败: {e}")

            time.sleep(0.05)

        print(f"\n✗ 未获取到有效数据")
        return False

    except Exception as e:
        print(f"✗ 命令发送失败: {e}")
        return False


def main():
    print("="*60)
    print("HID设备初始化命令测试工具")
    print("="*60)

    # 打开设备
    print(f"\n打开设备: {DEVICE_PATH.decode('utf-8', errors='replace')}")
    dev = hid.device()

    try:
        dev.open_path(DEVICE_PATH)
        print("✓ 设备已打开")

        # 获取设备信息
        manufacturer = dev.get_manufacturer_string() or "Unknown"
        product = dev.get_product_string() or "Unknown"
        print(f"  制造商: {manufacturer}")
        print(f"  产品: {product}")

        successful_commands = []

        # 测试所有命令
        for description, command in INIT_COMMANDS:
            if test_command(dev, description, command):
                successful_commands.append((description, command))

            # 短暂延迟
            time.sleep(0.2)

        # 总结
        print("\n" + "="*60)
        print("测试完成!")
        print("="*60)

        if successful_commands:
            print(f"\n✓ 找到 {len(successful_commands)} 个有效命令:\n")
            for desc, cmd in successful_commands:
                print(f"  - {desc}")
                print(f"    命令: {format_bytes(cmd)}")
                print(f"    使用方法: --send \"{format_bytes(cmd)}\"")
                print()
        else:
            print("\n✗ 未找到有效的初始化命令")
            print("\n建议:")
            print("1. 使用 USBPcap + Wireshark 抓包分析怒喵软件的通信")
            print("2. 查看官方软件的日志或调试输出")
            print("3. 联系设备制造商获取技术文档")

    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)
    finally:
        dev.close()
        print("\n设备已关闭")


if __name__ == "__main__":
    main()
