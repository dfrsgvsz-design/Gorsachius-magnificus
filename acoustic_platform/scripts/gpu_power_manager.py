"""
GPU Power Manager — RTX 3080 长时间满负载训练功耗保护。

已知问题:
RTX 3080 10GB 在持续满负载下可能因瞬态功耗尖峰超出供电能力导致崩溃/重启。
部分型号使用 SP-CAP 电容而非 MLCC，对功耗瞬变更敏感。

解决方案:
1. 启动时将 GPU 功耗限制设为安全值 (默认 280W, TDP 320W 的 87.5%)
2. 周期性监控 GPU 温度、功耗、利用率
3. 温度过高时自动进一步降低功耗限制
4. 温度恢复后逐步恢复功耗限制
5. 训练结束时恢复原始功耗设置

依赖: pynvml (nvidia-ml-py3)
"""

import atexit
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Callable

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False


@dataclass
class GPUStatus:
    temperature: int = 0          # °C
    power_draw: float = 0.0       # W
    power_limit: float = 0.0      # W
    power_limit_default: float = 0.0  # W
    utilization_gpu: int = 0      # %
    utilization_mem: int = 0      # %
    memory_used: float = 0.0      # GB
    memory_total: float = 0.0     # GB
    fan_speed: int = 0            # %
    throttle_reasons: str = ""


class GPUPowerManager:
    """
    管理 GPU 功耗限制和温度监控，防止长时间满负载训练时崩溃。

    用法:
        mgr = GPUPowerManager(power_limit_watts=280)
        mgr.start()
        # ... 训练循环 ...
        mgr.stop()  # 或依赖 atexit 自动恢复
    """

    # RTX 3080 安全功耗阈值
    DEFAULT_POWER_LIMIT = 280       # W — 正常训练功耗上限
    THERMAL_THROTTLE_LIMIT = 250    # W — 高温时降至此值
    CRITICAL_THROTTLE_LIMIT = 220   # W — 临界温度时进一步降低

    # 温度阈值 (°C)
    TEMP_NORMAL = 75                # 正常运行温度上限
    TEMP_HIGH = 83                  # 高温警告，开始降功耗
    TEMP_CRITICAL = 88              # 临界温度，大幅降功耗

    # 监控间隔 (秒)
    MONITOR_INTERVAL = 30

    def __init__(self, gpu_index: int = 0,
                 power_limit_watts: Optional[float] = None,
                 temp_high: Optional[int] = None,
                 temp_critical: Optional[int] = None,
                 monitor_interval: int = 30,
                 log_fn: Optional[Callable] = None):
        """
        Args:
            gpu_index: GPU 设备索引
            power_limit_watts: 初始功耗限制 (W), None 则使用 DEFAULT_POWER_LIMIT
            temp_high: 高温阈值 (°C), None 则使用 TEMP_HIGH
            temp_critical: 临界温度阈值 (°C), None 则使用 TEMP_CRITICAL
            monitor_interval: 监控轮询间隔 (秒)
            log_fn: 日志回调函数, None 则使用 print
        """
        self.gpu_index = gpu_index
        self.target_power_limit = power_limit_watts or self.DEFAULT_POWER_LIMIT
        self.temp_high = temp_high or self.TEMP_HIGH
        self.temp_critical = temp_critical or self.TEMP_CRITICAL
        self.monitor_interval = monitor_interval
        self.log_fn = log_fn or print

        self._handle = None
        self._original_power_limit = None
        self._current_power_limit = None
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._initialized = False
        self._throttle_state = "normal"  # normal / high / critical

    def start(self) -> bool:
        """初始化 NVML 并设置功耗限制。返回是否成功。"""
        if not PYNVML_AVAILABLE:
            self.log_fn("[GPU Power] pynvml 不可用，跳过功耗管理。"
                        "安装: pip install nvidia-ml-py3")
            return False

        try:
            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(self.gpu_index)
            self._initialized = True

            # 读取原始功耗限制
            self._original_power_limit = (
                pynvml.nvmlDeviceGetPowerManagementLimit(self._handle) / 1000.0
            )

            # 读取允许的功耗范围
            min_limit, max_limit = pynvml.nvmlDeviceGetPowerManagementLimitConstraints(
                self._handle
            )
            min_w, max_w = min_limit / 1000.0, max_limit / 1000.0

            # 确保目标功耗在允许范围内
            safe_limit = max(min_w, min(self.target_power_limit, max_w))

            name = pynvml.nvmlDeviceGetName(self._handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            self.log_fn(f"[GPU Power] {name}")
            self.log_fn(f"[GPU Power] 原始功耗限制: {self._original_power_limit:.0f}W")
            self.log_fn(f"[GPU Power] 允许范围: {min_w:.0f}W ~ {max_w:.0f}W")

            # 设置功耗限制
            pynvml.nvmlDeviceSetPowerManagementLimit(
                self._handle, int(safe_limit * 1000)
            )
            self._current_power_limit = safe_limit
            self.log_fn(f"[GPU Power] 已设置功耗限制: {safe_limit:.0f}W "
                        f"(原始 {self._original_power_limit:.0f}W 的 "
                        f"{safe_limit/self._original_power_limit*100:.0f}%)")

            # 注册退出时恢复
            atexit.register(self._restore_power_limit)

            # 启动监控线程
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True, name="gpu-power-monitor"
            )
            self._monitor_thread.start()
            self.log_fn(f"[GPU Power] 温度监控已启动 (间隔 {self.monitor_interval}s, "
                        f"高温 {self.temp_high}°C, 临界 {self.temp_critical}°C)")

            return True

        except pynvml.NVMLError as e:
            self.log_fn(f"[GPU Power] NVML 错误: {e}")
            self.log_fn("[GPU Power] 功耗管理不可用 (可能需要管理员权限)")
            return False

    def stop(self):
        """停止监控并恢复原始功耗设置。"""
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        self._restore_power_limit()

    def get_status(self) -> Optional[GPUStatus]:
        """获取当前 GPU 状态。"""
        if not self._initialized:
            return None
        try:
            temp = pynvml.nvmlDeviceGetTemperature(
                self._handle, pynvml.NVML_TEMPERATURE_GPU
            )
            power = pynvml.nvmlDeviceGetPowerUsage(self._handle) / 1000.0
            limit = pynvml.nvmlDeviceGetPowerManagementLimit(self._handle) / 1000.0
            default_limit = pynvml.nvmlDeviceGetPowerManagementDefaultLimit(
                self._handle
            ) / 1000.0
            util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(self._handle)

            try:
                fan = pynvml.nvmlDeviceGetFanSpeed(self._handle)
            except pynvml.NVMLError:
                fan = -1

            # 检查节流原因
            throttle = ""
            try:
                reasons = pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(self._handle)
                parts = []
                if reasons & 0x0000000000000008:
                    parts.append("HW_Slowdown")
                if reasons & 0x0000000000000020:
                    parts.append("SW_Power")
                if reasons & 0x0000000000000040:
                    parts.append("SW_Thermal")
                if reasons & 0x0000000000000080:
                    parts.append("HW_Thermal")
                if reasons & 0x0000000000000100:
                    parts.append("HW_Power")
                throttle = ",".join(parts) if parts else "none"
            except pynvml.NVMLError:
                throttle = "unknown"

            return GPUStatus(
                temperature=temp,
                power_draw=power,
                power_limit=limit,
                power_limit_default=default_limit,
                utilization_gpu=util.gpu,
                utilization_mem=util.memory,
                memory_used=mem_info.used / 1e9,
                memory_total=mem_info.total / 1e9,
                fan_speed=fan,
                throttle_reasons=throttle,
            )
        except pynvml.NVMLError:
            return None

    def log_status(self):
        """打印当前 GPU 状态摘要。"""
        s = self.get_status()
        if not s:
            return
        self.log_fn(
            f"[GPU] {s.temperature}°C | {s.power_draw:.0f}W/{s.power_limit:.0f}W | "
            f"GPU {s.utilization_gpu}% | Mem {s.memory_used:.1f}/{s.memory_total:.1f}GB | "
            f"Fan {s.fan_speed}% | Throttle: {s.throttle_reasons} | "
            f"State: {self._throttle_state}"
        )

    def _set_power_limit(self, watts: float):
        """设置功耗限制 (内部方法)。"""
        if not self._initialized:
            return
        try:
            pynvml.nvmlDeviceSetPowerManagementLimit(
                self._handle, int(watts * 1000)
            )
            self._current_power_limit = watts
        except pynvml.NVMLError as e:
            self.log_fn(f"[GPU Power] 设置功耗限制失败: {e}")

    def _monitor_loop(self):
        """后台温度监控循环。"""
        log_counter = 0
        while not self._stop_event.is_set():
            status = self.get_status()
            if status:
                self._adjust_power(status)

                # 每 5 个周期打印一次完整状态
                log_counter += 1
                if log_counter % 5 == 0:
                    self.log_status()

            self._stop_event.wait(self.monitor_interval)

    def _adjust_power(self, status: GPUStatus):
        """根据温度动态调整功耗限制。"""
        temp = status.temperature
        prev_state = self._throttle_state

        if temp >= self.temp_critical:
            new_state = "critical"
            new_limit = self.CRITICAL_THROTTLE_LIMIT
        elif temp >= self.temp_high:
            new_state = "high"
            new_limit = self.THERMAL_THROTTLE_LIMIT
        else:
            new_state = "normal"
            new_limit = self.target_power_limit

        if new_state != prev_state:
            self._throttle_state = new_state
            self._set_power_limit(new_limit)
            if new_state == "critical":
                self.log_fn(
                    f"[GPU Power] ⚠️ 临界温度 {temp}°C! 功耗降至 {new_limit}W"
                )
            elif new_state == "high":
                self.log_fn(
                    f"[GPU Power] ⚡ 高温 {temp}°C, 功耗降至 {new_limit}W"
                )
            elif prev_state != "normal":
                self.log_fn(
                    f"[GPU Power] ✓ 温度恢复 {temp}°C, 功耗恢复至 {new_limit}W"
                )

    def _restore_power_limit(self):
        """恢复原始功耗限制。"""
        if not self._initialized or self._original_power_limit is None:
            return
        try:
            pynvml.nvmlDeviceSetPowerManagementLimit(
                self._handle, int(self._original_power_limit * 1000)
            )
            self.log_fn(
                f"[GPU Power] 已恢复原始功耗限制: {self._original_power_limit:.0f}W"
            )
        except pynvml.NVMLError:
            pass
        try:
            pynvml.nvmlShutdown()
        except pynvml.NVMLError:
            pass
        self._initialized = False
