"""
监控和指标收集系统
支持Prometheus + Grafana集成
"""
import time
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
import os

logger = logging.getLogger(__name__)

@dataclass
class MetricPoint:
    """指标数据点"""
    name: str
    value: float
    labels: Dict[str, str]
    timestamp: datetime
    
class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self.metrics = defaultdict(deque)
        self.counters = defaultdict(float)
        self.gauges = defaultdict(float)
        self.histograms = defaultdict(list)
        self.timers = {}
        
        # 系统指标
        self.system_metrics = {
            'request_count': 0,
            'error_count': 0,
            'active_sessions': 0,
            'processing_files': 0,
            'db_connections': {
                'mysql': 0,
                'milvus': 0,
                'neo4j': 0
            }
        }
        
        # 性能指标
        self.performance_metrics = {
            'response_times': deque(maxlen=1000),
            'vector_search_times': deque(maxlen=1000),
            'graph_search_times': deque(maxlen=1000),
            'llm_call_times': deque(maxlen=1000),
            'file_processing_times': deque(maxlen=100)
        }
        
        # 错误指标
        self.error_metrics = {
            'milvus_errors': deque(maxlen=100),
            'neo4j_errors': deque(maxlen=100),
            'mysql_errors': deque(maxlen=100),
            'llm_errors': deque(maxlen=100),
            'processing_errors': deque(maxlen=100)
        }
        
        self._lock = threading.Lock()
        logger.info("指标收集器初始化完成")
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Dict[str, str] = None):
        """增加计数器"""
        with self._lock:
            key = self._make_key(name, labels)
            self.counters[key] += value
            self._add_metric_point(name, value, labels or {})
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """设置仪表值"""
        with self._lock:
            key = self._make_key(name, labels)
            self.gauges[key] = value
            self._add_metric_point(name, value, labels or {})
    
    def record_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """记录直方图值"""
        with self._lock:
            key = self._make_key(name, labels)
            self.histograms[key].append(value)
            # 保持最近1000个值
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]
            self._add_metric_point(name, value, labels or {})
    
    def start_timer(self, name: str) -> str:
        """开始计时"""
        timer_id = f"{name}_{time.time()}"
        self.timers[timer_id] = time.time()
        return timer_id
    
    def end_timer(self, timer_id: str, labels: Dict[str, str] = None) -> float:
        """结束计时"""
        if timer_id not in self.timers:
            return 0.0
        
        start_time = self.timers.pop(timer_id)
        duration = time.time() - start_time
        
        # 提取指标名称
        name = timer_id.split('_')[0]
        self.record_histogram(f"{name}_duration", duration, labels)
        
        return duration
    
    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """创建指标键"""
        if not labels:
            return name
        
        label_str = ','.join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def _add_metric_point(self, name: str, value: float, labels: Dict[str, str]):
        """添加指标点"""
        point = MetricPoint(
            name=name,
            value=value,
            labels=labels,
            timestamp=datetime.now()
        )
        
        self.metrics[name].append(point)
        # 保持最近1000个点
        if len(self.metrics[name]) > 1000:
            self.metrics[name].popleft()
    
    def get_metrics_summary(self, time_window: int = 300) -> Dict[str, Any]:
        """获取指标摘要（最近N秒）"""
        cutoff_time = datetime.now() - timedelta(seconds=time_window)
        summary = {}
        
        with self._lock:
            # 计数器
            summary['counters'] = dict(self.counters)
            
            # 仪表
            summary['gauges'] = dict(self.gauges)
            
            # 直方图统计
            summary['histograms'] = {}
            for key, values in self.histograms.items():
                if values:
                    summary['histograms'][key] = {
                        'count': len(values),
                        'avg': sum(values) / len(values),
                        'min': min(values),
                        'max': max(values),
                        'p50': self._percentile(values, 50),
                        'p90': self._percentile(values, 90),
                        'p95': self._percentile(values, 95),
                        'p99': self._percentile(values, 99)
                    }
            
            # 时间序列指标
            summary['timeseries'] = {}
            for name, points in self.metrics.items():
                recent_points = [p for p in points if p.timestamp >= cutoff_time]
                if recent_points:
                    summary['timeseries'][name] = {
                        'count': len(recent_points),
                        'latest_value': recent_points[-1].value,
                        'avg_value': sum(p.value for p in recent_points) / len(recent_points)
                    }
        
        return summary
    
    def _percentile(self, values: List[float], percentile: int) -> float:
        """计算百分位数"""
        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * percentile / 100
        f = int(k)
        c = k - f
        
        if f == len(sorted_values) - 1:
            return sorted_values[f]
        else:
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c
    
    def export_prometheus_format(self) -> str:
        """导出Prometheus格式"""
        lines = []
        
        with self._lock:
            # 计数器
            for key, value in self.counters.items():
                lines.append(f"# TYPE {key.split('{')[0]} counter")
                lines.append(f"{key} {value}")
            
            # 仪表
            for key, value in self.gauges.items():
                lines.append(f"# TYPE {key.split('{')[0]} gauge")
                lines.append(f"{key} {value}")
            
            # 直方图
            for key, values in self.histograms.items():
                if values:
                    base_name = key.split('{')[0]
                    labels_part = key[len(base_name):]
                    
                    # 总计数
                    lines.append(f"# TYPE {base_name} histogram")
                    lines.append(f"{base_name}_count{labels_part} {len(values)}")
                    
                    # 总和
                    lines.append(f"{base_name}_sum{labels_part} {sum(values)}")
                    
                    # 分位数桶
                    for percentile in [0.5, 0.9, 0.95, 0.99]:
                        p_value = self._percentile(values, int(percentile * 100))
                        lines.append(f"{base_name}_bucket{{le=\"{percentile}\"{labels_part[1:] if labels_part else ''}}} {p_value}")
        
        return '\n'.join(lines)

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
        self.active_requests = {}
        self._lock = threading.Lock()
    
    def start_request(self, request_id: str, request_type: str = "unknown"):
        """开始请求监控"""
        with self._lock:
            self.active_requests[request_id] = {
                'type': request_type,
                'start_time': time.time(),
                'timer_id': self.collector.start_timer('request_duration')
            }
            
            self.collector.increment_counter('requests_total', labels={'type': request_type})
            self.collector.set_gauge('active_requests', len(self.active_requests))
    
    def end_request(self, request_id: str, success: bool = True, error_type: str = None):
        """结束请求监控"""
        with self._lock:
            if request_id not in self.active_requests:
                return
            
            req_info = self.active_requests.pop(request_id)
            duration = self.collector.end_timer(req_info['timer_id'], 
                                               labels={'type': req_info['type']})
            
            if success:
                self.collector.increment_counter('requests_success', 
                                                labels={'type': req_info['type']})
            else:
                self.collector.increment_counter('requests_error', 
                                                labels={'type': req_info['type'], 'error': error_type or 'unknown'})
            
            self.collector.set_gauge('active_requests', len(self.active_requests))
            self.collector.record_histogram('request_duration_seconds', duration,
                                          labels={'type': req_info['type']})

class DatabaseMonitor:
    """数据库监控器"""
    
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
    
    def record_query(self, db_type: str, operation: str, duration: float, success: bool = True):
        """记录数据库查询"""
        labels = {'db': db_type, 'operation': operation}
        
        self.collector.increment_counter('db_queries_total', labels=labels)
        self.collector.record_histogram('db_query_duration_seconds', duration, labels=labels)
        
        if success:
            self.collector.increment_counter('db_queries_success', labels=labels)
        else:
            self.collector.increment_counter('db_queries_error', labels=labels)
    
    def record_connection_status(self, db_type: str, active_connections: int):
        """记录连接状态"""
        self.collector.set_gauge('db_connections_active', active_connections, 
                                labels={'db': db_type})

class AlertManager:
    """告警管理器"""
    
    def __init__(self, collector: MetricsCollector):
        self.collector = collector
        self.alert_rules = []
        self.alert_history = deque(maxlen=1000)
        self.notification_handlers = []
    
    def add_alert_rule(self, name: str, condition: callable, severity: str = "warning"):
        """添加告警规则"""
        self.alert_rules.append({
            'name': name,
            'condition': condition,
            'severity': severity
        })
    
    def add_notification_handler(self, handler: callable):
        """添加通知处理器"""
        self.notification_handlers.append(handler)
    
    def check_alerts(self):
        """检查告警"""
        current_metrics = self.collector.get_metrics_summary()
        
        for rule in self.alert_rules:
            try:
                if rule['condition'](current_metrics):
                    alert = {
                        'name': rule['name'],
                        'severity': rule['severity'],
                        'timestamp': datetime.now(),
                        'metrics': current_metrics
                    }
                    
                    self.alert_history.append(alert)
                    
                    # 发送通知
                    for handler in self.notification_handlers:
                        try:
                            handler(alert)
                        except Exception as e:
                            logger.error(f"通知处理器错误: {e}")
            
            except Exception as e:
                logger.error(f"告警规则检查错误 {rule['name']}: {e}")

# 全局监控实例
metrics_collector = MetricsCollector()
performance_monitor = PerformanceMonitor(metrics_collector)
db_monitor = DatabaseMonitor(metrics_collector)
alert_manager = AlertManager(metrics_collector)

# 设置默认告警规则
def setup_default_alerts():
    """设置默认告警规则"""
    
    # 响应时间过长
    alert_manager.add_alert_rule(
        "高响应时间",
        lambda m: m.get('histograms', {}).get('request_duration', {}).get('p95', 0) > 10.0,
        "warning"
    )
    
    # 错误率过高
    alert_manager.add_alert_rule(
        "高错误率",
        lambda m: (m.get('counters', {}).get('requests_error', 0) / 
                  max(m.get('counters', {}).get('requests_total', 1), 1)) > 0.1,
        "critical"
    )
    
    # 数据库连接异常
    alert_manager.add_alert_rule(
        "数据库连接失败",
        lambda m: m.get('counters', {}).get('db_queries_error', 0) > 10,
        "critical"
    )

# 日志通知处理器
def log_alert_handler(alert: Dict[str, Any]):
    """日志告警处理器"""
    logger.warning(f"🚨 告警: {alert['name']} - {alert['severity']} - {alert['timestamp']}")

# 便捷装饰器
def monitor_function(func_name: str = None, db_type: str = None):
    """监控函数装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            name = func_name or func.__name__
            timer_id = metrics_collector.start_timer(name)
            
            try:
                result = func(*args, **kwargs)
                
                if db_type:
                    duration = metrics_collector.end_timer(timer_id, labels={'db': db_type})
                    db_monitor.record_query(db_type, name, duration, success=True)
                else:
                    metrics_collector.end_timer(timer_id)
                    metrics_collector.increment_counter(f'{name}_success')
                
                return result
                
            except Exception as e:
                if db_type:
                    duration = metrics_collector.end_timer(timer_id, labels={'db': db_type})
                    db_monitor.record_query(db_type, name, duration, success=False)
                else:
                    metrics_collector.end_timer(timer_id)
                    metrics_collector.increment_counter(f'{name}_error')
                
                raise
        
        return wrapper
    return decorator

# 初始化监控
def init_monitoring():
    """初始化监控系统"""
    setup_default_alerts()
    alert_manager.add_notification_handler(log_alert_handler)
    logger.info("监控系统初始化完成")

# HTTP端点支持（用于Prometheus抓取）
def get_metrics_endpoint() -> str:
    """获取Prometheus格式的指标"""
    return metrics_collector.export_prometheus_format()

def get_health_status() -> Dict[str, Any]:
    """获取健康状态"""
    metrics = metrics_collector.get_metrics_summary()
    
    # 简单的健康检查逻辑
    error_rate = (metrics.get('counters', {}).get('requests_error', 0) / 
                 max(metrics.get('counters', {}).get('requests_total', 1), 1))
    
    avg_response_time = metrics.get('histograms', {}).get('request_duration', {}).get('avg', 0)
    
    status = "healthy"
    if error_rate > 0.2:
        status = "unhealthy"
    elif error_rate > 0.1 or avg_response_time > 5.0:
        status = "degraded"
    
    return {
        "status": status,
        "error_rate": error_rate,
        "avg_response_time": avg_response_time,
        "active_requests": metrics.get('gauges', {}).get('active_requests', 0),
        "timestamp": datetime.now().isoformat()
    }