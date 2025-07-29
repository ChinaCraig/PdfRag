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
    log_config = config_loader.get_app_config().get("logging", {})
    
    log_level = getattr(logging, log_config.get("level", "INFO").upper())
    log_format = log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log_file = log_config.get("file", "logs/app.log")
    
    # 确保日志目录存在
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 配置日志
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

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
            return {
                "status": "healthy",
                "service": "pdf-rag-system",
                "version": "1.0.0",
                "message": "PDF智能文件管理系统运行正常"
            }, 200
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "pdf-rag-system",
                "error": str(e)
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
        print("基于GraphRAG的智能文档检索系统 - 硬件自适应版本")
        print("=" * 60)
    
    # 设置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # 只在主进程中执行环境检查（避免Flask reloader重复检查）
        if not is_reloader:
            # 环境检查（包含硬件检测）
            logger.info("开始环境检查...")
            all_passed, results = environment_checker.check_all()
            
            # 输出检查报告
            report = environment_checker.generate_report()
            print(report)
            
            if not all_passed:
                logger.error("环境检查失败，请修复后重新启动")
                return False
            
            # 初始化资源管理器
            logger.info("初始化资源管理器...")
            try:
                from utils.resource_manager import resource_manager
                from utils.model_manager import model_manager
                
                # 获取硬件信息
                hardware_info = environment_checker.hardware_info
                recommended_config = environment_checker.recommended_config
                
                # 初始化资源管理器
                resource_manager.initialize(hardware_info)
                
                # 应用硬件配置到模型管理器
                model_manager.apply_hardware_config(recommended_config)
                
                # 输出启动建议
                startup_recommendations = environment_checker.get_startup_recommendations()
                if startup_recommendations:
                    print("\n💡 系统启动建议:")
                    for rec in startup_recommendations:
                        print(f"  {rec}")
                
                logger.info("资源管理器初始化完成")
                
                # 可选：预加载模型（根据硬件性能决定）
                performance_score = hardware_info.get("performance_score", 50)
                if performance_score > 70 and recommended_config.get("preload_models", False):
                    logger.info("系统性能良好，开始预加载模型...")
                    try:
                        model_manager.preload_models(["embedding"])
                        logger.info("模型预加载完成")
                    except Exception as e:
                        logger.warning(f"模型预加载失败: {e}")
                
            except Exception as e:
                logger.error(f"资源管理器初始化失败: {e}")
                # 可以选择继续启动但不使用资源管理器
                logger.info("将使用传统模式启动")
                
        else:
            logger.info("Flask reloader进程启动，跳过环境检查和资源管理器初始化")
        
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
            print(f"\n🚀 服务器启动成功!")
            print(f"📖 访问地址: http://{host}:{port}")
            print(f"📁 文件管理: http://{host}:{port}/#file-management")
            print(f"🔍 智能检索: http://{host}:{port}/#smart-search")
            print(f"❓ 使用帮助: 点击页面右上角的帮助按钮")
            print(f"⚙️ 系统已启用硬件自适应优化")
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
                from utils.resource_manager import resource_manager
                from utils.model_manager import model_manager
                
                logger.info("正在清理资源...")
                resource_manager.shutdown()
                model_manager.cleanup()
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