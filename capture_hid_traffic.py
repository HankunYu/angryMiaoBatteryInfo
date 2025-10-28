#!/usr/bin/env python3
"""
HID通信监控工具 - 用于捕获设备与应用之间的通信

注意: 这个脚本需要在怒喵软件运行的同时运行，
通过轮询设备来观察数据变化，间接推断发送了什么命令
"""

import hid
import time
import sys
from collections import defaultdict

# 你的设备路径
DEVICE_PATH = b"\\\\?\\HID#VID_3151&PID_5007&MI_02#8&512c24e&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"

# 要监控的报告ID列表
MONITOR_REPORTS = [
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
    0x10, 0x11, 0x20, 0x21, 0x30, 0x31,
    0x3F, 0x40, 0x41, 0x81, 0x90, 0x91
]

FEATURE_LENGTH = 64


def format_bytes(data):
    """格式化字节为十六进制字符串"""
    return ' '.join(f"{b:02X}" for b in data)


def monitor_device(poll_interval=0.5):
    """
    监控HID设备的报告变化

    Args:
        poll_interval: 轮询间隔（秒）
    """
    print("="*70)
    print("HID设备监控工具")
    print("="*70)
    print(f"\n设备: {DEVICE_PATH.decode('utf-8', errors='replace')}")
    print(f"监控的Report IDs: {[f'0x{rid:02X}' for rid in MONITOR_REPORTS]}")
    print(f"轮询间隔: {poll_interval} 秒")
    print("\n说明:")
    print("1. 启动此脚本")
    print("2. 打开怒喵软件")
    print("3. 观察数据变化，找出与电池相关的报告")
    print("\n按 Ctrl+C 停止监控")
    print("="*70)

    dev = hid.device()

    try:
        dev.open_path(DEVICE_PATH)
        print("\n✓ 设备已打开\n")

        # 存储上一次的数据，用于检测变化
        last_data = {}

        iteration = 0

        while True:
            iteration += 1
            print(f"\n[轮询 #{iteration}] {time.strftime('%H:%M:%S')}")
            print("-" * 70)

            changes_detected = False

            for report_id in MONITOR_REPORTS:
                try:
                    # 读取特征报告
                    data = dev.get_feature_report(report_id, FEATURE_LENGTH + 1)

                    if data and len(data) > 1:
                        payload = bytes(data[1:])

                        # 检查是否有变化
                        if report_id in last_data:
                            if payload != last_data[report_id]:
                                # 检测到变化
                                changes_detected = True
                                print(f"\n🔄 Report 0x{report_id:02X} 数据已改变!")
                                print(f"   旧: {format_bytes(last_data[report_id])}")
                                print(f"   新: {format_bytes(payload)}")

                                # 分析差异
                                old = last_data[report_id]
                                for i, (old_byte, new_byte) in enumerate(zip(old, payload)):
                                    if old_byte != new_byte:
                                        print(f"      byte[{i}]: 0x{old_byte:02X} → 0x{new_byte:02X} "
                                              f"({old_byte} → {new_byte})")
                        else:
                            # 首次获取
                            print(f"Report 0x{report_id:02X}: {format_bytes(payload)}")

                        # 更新存储
                        last_data[report_id] = payload

                except OSError:
                    # 报告不可用，跳过
                    pass

            if not changes_detected and iteration > 1:
                print("   (无变化)")

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\n\n监控已停止")
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)
    finally:
        dev.close()
        print("设备已关闭")


def capture_snapshots(num_snapshots=5, interval=2.0):
    """
    在不同状态下捕获设备快照

    使用方法:
    1. 运行此函数，关闭怒喵软件
    2. 捕获"未初始化"状态
    3. 打开怒喵软件
    4. 捕获"已初始化"状态
    5. 对比差异
    """
    print("="*70)
    print("HID设备快照工具")
    print("="*70)
    print(f"\n将捕获 {num_snapshots} 个快照，间隔 {interval} 秒")
    print("建议操作:")
    print("  - 前几个快照: 保持怒喵软件关闭")
    print("  - 然后: 打开怒喵软件")
    print("  - 后几个快照: 观察数据变化")
    print("\n按 Ctrl+C 提前停止")
    print("="*70)

    dev = hid.device()

    try:
        dev.open_path(DEVICE_PATH)
        print("\n✓ 设备已打开\n")

        snapshots = []

        for i in range(num_snapshots):
            countdown = interval
            while countdown > 0:
                print(f"\r快照 {i+1}/{num_snapshots} 将在 {countdown:.1f} 秒后捕获...", end='')
                time.sleep(0.1)
                countdown -= 0.1

            print(f"\r{'✓ 捕获快照 ' + str(i+1):<50}")

            snapshot = {}
            for report_id in MONITOR_REPORTS:
                try:
                    data = dev.get_feature_report(report_id, FEATURE_LENGTH + 1)
                    if data and len(data) > 1:
                        snapshot[report_id] = bytes(data[1:])
                except OSError:
                    pass

            snapshots.append({
                'time': time.strftime('%H:%M:%S'),
                'data': snapshot
            })

        # 分析快照
        print("\n" + "="*70)
        print("快照分析")
        print("="*70)

        for i, snap in enumerate(snapshots):
            print(f"\n快照 {i+1} ({snap['time']}):")
            for rid, payload in snap['data'].items():
                print(f"  Report 0x{rid:02X}: {format_bytes(payload)}")

        # 对比第一个和最后一个快照
        if len(snapshots) >= 2:
            print("\n" + "="*70)
            print("差异分析 (第一个 vs 最后一个快照)")
            print("="*70)

            first = snapshots[0]['data']
            last = snapshots[-1]['data']

            all_rids = set(first.keys()) | set(last.keys())

            for rid in sorted(all_rids):
                if rid in first and rid in last:
                    if first[rid] != last[rid]:
                        print(f"\nReport 0x{rid:02X} 已改变:")
                        print(f"  初始: {format_bytes(first[rid])}")
                        print(f"  最终: {format_bytes(last[rid])}")

                        # 字节级差异
                        for i, (old, new) in enumerate(zip(first[rid], last[rid])):
                            if old != new:
                                print(f"    byte[{i}]: 0x{old:02X} → 0x{new:02X}")
                elif rid in last and rid not in first:
                    print(f"\nReport 0x{rid:02X} 新出现:")
                    print(f"  数据: {format_bytes(last[rid])}")

    except KeyboardInterrupt:
        print("\n\n快照捕获已停止")
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)
    finally:
        dev.close()
        print("\n设备已关闭")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HID设备通信监控工具")
    parser.add_argument('--mode', choices=['monitor', 'snapshot'], default='monitor',
                        help='监控模式: monitor=持续监控, snapshot=快照对比')
    parser.add_argument('--interval', type=float, default=0.5,
                        help='轮询间隔(秒)')
    parser.add_argument('--snapshots', type=int, default=5,
                        help='快照模式下的快照数量')

    args = parser.parse_args()

    if args.mode == 'monitor':
        monitor_device(poll_interval=args.interval)
    else:
        capture_snapshots(num_snapshots=args.snapshots, interval=args.interval)
