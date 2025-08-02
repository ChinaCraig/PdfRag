"""
PDF智能文件管理系统主应用
"""
import os
import logging
import mimetypes
from flask import Flask, render_template, send_from_directory, request
from flask_cors import CORS

from utils.config_loader import config_loader
from utils.environment_checker import environment_checker
from app.routes.FileRoutes import file_bp
from app.routes.SearchRoutes import search_bp

# 配置日志
def setup_logging():
    """设置日志配置"""
    app_config = config_loader.get_app_config()
    log_config = app_config.get("logging", {})
    dev_config = app_config.get("development", {})
    
    # 基础日志级别
    base_level = log_config.get("level", "INFO").upper()
    
    # 如果启用了详细日志，将级别设为DEBUG
    if dev_config.get("verbose_logging", False):
        log_level = logging.DEBUG
        print("🔍 详细日志已启用 (DEBUG级别)")
    else:
        log_level = getattr(logging, base_level)
    
    log_format = log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log_file = log_config.get("file", "logs/app.log")
    
    # 确保日志目录存在
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 强制重新配置日志 - 解决第三方包覆盖问题
    root_logger = logging.getLogger()
    
    # 清除现有的handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 设置日志级别
    root_logger.setLevel(log_level)
    
    # 创建formatter
    formatter = logging.Formatter(log_format)
    
    # 添加文件handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 添加控制台handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    print(f"✅ 日志配置完成 - 级别: {logging.getLevelName(log_level)}, 文件: {log_file}")
    
    # 测试日志输出
    test_logger = logging.getLogger("app.setup")
    test_logger.info("🚀 日志系统初始化完成")

def create_app():
    """创建Flask应用"""
    # 设置静态文件和模板目录
    app = Flask(__name__, 
                static_folder='templates', 
                static_url_path='/static',
                template_folder='templates/html')
    
    # 加载配置
    app_config = config_loader.get_app_config()
    
    # 应用配置
    app.config.update({
        'DEBUG': app_config.get("debug", False),
        'SECRET_KEY': os.environ.get('SECRET_KEY', 'pdf-rag-secret-key-2024'),
        'MAX_CONTENT_LENGTH': app_config["upload"]["max_file_size"] * 1024 * 1024,  # MB to bytes
        'UPLOAD_FOLDER': app_config["upload"]["upload_dir"]
    })
    
    # 启用CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # 注册蓝图
    app.register_blueprint(file_bp)
    app.register_blueprint(search_bp)
    
    # 首页路由
    @app.route('/')
    def index():
        """首页"""
        return render_template('index.html')
    
    # Flask内置静态文件支持会自动处理 /static/ 路由
    
    # 健康检查
    @app.route('/health')
    def health_check():
        """系统健康检查"""
        try:
            from utils.monitoring import get_health_status
            return get_health_status(), 200
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "pdf-rag-system",
                "error": str(e)
            }, 500
    
    # Prometheus指标端点
    @app.route('/metrics')
    def metrics_endpoint():
        """Prometheus指标收集端点"""
        try:
            from utils.monitoring import get_metrics_endpoint
            from flask import Response
            
            metrics_data = get_metrics_endpoint()
            return Response(metrics_data, mimetype='text/plain')
        except Exception as e:
            logger.error(f"指标收集失败: {e}")
            return "# 指标收集失败\n", 500
    
    # 系统状态监控
    @app.route('/api/system/status')
    def system_status():
        """获取系统运行状态"""
        try:
            from utils.monitoring import metrics_collector
            metrics = metrics_collector.get_metrics_summary()
            
            return {
                "success": True,
                "data": {
                    "uptime": "运行中",
                    "active_requests": metrics.get('gauges', {}).get('active_requests', 0),
                    "total_requests": metrics.get('counters', {}).get('requests_total', 0),
                    "error_count": metrics.get('counters', {}).get('requests_error', 0),
                    "avg_response_time": metrics.get('histograms', {}).get('request_duration', {}).get('avg', 0),
                    "system_load": "正常"
                }
            }, 200
        except Exception as e:
            return {
                "success": False,
                "message": f"获取系统状态失败: {str(e)}"
            }, 500
    
    # 错误处理
    @app.errorhandler(404)
    def not_found(error):
        """404错误处理"""
        # 只对HTML页面请求返回主页，静态文件请求返回404
        if request.path.startswith('/static/'):
            return "Static file not found", 404
        return render_template('index.html')
    
    @app.errorhandler(413)
    def too_large(error):
        """文件过大错误处理"""
        return {
            "success": False,
            "message": "文件大小超过限制"
        }, 413
    
    @app.errorhandler(500)
    def internal_error(error):
        """500错误处理"""
        logging.error(f"服务器内部错误: {error}")
        return {
            "success": False,
            "message": "服务器内部错误"
        }, 500
    
    return app

def main():
    """主函数"""
    # 检查是否为Flask reloader进程
    is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    
    if not is_reloader:
        print("=" * 60)
        print("PDF智能文件管理系统")
        print("基于GraphRAG的智能文档检索系统 - 重构版")
        print("=" * 60)
    
    # 设置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # 只在主进程中执行环境检查（避免Flask reloader重复检查）
        if not is_reloader:
            # GraphRAG环境检查
            logger.info("开始GraphRAG系统环境检查...")
            all_passed = environment_checker.check_all()
            
            # 输出检查报告
            report = environment_checker.generate_report()
            print(report)
            
            if not all_passed:
                logger.error("环境检查失败，请修复后重新启动")
                return False
            
            # 输出启动建议
            startup_recommendations = environment_checker.get_startup_recommendations()
            if startup_recommendations:
                print("\n💡 系统启动建议:")
                for rec in startup_recommendations:
                    print(f"  - {rec}")
            
            # 可选：预加载模型（仅在非debug模式或显式启用时）
            app_config = config_loader.get_app_config()
            dev_config = app_config.get("development", {})
            debug_mode = app_config.get("app", {}).get("debug", False)
            dev_safe_mode = dev_config.get("dev_mode_safe", False)
            preload_enabled = dev_config.get("preload_models", False)
            
            # 开发安全模式：即使preload_models=true，也在特定条件下禁用
            if dev_safe_mode and debug_mode:
                logger.warning("🛡️ 开发安全模式：检测到debug模式，自动禁用模型预加载")
                preload_enabled = False
            
            # 如果是debug模式但未启用安全模式，警告用户预加载风险
            if debug_mode and preload_enabled and not dev_safe_mode:
                logger.warning("⚠️ Debug模式下的模型预加载可能导致进程冲突")
                logger.warning("⚠️ 建议: 启用dev_mode_safe或关闭debug模式")
                logger.warning("⚠️ 现在强制禁用预加载以避免冲突")
                preload_enabled = False  # 强制禁用
            
            if preload_enabled:
                logger.info("⏳ 模型预加载功能已简化，模型将在首次使用时自动加载")
                print("⏳ 模型预加载功能已简化，模型将在首次使用时自动加载")
            else:
                logger.info("⏳ 模型将在首次使用时自动下载")
                if debug_mode:
                    logger.info("🔧 Debug模式下已禁用预加载，避免进程冲突")
                if dev_safe_mode:
                    logger.info("🛡️ 开发安全模式已启用")
        
        else:
            logger.info("Flask reloader进程启动，跳过环境检查")
        
        # 创建Flask应用
        app = create_app()
        
        # 获取启动配置
        app_config = config_loader.get_app_config()["app"]
        host = app_config.get("host", "0.0.0.0")
        port = app_config.get("port", 5000)
        debug = app_config.get("debug", False)
        
        # 只在主进程输出启动信息
        if not is_reloader:
            logger.info(f"启动服务器: http://{host}:{port}")
            print(f"\n🚀 GraphRAG系统启动成功!")
            print(f"📖 访问地址: http://{host}:{port}")
            print(f"📁 文件管理: http://{host}:{port}/#file-management")
            print(f"🔍 智能检索: http://{host}:{port}/#smart-search")
            print(f"❓ 使用帮助: 点击页面右上角的帮助按钮")
            print(f"🤖 支持文字、表格、图片、图表的智能解析")
            print(f"🧠 基于768维向量和知识图谱的检索")
            print("\n按 Ctrl+C 停止服务器")
            print("=" * 60)
        
        # 启动应用
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭服务...")
        
        # 清理资源
        if not is_reloader:
            try:
                logger.info("正在清理资源...")
                # 模型管理器已简化，无需额外清理
                logger.info("资源清理完成")
            except Exception as e:
                logger.warning(f"资源清理时出现错误: {e}")
        
        print("\n👋 服务器已停止")
        return True
        
    except Exception as e:
        logger.error(f"服务器启动失败: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 