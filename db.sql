-- PDF智能文件管理系统数据库初始化脚本
-- 数据库: pdf_rag
-- 创建时间: 2024

-- 创建数据库
CREATE DATABASE IF NOT EXISTS pdf_rag DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 使用数据库
USE pdf_rag;

-- 删除已存在的表（如果需要重新创建）
-- DROP TABLE IF EXISTS file_chunks;
-- DROP TABLE IF EXISTS processing_logs;
-- DROP TABLE IF EXISTS files;

-- 1. 文件信息表
CREATE TABLE IF NOT EXISTS files (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    file_id VARCHAR(36) NOT NULL UNIQUE COMMENT '文件唯一标识符(UUID)',
    original_filename VARCHAR(255) NOT NULL COMMENT '原始文件名',
    filename VARCHAR(255) NOT NULL COMMENT '存储文件名',
    file_path VARCHAR(500) NOT NULL COMMENT '文件存储路径',
    file_size BIGINT NOT NULL COMMENT '文件大小(字节)',
    file_hash VARCHAR(64) COMMENT '文件MD5哈希值',
    upload_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    status ENUM('uploaded', 'processing', 'completed', 'failed') NOT NULL DEFAULT 'uploaded' COMMENT '处理状态',
    processing_progress INT DEFAULT 0 COMMENT '处理进度(0-100)',
    page_count INT DEFAULT 0 COMMENT 'PDF页数',
    total_chunks INT DEFAULT 0 COMMENT '总文本块数',
    total_images INT DEFAULT 0 COMMENT '总图像数',
    total_tables INT DEFAULT 0 COMMENT '总表格数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文件信息表';

-- 2. 文件内容块表
CREATE TABLE IF NOT EXISTS file_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    chunk_id VARCHAR(100) NOT NULL UNIQUE COMMENT '文本块唯一标识符',
    file_id VARCHAR(36) NOT NULL COMMENT '文件ID',
    content_type ENUM('text', 'image', 'table', 'chart') NOT NULL COMMENT '内容类型',
    content TEXT NOT NULL COMMENT '内容文本',
    page_number INT NOT NULL COMMENT '页码',
    chunk_index INT NOT NULL COMMENT '在页面中的块索引',
    start_position INT COMMENT '在原文中的起始位置',
    end_position INT COMMENT '在原文中的结束位置',
    bbox_x1 FLOAT COMMENT '边界框左上角X坐标',
    bbox_y1 FLOAT COMMENT '边界框左上角Y坐标',
    bbox_x2 FLOAT COMMENT '边界框右下角X坐标',
    bbox_y2 FLOAT COMMENT '边界框右下角Y坐标',
    metadata JSON COMMENT '额外元数据',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
    INDEX idx_file_id (file_id),
    INDEX idx_content_type (content_type),
    INDEX idx_page_number (page_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文件内容块表';

-- 3. 处理日志表
CREATE TABLE IF NOT EXISTS processing_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    file_id VARCHAR(36) NOT NULL COMMENT '文件ID',
    stage ENUM('upload', 'text_extraction', 'image_extraction', 'table_extraction', 'embedding', 'entity_extraction', 'graph_construction', 'completed', 'failed') NOT NULL COMMENT '处理阶段',
    status ENUM('started', 'processing', 'completed', 'failed') NOT NULL COMMENT '阶段状态',
    progress INT DEFAULT 0 COMMENT '阶段进度(0-100)',
    message TEXT COMMENT '处理消息或错误信息',
    start_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
    end_time DATETIME COMMENT '结束时间',
    processing_time INT COMMENT '处理耗时(秒)',
    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
    INDEX idx_file_id (file_id),
    INDEX idx_stage (stage),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='处理日志表';

-- 4. 实体表
CREATE TABLE IF NOT EXISTS entities (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    entity_id VARCHAR(36) NOT NULL UNIQUE COMMENT '实体唯一标识符',
    file_id VARCHAR(36) NOT NULL COMMENT '文件ID',
    entity_name VARCHAR(255) NOT NULL COMMENT '实体名称',
    entity_type VARCHAR(50) NOT NULL COMMENT '实体类型(PERSON, ORGANIZATION, LOCATION, etc.)',
    frequency INT DEFAULT 1 COMMENT '在文档中出现的频次',
    confidence FLOAT DEFAULT 1.0 COMMENT '识别置信度(0-1)',
    first_mention_chunk_id VARCHAR(100) COMMENT '首次提及的文本块ID',
    metadata JSON COMMENT '实体元数据',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
    INDEX idx_file_id (file_id),
    INDEX idx_entity_type (entity_type),
    INDEX idx_entity_name (entity_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='实体表';

-- 5. 关系表
CREATE TABLE IF NOT EXISTS relationships (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    relationship_id VARCHAR(36) NOT NULL UNIQUE COMMENT '关系唯一标识符',
    file_id VARCHAR(36) NOT NULL COMMENT '文件ID',
    subject_entity_id VARCHAR(36) NOT NULL COMMENT '主体实体ID',
    predicate VARCHAR(100) NOT NULL COMMENT '关系谓词',
    object_entity_id VARCHAR(36) NOT NULL COMMENT '客体实体ID',
    confidence FLOAT DEFAULT 1.0 COMMENT '关系置信度(0-1)',
    source_chunk_id VARCHAR(100) COMMENT '关系来源文本块ID',
    metadata JSON COMMENT '关系元数据',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (object_entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    INDEX idx_file_id (file_id),
    INDEX idx_subject_entity (subject_entity_id),
    INDEX idx_object_entity (object_entity_id),
    INDEX idx_predicate (predicate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='关系表';

-- 6. 会话表（用于存储用户对话会话）
CREATE TABLE IF NOT EXISTS sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    session_id VARCHAR(36) NOT NULL UNIQUE COMMENT '会话唯一标识符',
    user_id VARCHAR(36) COMMENT '用户ID（可为空，支持匿名会话）',
    title VARCHAR(255) COMMENT '会话标题',
    status ENUM('active', 'closed') NOT NULL DEFAULT 'active' COMMENT '会话状态',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话表';

-- 7. 对话记录表
CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    session_id VARCHAR(36) NOT NULL COMMENT '会话ID',
    message_id VARCHAR(36) NOT NULL UNIQUE COMMENT '消息唯一标识符',
    role ENUM('user', 'assistant') NOT NULL COMMENT '消息角色',
    content TEXT NOT NULL COMMENT '消息内容',
    metadata JSON COMMENT '消息元数据（如引用的文档等）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    INDEX idx_session_id (session_id),
    INDEX idx_role (role),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对话记录表';

-- 8. 系统配置表
CREATE TABLE IF NOT EXISTS system_config (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    config_key VARCHAR(100) NOT NULL UNIQUE COMMENT '配置键',
    config_value TEXT COMMENT '配置值',
    config_type ENUM('string', 'number', 'boolean', 'json') NOT NULL DEFAULT 'string' COMMENT '配置类型',
    description VARCHAR(255) COMMENT '配置描述',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统配置表';

-- 插入默认系统配置
INSERT INTO system_config (config_key, config_value, config_type, description) VALUES
('max_file_size_mb', '100', 'number', '最大文件上传大小(MB)'),
('allowed_file_types', '["pdf"]', 'json', '允许的文件类型'),
('chunk_size', '1000', 'number', '文本分块大小'),
('chunk_overlap', '200', 'number', '文本分块重叠大小'),
('vector_similarity_threshold', '0.7', 'number', '向量相似度阈值'),
('max_search_results', '10', 'number', '最大搜索结果数'),
('session_timeout_hours', '24', 'number', '会话超时时间(小时)');

-- 创建视图：文件处理统计
CREATE VIEW file_processing_stats AS
SELECT 
    DATE(created_at) as processing_date,
    COUNT(*) as total_files,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_files,
    SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing_files,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_files,
    AVG(file_size) as avg_file_size,
    SUM(total_chunks) as total_chunks,
    SUM(total_images) as total_images,
    SUM(total_tables) as total_tables
FROM files 
GROUP BY DATE(created_at)
ORDER BY processing_date DESC;

-- 创建视图：最近的对话会话
CREATE VIEW recent_conversations AS
SELECT 
    s.session_id,
    s.title,
    s.status,
    s.created_at as session_created,
    COUNT(c.id) as message_count,
    MAX(c.created_at) as last_message_time
FROM sessions s
LEFT JOIN conversations c ON s.session_id = c.session_id
GROUP BY s.session_id, s.title, s.status, s.created_at
ORDER BY last_message_time DESC;

-- 添加索引优化查询性能
CREATE INDEX idx_files_status_created ON files(status, created_at);
CREATE INDEX idx_chunks_file_page ON file_chunks(file_id, page_number);
CREATE INDEX idx_entities_name_type ON entities(entity_name, entity_type);
CREATE INDEX idx_conversations_session_created ON conversations(session_id, created_at);

-- 创建存储过程：清理过期会话
DELIMITER //
CREATE PROCEDURE CleanupExpiredSessions()
BEGIN
    DECLARE session_timeout_hours INT DEFAULT 24;
    
    -- 获取会话超时配置
    SELECT CAST(config_value AS UNSIGNED) INTO session_timeout_hours 
    FROM system_config 
    WHERE config_key = 'session_timeout_hours' 
    LIMIT 1;
    
    -- 删除过期会话的对话记录
    DELETE c FROM conversations c
    JOIN sessions s ON c.session_id = s.session_id
    WHERE s.updated_at < DATE_SUB(NOW(), INTERVAL session_timeout_hours HOUR)
    AND s.status = 'active';
    
    -- 关闭过期会话
    UPDATE sessions 
    SET status = 'closed' 
    WHERE updated_at < DATE_SUB(NOW(), INTERVAL session_timeout_hours HOUR)
    AND status = 'active';
    
    SELECT ROW_COUNT() as cleaned_sessions;
END //
DELIMITER ;

-- 创建触发器：自动更新文件统计信息
DELIMITER //
CREATE TRIGGER update_file_stats_after_chunk_insert
AFTER INSERT ON file_chunks
FOR EACH ROW
BEGIN
    UPDATE files 
    SET 
        total_chunks = (
            SELECT COUNT(*) 
            FROM file_chunks 
            WHERE file_id = NEW.file_id AND content_type = 'text'
        ),
        total_images = (
            SELECT COUNT(*) 
            FROM file_chunks 
            WHERE file_id = NEW.file_id AND content_type = 'image'
        ),
        total_tables = (
            SELECT COUNT(*) 
            FROM file_chunks 
            WHERE file_id = NEW.file_id AND content_type = 'table'
        )
    WHERE file_id = NEW.file_id;
END //
DELIMITER ;

-- 数据库初始化完成
-- 
-- 使用说明：
-- 1. 执行此脚本前，确保MySQL服务正在运行
-- 2. 确保有足够的权限创建数据库和表
-- 3. 建议定期执行 CALL CleanupExpiredSessions(); 清理过期会话
-- 4. 可以通过修改system_config表中的配置来调整系统参数
-- 
-- 表结构说明：
-- - files: 存储上传的PDF文件基本信息
-- - file_chunks: 存储从PDF中提取的文本块、图像、表格等内容
-- - processing_logs: 记录文件处理过程的详细日志
-- - entities: 存储从文档中提取的实体信息
-- - relationships: 存储实体之间的关系
-- - sessions: 存储用户对话会话
-- - conversations: 存储具体的对话消息
-- - system_config: 存储系统配置参数 