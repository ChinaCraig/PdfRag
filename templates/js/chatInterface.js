/**
 * 智能检索聊天界面模块
 */

// 初始化聊天界面
document.addEventListener('DOMContentLoaded', function() {
    initializeChatInterface();
});

/**
 * 初始化聊天界面
 */
function initializeChatInterface() {
    console.log('初始化聊天界面...');
    
    // 初始化输入框
    initializeChatInput();
    
    // 初始化会话
    initializeSession();
}

/**
 * 初始化聊天输入
 */
function initializeChatInput() {
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    const charCount = document.getElementById('charCount');
    
    if (!chatInput) return;
    
    // 输入框自动调整高度
    chatInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        
        // 更新字符计数
        if (charCount) {
            const count = this.value.length;
            charCount.textContent = count;
            
            // 字符数超限提示
            const charCountContainer = charCount.parentElement;
            if (count > 1000) {
                charCountContainer.style.color = 'var(--error-color)';
            } else if (count > 800) {
                charCountContainer.style.color = 'var(--warning-color)';
            } else {
                charCountContainer.style.color = 'var(--text-muted)';
            }
        }
        
        // 更新发送按钮状态
        updateSendButton();
    });
    
    // 回车发送（Shift+Enter换行）
    chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // 发送按钮点击
    if (sendButton) {
        sendButton.addEventListener('click', sendMessage);
    }
}

/**
 * 初始化会话
 */
async function initializeSession() {
    if (!window.App.sessionId) {
        try {
            const result = await window.Http.post('/api/search/session', {});
            if (result.success) {
                window.App.sessionId = result.session_id;
                console.log('创建新会话:', window.App.sessionId);
            }
        } catch (error) {
            console.error('创建会话失败:', error);
        }
    }
}

/**
 * 发送消息
 */
async function sendMessage() {
    const chatInput = document.getElementById('chatInput');
    const message = chatInput.value.trim();
    
    if (!message) {
        showNotification('请输入问题', 'warning');
        return;
    }
    
    if (message.length > 1000) {
        showNotification('问题长度不能超过1000字符', 'error');
        return;
    }
    
    // 禁用输入和发送按钮
    setInputDisabled(true);
    
    try {
        // 显示用户消息
        addMessage('user', message);
        
        // 清空输入框
        chatInput.value = '';
        chatInput.style.height = 'auto';
        updateCharCount(0);
        
        // 滚动到底部
        scrollToBottom();
        
        // 显示AI思考状态
        const thinkingMessageId = addThinkingMessage();
        
        // 发送到服务器（流式）
        await sendStreamMessage(message, thinkingMessageId);
        
    } catch (error) {
        console.error('发送消息失败:', error);
        showNotification('发送失败，请重试', 'error');
        removeMessage(thinkingMessageId);
    } finally {
        // 恢复输入状态
        setInputDisabled(false);
        chatInput.focus();
    }
}

/**
 * 发送流式消息 - 支持思考过程和多媒体内容
 */
async function sendStreamMessage(message, thinkingMessageId) {
    try {
        const response = await fetch('/api/search/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: message,
                session_id: window.App.sessionId
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        let buffer = '';
        let aiMessageId = null;
        let multimediaContents = [];
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            // 处理数据行
            const lines = buffer.split('\n');
            buffer = lines.pop(); // 保留最后一个可能不完整的行
            
            for (const line of lines) {
                if (line.trim() === '') continue;
                
                try {
                    // 处理SSE格式：移除"data: "前缀
                    let jsonData = line;
                if (line.startsWith('data: ')) {
                        jsonData = line.slice(6); // 移除"data: "前缀
                    }
                    
                    if (jsonData.trim() === '') continue;
                    
                    const parsed = JSON.parse(jsonData);
                    
                    // 处理思考过程
                    if (parsed.type === 'thinking_start') {
                        updateThinkingMessage(thinkingMessageId, parsed.message, parsed.progress);
                    } else if (parsed.type === 'thinking_update') {
                        updateThinkingMessage(thinkingMessageId, parsed.message, parsed.progress, parsed.data);
                    } else if (parsed.type === 'thinking_complete') {
                        updateThinkingMessage(thinkingMessageId, parsed.message, parsed.progress);
                        // 思考完成后，准备开始显示答案
                        setTimeout(() => {
                            removeMessage(thinkingMessageId);
                            aiMessageId = addMessage('assistant', '', true);
                        }, 500);
                    }
                    // 处理多媒体内容
                    else if (parsed.type === 'multimedia_content') {
                        multimediaContents = parsed.contents;
                    }
                                        // 处理答案内容
                    else if (parsed.type === 'answer_start') {
                        // 准备开始接收完整答案
                        console.log('开始生成答案:', parsed.message);
                    } else if (parsed.type === 'answer_complete') {
                        // 接收完整的结构化答案
                        console.log('答案生成完成');
                        removeMessage(thinkingMessageId);
                        aiMessageId = addUnifiedMessage('assistant', parsed.content);
                        finalizeMessage(aiMessageId);
                        } else if (parsed.type === 'error') {
                            throw new Error(parsed.message);
                        }
                        
                    } catch (parseError) {
                    console.error('解析流式数据失败:', parseError, 'Line:', line);
                }
            }
        }
        
    } catch (error) {
        console.error('流式消息发送失败:', error);
        removeMessage(thinkingMessageId);
        addMessage('assistant', '抱歉，我遇到了一些问题，请稍后再试。');
        throw error;
    }
}

/**
 * 添加消息到聊天界面
 */
function addMessage(role, content, isStreaming = false) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const isUser = role === 'user';
    
    const messageHtml = `
        <div class="message ${role}" id="${messageId}">
            <div class="message-avatar ${role}-avatar">
                <i class="fas ${isUser ? 'fa-user' : 'fa-robot'}"></i>
            </div>
            <div class="message-content">
                ${isStreaming ? '' : content}
            </div>
        </div>
    `;
    
    chatMessages.insertAdjacentHTML('beforeend', messageHtml);
    scrollToBottom();
    
    return messageId;
}

/**
 * 添加思考状态消息
 */
function addThinkingMessage() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const messageId = `thinking_${Date.now()}`;
    
    const thinkingHtml = `
        <div class="message assistant thinking-message" id="${messageId}">
            <div class="message-avatar assistant-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="thinking-container">
                    <div class="thinking-header">
                        <div class="thinking-title">
                            <i class="fas fa-brain thinking-icon"></i>
                            <span id="${messageId}_title">AI正在思考</span>
                        </div>
                        <div class="thinking-progress">
                            <div class="progress-bar">
                                <div class="progress-fill" id="${messageId}_progress" style="width: 0%"></div>
                            </div>
                            <span class="progress-text" id="${messageId}_percent">0%</span>
                        </div>
                    </div>
                    <div class="thinking-details">
                        <div class="thinking-stage" id="${messageId}_stage">正在分析您的问题...</div>
                        <div class="thinking-data" id="${messageId}_data"></div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    chatMessages.insertAdjacentHTML('beforeend', thinkingHtml);
    scrollToBottom();
    
    return messageId;
}

/**
 * 更新思考状态消息
 */
function updateThinkingMessage(messageId, message, progress, data = null) {
    const stageElement = document.getElementById(`${messageId}_stage`);
    const progressElement = document.getElementById(`${messageId}_progress`);
    const percentElement = document.getElementById(`${messageId}_percent`);
    const dataElement = document.getElementById(`${messageId}_data`);
    
    if (stageElement) {
        stageElement.textContent = message;
    }
    
    if (progressElement && percentElement) {
        progressElement.style.width = `${progress}%`;
        percentElement.textContent = `${progress}%`;
    }
    
    if (data && dataElement) {
        let dataText = '';
        if (data.vector_count !== undefined) {
            dataText += `找到${data.vector_count}个相关文档 `;
        }
        if (data.graph_count !== undefined) {
            dataText += `发现${data.graph_count}个知识关联 `;
        }
        if (data.multimedia_count !== undefined) {
            dataText += `包含${data.multimedia_count}个多媒体元素 `;
        }
        if (data.content_types) {
            const types = data.content_types.map(type => {
                const typeMap = {
                    'text': '文字',
                    'image': '图片', 
                    'table': '表格',
                    'chart': '图表'
                };
                return typeMap[type] || type;
            });
            dataText += `(${types.join('、')})`;
        }
        dataElement.textContent = dataText;
    }
    
    scrollToBottom();
}

/**
 * 向消息追加内容
 */
function appendToMessage(messageId, content) {
    const messageElement = document.getElementById(messageId);
    if (!messageElement) return;
    
    const contentElement = messageElement.querySelector('.message-content');
    if (contentElement) {
        // 查找或创建文本内容容器
        let textContainer = contentElement.querySelector('.text-content');
        if (!textContainer) {
            textContainer = document.createElement('div');
            textContainer.className = 'text-content';
            contentElement.appendChild(textContainer);
        }
        textContainer.textContent += content;
    }
}

/**
 * 添加统一的消息（包含文本和多媒体内容）
 */
function addUnifiedMessage(role, unifiedContent) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const isUser = role === 'user';
    
    // 创建消息容器
    const messageHtml = `
        <div class="message ${role}" id="${messageId}">
            <div class="message-avatar ${role}-avatar">
                <i class="fas ${isUser ? 'fa-user' : 'fa-robot'}"></i>
            </div>
            <div class="message-content">
                <div class="unified-content-container"></div>
            </div>
        </div>
    `;
    
    chatMessages.insertAdjacentHTML('beforeend', messageHtml);
    
    // 渲染统一内容
    renderUnifiedContent(messageId, unifiedContent);
    
    scrollToBottom();
    return messageId;
}

/**
 * 渲染统一内容（文本 + 多媒体）
 */
function renderUnifiedContent(messageId, unifiedContent) {
    const messageElement = document.getElementById(messageId);
    if (!messageElement) return;
    
    const container = messageElement.querySelector('.unified-content-container');
    if (!container) return;
    
    const textContent = unifiedContent.text_content || '';
    const multimediaMap = unifiedContent.multimedia_map || {};
    
    // 处理文本中的占位符
    let processedText = textContent;
    
    // 替换占位符为实际的多媒体内容
    const placeholderRegex = /\[([A-Z]+):([^\]]+)\]/g;
    let lastIndex = 0;
    const contentParts = [];
    
    let match;
    while ((match = placeholderRegex.exec(textContent)) !== null) {
        // 添加占位符之前的文本
        if (match.index > lastIndex) {
            const textPart = textContent.slice(lastIndex, match.index);
            if (textPart.trim()) {
                contentParts.push({
                    type: 'text',
                    content: textPart
                });
            }
        }
        
        // 添加多媒体内容
        const [fullMatch, mediaType, chunkId] = match;
        if (multimediaMap[chunkId]) {
            contentParts.push({
                type: 'multimedia',
                mediaType: mediaType.toLowerCase(),
                chunkId: chunkId,
                data: multimediaMap[chunkId]
            });
        } else {
            // 如果找不到对应的多媒体内容，保留原文本
            contentParts.push({
                type: 'text',
                content: fullMatch
            });
        }
        
        lastIndex = match.index + fullMatch.length;
    }
    
    // 添加最后一部分文本
    if (lastIndex < textContent.length) {
        const remainingText = textContent.slice(lastIndex);
        if (remainingText.trim()) {
            contentParts.push({
                type: 'text',
                content: remainingText
            });
        }
    }
    
    // 如果没有占位符，直接显示文本
    if (contentParts.length === 0 && textContent.trim()) {
        contentParts.push({
            type: 'text',
            content: textContent
        });
    }
    
    // 渲染所有部分
    contentParts.forEach(part => {
        if (part.type === 'text') {
            const textElement = document.createElement('div');
            textElement.className = 'text-part';
            textElement.innerHTML = part.content.replace(/\n/g, '<br>');
            container.appendChild(textElement);
        } else if (part.type === 'multimedia') {
            const multimediaElement = createInlineMultimediaElement(part.data, part.chunkId);
            if (multimediaElement) {
                container.appendChild(multimediaElement);
            }
        }
    });
    
    scrollToBottom();
}

/**
 * 创建内联多媒体元素
 */
function createInlineMultimediaElement(data, chunkId) {
    const wrapper = document.createElement('div');
    wrapper.className = `inline-multimedia-item ${data.type}-item`;
    
    switch (data.type) {
        case 'image':
            return createInlineImageElement(data, wrapper, chunkId);
        case 'table':
            return createInlineTableElement(data, wrapper, chunkId);
        case 'chart':
            return createInlineChartElement(data, wrapper, chunkId);
        default:
            return null;
    }
}

/**
 * 创建内联图片元素
 */
function createInlineImageElement(data, wrapper, chunkId) {
    const displayData = data.display_data || {};
    
    wrapper.innerHTML = `
        <div class="inline-image-container">
            <div class="multimedia-header">
                <i class="fas fa-image"></i>
                <span class="multimedia-title">相关图片</span>
                <button class="btn-expand" onclick="expandImage('${chunkId}')">
                    <i class="fas fa-expand"></i>
                </button>
            </div>
            <div class="image-content">
                ${displayData.image_base64 ? 
                    `<img src="${displayData.image_base64}" alt="文档图片" class="document-image" onclick="expandImage('${chunkId}')">` :
                    '<div class="image-placeholder">图片内容暂时不可用</div>'
                }
                ${data.content_description ? `<div class="image-description">${data.content_description}</div>` : ''}
            </div>
        </div>
    `;
    
    return wrapper;
}

/**
 * 创建内联表格元素
 */
function createInlineTableElement(data, wrapper, chunkId) {
    const displayData = data.display_data || {};
    const tableData = displayData.table_data || [];
    
    let tableHtml = '';
    if (tableData.length > 0) {
        const headers = tableData[0];
        const rows = tableData.slice(1);
        
        tableHtml = `
            <table class="document-table">
                <thead>
                    <tr>
                        ${headers.map(header => `<th>${header}</th>`).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${rows.slice(0, 5).map(row => 
                        `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`
                    ).join('')}
                </tbody>
            </table>
            ${rows.length > 5 ? `<div class="table-more">还有 ${rows.length - 5} 行数据... <button onclick="expandTable('${chunkId}')">查看全部</button></div>` : ''}
        `;
    } else {
        tableHtml = '<div class="table-placeholder">表格数据暂时不可用</div>';
    }
    
    wrapper.innerHTML = `
        <div class="inline-table-container">
            <div class="multimedia-header">
                <i class="fas fa-table"></i>
                <span class="multimedia-title">相关表格</span>
                <button class="btn-expand" onclick="expandTable('${chunkId}')">
                    <i class="fas fa-expand"></i>
                </button>
            </div>
            <div class="table-content">
                <div class="table-wrapper">
                    ${tableHtml}
                </div>
                ${data.content_description ? `<div class="table-description">${data.content_description}</div>` : ''}
            </div>
        </div>
    `;
    
    return wrapper;
}

/**
 * 创建内联图表元素
 */
function createInlineChartElement(data, wrapper, chunkId) {
    const displayData = data.display_data || {};
    
    wrapper.innerHTML = `
        <div class="inline-chart-container">
            <div class="multimedia-header">
                <i class="fas fa-chart-bar"></i>
                <span class="multimedia-title">相关图表</span>
                <button class="btn-expand" onclick="expandChart('${chunkId}')">
                    <i class="fas fa-expand"></i>
                </button>
            </div>
            <div class="chart-content">
                ${displayData.chart_base64 ? 
                    `<img src="${displayData.chart_base64}" alt="文档图表" class="document-chart" onclick="expandChart('${chunkId}')">` :
                    '<div class="chart-placeholder">图表内容暂时不可用</div>'
                }
                ${data.content_description ? `<div class="chart-description">${data.content_description}</div>` : ''}
            </div>
        </div>
    `;
    
    return wrapper;
}

/**
 * 添加多媒体内容到消息（兼容旧版本）
 */
function addMultimediaToMessage(messageId, multimediaContents) {
    // 保留这个函数以防向后兼容问题
    console.warn('addMultimediaToMessage已弃用，请使用addUnifiedMessage');
}

/**
 * 创建多媒体元素
 */
function createMultimediaElement(content, index) {
    const wrapper = document.createElement('div');
    wrapper.className = `multimedia-item ${content.type}-item`;
    
    switch (content.type) {
        case 'image':
            return createImageElement(content, wrapper);
        case 'table':
            return createTableElement(content, wrapper);
        case 'chart':
            return createChartElement(content, wrapper);
        default:
            return null;
    }
}

/**
 * 创建图片元素
 */
function createImageElement(content, wrapper) {
    const displayData = content.display_data || {};
    
    wrapper.innerHTML = `
        <div class="image-container">
            <div class="multimedia-header">
                <i class="fas fa-image"></i>
                <span class="multimedia-title">相关图片</span>
                <button class="btn-expand" onclick="expandImage('${content.chunk_id}')">
                    <i class="fas fa-expand"></i>
                </button>
            </div>
            <div class="image-content">
                ${displayData.image_base64 ? 
                    `<img src="${displayData.image_base64}" alt="文档图片" class="document-image" onclick="expandImage('${content.chunk_id}')">` :
                    '<div class="image-placeholder">图片加载中...</div>'
                }
                <div class="image-description">${content.content}</div>
            </div>
        </div>
    `;
    
    return wrapper;
}

/**
 * 创建表格元素
 */
function createTableElement(content, wrapper) {
    const displayData = content.display_data || {};
    const tableData = displayData.table_data || [];
    
    let tableHtml = '';
    if (tableData.length > 0) {
        const headers = tableData[0];
        const rows = tableData.slice(1);
        
        tableHtml = `
            <table class="document-table">
                <thead>
                    <tr>
                        ${headers.map(header => `<th>${header}</th>`).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${rows.slice(0, 10).map(row => 
                        `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`
                    ).join('')}
                </tbody>
            </table>
            ${rows.length > 10 ? `<div class="table-more">还有 ${rows.length - 10} 行数据...</div>` : ''}
        `;
    } else {
        tableHtml = '<div class="table-placeholder">表格数据加载中...</div>';
    }
    
    wrapper.innerHTML = `
        <div class="table-container">
            <div class="multimedia-header">
                <i class="fas fa-table"></i>
                <span class="multimedia-title">相关表格</span>
                <button class="btn-expand" onclick="expandTable('${content.chunk_id}')">
                    <i class="fas fa-expand"></i>
                </button>
            </div>
            <div class="table-content">
                <div class="table-wrapper">
                    ${tableHtml}
                </div>
                <div class="table-description">${content.content}</div>
            </div>
        </div>
    `;
    
    return wrapper;
}

/**
 * 创建图表元素
 */
function createChartElement(content, wrapper) {
    const displayData = content.display_data || {};
    
    wrapper.innerHTML = `
        <div class="chart-container">
            <div class="multimedia-header">
                <i class="fas fa-chart-bar"></i>
                <span class="multimedia-title">相关图表</span>
                <button class="btn-expand" onclick="expandChart('${content.chunk_id}')">
                    <i class="fas fa-expand"></i>
                </button>
            </div>
            <div class="chart-content">
                ${displayData.chart_base64 ? 
                    `<img src="${displayData.chart_base64}" alt="文档图表" class="document-chart" onclick="expandChart('${content.chunk_id}')">` :
                    '<div class="chart-placeholder">图表加载中...</div>'
                }
                <div class="chart-description">${content.content}</div>
            </div>
        </div>
    `;
    
    return wrapper;
}

/**
 * 完成消息处理
 */
function finalizeMessage(messageId) {
    const messageElement = document.getElementById(messageId);
    if (messageElement) {
        messageElement.classList.add('message-complete');
    }
}

/**
 * 移除消息
 */
function removeMessage(messageId) {
    const messageElement = document.getElementById(messageId);
    if (messageElement) {
        messageElement.remove();
    }
}

/**
 * 滚动到底部
 */
function scrollToBottom() {
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

/**
 * 设置输入禁用状态
 */
function setInputDisabled(disabled) {
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    
    if (chatInput) {
        chatInput.disabled = disabled;
    }
    
    if (sendButton) {
        sendButton.disabled = disabled;
    }
    
    updateSendButton();
}

/**
 * 更新发送按钮状态
 */
function updateSendButton() {
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    
    if (!chatInput || !sendButton) return;
    
    const hasContent = chatInput.value.trim().length > 0;
    const isEnabled = hasContent && !chatInput.disabled;
    
    sendButton.disabled = !isEnabled;
}

/**
 * 更新字符计数
 */
function updateCharCount(count) {
    const charCount = document.getElementById('charCount');
    if (charCount) {
        charCount.textContent = count;
    }
}

/**
 * 清空对话
 */
async function clearChat() {
    if (!confirm('确定要清空对话历史吗？')) {
        return;
    }
    
    try {
        if (window.App.sessionId) {
            await window.Http.delete(`/api/search/clear/${window.App.sessionId}`);
        }
        
        // 清空聊天界面
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            chatMessages.innerHTML = `
                <div class="welcome-message">
                    <div class="assistant-avatar">
                        <i class="fas fa-robot"></i>
                    </div>
                    <div class="message-content">
                        <p>您好！我是PDF智能助手，可以帮您分析和检索已上传的PDF文档内容。请输入您的问题。</p>
                    </div>
                </div>
            `;
        }
        
        // 创建新会话
        await initializeSession();
        
        showNotification('对话已清空', 'success');
        
    } catch (error) {
        console.error('清空对话失败:', error);
        showNotification('清空对话失败', 'error');
    }
}

/**
 * 展开图片
 */
function expandImage(chunkId) {
    // 创建图片预览模态框
    const modal = document.createElement('div');
    modal.className = 'image-modal';
    modal.innerHTML = `
        <div class="modal-overlay" onclick="closeImageModal()">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>图片详情</h3>
                    <button class="modal-close" onclick="closeImageModal()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="modal-body">
                    <div class="loading">加载中...</div>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // 这里可以加载完整的图片信息
    console.log('展开图片:', chunkId);
}

/**
 * 展开表格
 */
function expandTable(chunkId) {
    console.log('展开表格:', chunkId);
    // 实现表格的完整视图
}

/**
 * 展开图表
 */
function expandChart(chunkId) {
    console.log('展开图表:', chunkId);
    // 实现图表的完整视图
}

/**
 * 关闭图片模态框
 */
function closeImageModal() {
    const modal = document.querySelector('.image-modal');
    if (modal) {
        modal.remove();
    }
}

// 创建全局ChatInterface对象
window.ChatInterface = {
    sendMessage: sendMessage,
    clearChat: clearChat,
    initializeChatInterface: initializeChatInterface,
    expandImage: expandImage,
    expandTable: expandTable,
    expandChart: expandChart
}; 