"""
文件管理路由
处理文件上传、删除、重命名等HTTP请求
"""
from flask import Blueprint, request, jsonify, render_template
import logging
from werkzeug.utils import secure_filename

from app.service.FileService import file_service

logger = logging.getLogger(__name__)

# 创建蓝图
file_bp = Blueprint('file', __name__, url_prefix='/api/file')

@file_bp.route('/upload', methods=['POST'])
def upload_file():
    """
    上传PDF文件
    """
    try:
        # 检查是否有文件
        if 'file' not in request.files:
            return jsonify({
                "success": False,
                "message": "没有选择文件"
            }), 400
        
        file = request.files['file']
        
        # 检查文件名
        if file.filename == '':
            return jsonify({
                "success": False,
                "message": "没有选择文件"
            }), 400
        
        # 安全的文件名处理 - 保留原始文件名用于类型检查
        original_filename = file.filename
        filename = secure_filename(original_filename)
        
        logger.info(f"文件上传请求 - 原始文件名: {original_filename}, 安全文件名: {filename}")
        
        # 如果secure_filename导致文件名为空或丢失扩展名，使用原始文件名进行检查
        check_filename = filename if filename and '.' in filename else original_filename
        
        # 调用服务层处理
        result = file_service.upload_file(file, check_filename, original_filename)
        
        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"文件上传路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@file_bp.route('/delete/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    """
    删除文件
    
    Args:
        file_id: 文件ID
    """
    try:
        result = file_service.delete_file(file_id)
        
        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"文件删除路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@file_bp.route('/rename/<file_id>', methods=['PUT'])
def rename_file(file_id):
    """
    重命名文件
    
    Args:
        file_id: 文件ID
    """
    try:
        data = request.get_json()
        
        if not data or 'new_filename' not in data:
            return jsonify({
                "success": False,
                "message": "缺少新文件名"
            }), 400
        
        new_filename = data['new_filename'].strip()
        
        if not new_filename:
            return jsonify({
                "success": False,
                "message": "文件名不能为空"
            }), 400
        
        result = file_service.rename_file(file_id, new_filename)
        
        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"文件重命名路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@file_bp.route('/list', methods=['GET'])
def get_file_list():
    """
    获取文件列表
    """
    try:
        files = file_service.get_file_list()
        
        return jsonify({
            "success": True,
            "files": files
        }), 200
        
    except Exception as e:
        logger.error(f"获取文件列表路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误",
            "files": []
        }), 500

@file_bp.route('/status/<file_id>', methods=['GET'])
def get_processing_status(file_id):
    """
    获取文件处理状态
    
    Args:
        file_id: 文件ID
    """
    try:
        status = file_service.get_processing_status(file_id)
        
        return jsonify({
            "success": True,
            "status": status
        }), 200
        
    except Exception as e:
        logger.error(f"获取处理状态路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@file_bp.route('/info/<file_id>', methods=['GET'])
def get_file_info(file_id):
    """
    获取文件详细信息
    
    Args:
        file_id: 文件ID
    """
    try:
        result = file_service.get_file_detailed_info(file_id)
        
        status_code = 200 if result["success"] else 404
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"获取文件信息路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

# 错误处理
@file_bp.errorhandler(413)
def too_large(e):
    """文件过大处理"""
    return jsonify({
        "success": False,
        "message": "文件大小超过限制"
    }), 413

@file_bp.errorhandler(400)
def bad_request(e):
    """错误请求处理"""
    return jsonify({
        "success": False,
        "message": "请求参数错误"
    }), 400

@file_bp.errorhandler(500)
def internal_error(e):
    """服务器内部错误处理"""
    return jsonify({
        "success": False,
        "message": "服务器内部错误"
    }), 500 