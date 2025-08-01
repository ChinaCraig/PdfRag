"""
智能检索路由
处理智能问答、搜索建议等HTTP请求
"""
from flask import Blueprint, request, jsonify, Response, stream_template
import logging
import json

from app.service.SearchService import search_service

logger = logging.getLogger(__name__)

# 创建蓝图
search_bp = Blueprint('search', __name__, url_prefix='/api/search')

@search_bp.route('/query', methods=['POST'])
def search_query():
    """
    智能检索查询（非流式）
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                "success": False,
                "message": "缺少查询内容"
            }), 400
        
        query = data['query'].strip()
        session_id = data.get('session_id')
        
        if not query:
            return jsonify({
                "success": False,
                "message": "查询内容不能为空"
            }), 400
        
        # 调用服务层处理
        result = search_service.search(query, session_id, stream=False)
        
        status_code = 200 if result.get("success", True) else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"智能检索查询路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@search_bp.route('/stream', methods=['POST'])
def search_stream():
    """
    智能检索查询（流式）
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                "success": False,
                "message": "缺少查询内容"
            }), 400
        
        query = data['query'].strip()
        session_id = data.get('session_id')
        
        if not query:
            return jsonify({
                "success": False,
                "message": "查询内容不能为空"
            }), 400
        
        def generate():
            """生成流式响应"""
            try:
                # 流式生成回答 - SearchService已经返回结构化的JSON数据
                for chunk in search_service.search(query, session_id, stream=True):
                    # chunk已经是JSON字符串，直接作为SSE data发送
                    yield f"data: {chunk}"
                
            except Exception as e:
                logger.error(f"流式生成错误: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': '生成失败'})}\n\n"
        
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
        
    except Exception as e:
        logger.error(f"智能检索流式路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@search_bp.route('/suggestions', methods=['POST'])
def get_suggestions():
    """
    获取搜索建议
    """
    try:
        data = request.get_json()
        
        query = data.get('query', '') if data else ''
        
        suggestions = search_service.get_search_suggestions(query)
        
        return jsonify({
            "success": True,
            "suggestions": suggestions
        }), 200
        
    except Exception as e:
        logger.error(f"获取搜索建议路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误",
            "suggestions": []
        }), 500

@search_bp.route('/history/<session_id>', methods=['GET'])
def get_conversation_history(session_id):
    """
    获取对话历史
    
    Args:
        session_id: 会话ID
    """
    try:
        history = search_service.get_conversation_history(session_id)
        
        return jsonify({
            "success": True,
            "history": history
        }), 200
        
    except Exception as e:
        logger.error(f"获取对话历史路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误",
            "history": []
        }), 500

@search_bp.route('/clear/<session_id>', methods=['DELETE'])
def clear_conversation(session_id):
    """
    清空对话历史
    
    Args:
        session_id: 会话ID
    """
    try:
        success = search_service.clear_conversation(session_id)
        
        return jsonify({
            "success": success,
            "message": "对话历史已清空" if success else "会话不存在"
        }), 200 if success else 404
        
    except Exception as e:
        logger.error(f"清空对话历史路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@search_bp.route('/session', methods=['POST'])
def create_session():
    """
    创建新的对话会话
    """
    try:
        # 创建新会话ID
        import uuid
        session_id = str(uuid.uuid4())
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "message": "会话创建成功"
        }), 200
        
    except Exception as e:
        logger.error(f"创建会话路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@search_bp.route('/enhanced', methods=['POST'])
def enhanced_search():
    """
    增强智能检索（带智能布局）
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                "success": False,
                "message": "缺少查询内容"
            }), 400
        
        query = data['query'].strip()
        session_id = data.get('session_id')
        
        if not query:
            return jsonify({
                "success": False,
                "message": "查询内容不能为空"
            }), 400
        
        # 调用增强搜索服务
        result = search_service.get_enhanced_answer_with_layout(query, session_id)
        
        status_code = 200 if result.get("success", True) else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"增强智能检索路由错误: {e}")
        return jsonify({
            "success": False,
            "message": "服务器内部错误"
        }), 500

@search_bp.route('/health', methods=['GET'])
def health_check():
    """
    健康检查
    """
    try:
        return jsonify({
            "success": True,
            "status": "healthy",
            "service": "search",
            "message": "搜索服务运行正常"
        }), 200
        
    except Exception as e:
        logger.error(f"搜索服务健康检查错误: {e}")
        return jsonify({
            "success": False,
            "status": "unhealthy",
            "service": "search",
            "message": "搜索服务异常"
        }), 500

# 错误处理
@search_bp.errorhandler(400)
def bad_request(e):
    """错误请求处理"""
    return jsonify({
        "success": False,
        "message": "请求参数错误"
    }), 400

@search_bp.errorhandler(404)
def not_found(e):
    """资源不存在处理"""
    return jsonify({
        "success": False,
        "message": "请求的资源不存在"
    }), 404

@search_bp.errorhandler(500)
def internal_error(e):
    """服务器内部错误处理"""
    return jsonify({
        "success": False,
        "message": "服务器内部错误"
    }), 500 