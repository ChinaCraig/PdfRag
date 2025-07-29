# PDF智能文件管理系统

基于GraphRAG技术的PDF智能文档检索系统，支持PDF文件的智能解析、内容提取、向量检索和图谱检索。

## 🌟 主要特性

- **智能PDF解析**: 自动提取PDF中的文字、表格、图片、图表等内容
- **GraphRAG技术**: 结合向量检索和知识图谱检索，提供更准确的检索结果
- **多轮对话**: 支持连续对话，上下文理解
- **流式输出**: 实时显示AI分析过程
- **简约界面**: 类似ChatGPT的黑白配色，简洁易用
- **多模态支持**: 处理文字、表格、图片等多种内容类型

## 🏗️ 系统架构

```
PdfRAG/
├── app/                    # 应用核心代码
│   ├── routes/            # 路由处理
│   │   ├── FileRoutes.py  # 文件管理路由
│   │   └── SearchRoutes.py # 智能检索路由
│   └── service/           # 业务服务
│       ├── FileService.py  # 文件管理服务
│       └── SearchService.py # 智能检索服务
├── config/                # 配置文件
│   ├── db.yaml           # 数据库配置
│   ├── model.yaml        # 模型配置
│   ├── config.yaml       # 应用配置
│   └── prompt.yaml       # 提示词配置
├── templates/            # 前端文件
│   ├── html/            # HTML文件
│   ├── css/             # CSS样式
│   └── js/              # JavaScript文件
├── utils/               # 工具类
│   ├── config_loader.py # 配置加载器
│   ├── database.py      # 数据库连接
│   ├── model_manager.py # 模型管理
│   └── environment_checker.py # 环境检查
├── db.sql              # 数据库初始化脚本
├── app.py              # 主应用文件
└── requirements.txt    # 依赖包列表
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- MySQL 5.7+
- Milvus 2.3+
- Neo4j 5.0+

### 安装步骤

1. **克隆项目**
```bash
git clone <project_url>
cd PdfRAG
```

2. **创建虚拟环境**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **配置数据库**

首先确保MySQL、Milvus和Neo4j服务正在运行，然后执行数据库初始化：

```bash
# 初始化MySQL数据库
mysql -h 192.168.2.100 -u root -p < db.sql
```

5. **配置文件**

根据您的环境修改配置文件：

- `config/db.yaml`: 数据库连接信息
- `config/model.yaml`: 模型配置
- `config/config.yaml`: 应用配置

6. **启动应用**
```bash
python app.py
```

服务器启动后，访问 http://localhost:5000

## 📖 使用说明

### 文件管理

1. **上传文件**: 在文件管理页面，拖拽或点击上传PDF文件
2. **查看状态**: 文件上传后会自动解析，可查看处理进度
3. **文件操作**: 支持重命名、删除等操作

### 智能检索

1. **开始对话**: 在智能检索页面输入问题
2. **多轮对话**: 支持连续提问，系统会理解上下文
3. **查看来源**: AI回答会包含相关文档来源信息

## ⚙️ 配置说明

### 数据库配置 (config/db.yaml)

```yaml
mysql:
  host: "192.168.2.100"
  port: 3306
  username: "root"
  password: "zhang"
  database: "pdf_rag"

milvus:
  host: "192.168.2.100"
  port: 19530
  database: "pdf_ai_doc"
  collection: "pdf_doc"

neo4j:
  uri: "bolt://192.168.2.100:7687"
  username: "neo4j"
  password: "zhang123456"
```

### 模型配置 (config/model.yaml)

```yaml
# GPU加速开关
gpu_acceleration: false

# LLM配置
llm:
  api_url: "https://api.deepseek.com"
  api_key: "sk-27e712e3a6c64533884adc0ad040ff3b"
  model_name: "deepseek-chat"

# 嵌入模型配置
embedding:
  model_name: "sentence-transformers/all-MiniLM-L6-v2"
  dimensions: 768
```

## 🔧 开发指南

### 添加新的路由

1. 在 `app/routes/` 下创建新的路由文件
2. 实现对应的服务逻辑
3. 在 `app.py` 中注册蓝图

### 扩展模型支持

1. 在 `utils/model_manager.py` 中添加新模型的加载逻辑
2. 更新 `config/model.yaml` 配置
3. 在服务层调用新模型

### 前端开发

前端采用原生HTML/CSS/JavaScript开发，主要文件：

- `templates/html/index.html`: 主页面
- `templates/css/style.css`: 样式文件
- `templates/js/`: JavaScript文件

## 🐛 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查数据库服务是否启动
   - 验证连接配置是否正确

2. **模型下载失败**
   - 检查网络连接
   - 确认模型路径配置正确

3. **文件上传失败**
   - 检查文件大小是否超过限制
   - 确认上传目录权限

### 日志查看

系统日志保存在 `logs/app.log`，可以通过日志分析问题：

```bash
tail -f logs/app.log
```

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

## 🙏 致谢

- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) - PDF处理
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - OCR识别
- [Sentence Transformers](https://github.com/UKPLab/sentence-transformers) - 文本嵌入
- [Milvus](https://github.com/milvus-io/milvus) - 向量数据库
- [Neo4j](https://github.com/neo4j/neo4j) - 图数据库

## 📞 联系方式

如有问题或建议，请通过以下方式联系：

- 创建 Issue
- 发送邮件至: [your-email@example.com]

---

**PDF智能文件管理系统** - 让文档检索更智能！ 