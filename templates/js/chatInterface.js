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
 * 发送流式消息
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
        
        // 移除思考状态，添加AI消息容器
        removeMessage(thinkingMessageId);
        const aiMessageId = addMessage('assistant', '', true);
        
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            // 处理数据行
            const lines = buffer.split('\n');
            buffer = lines.pop(); // 保留最后一个可能不完整的行
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    
                    if (data.trim() === '') continue;
                    
                    try {
                        const parsed = JSON.parse(data);
                        
                        if (parsed.type === 'chunk') {
                            appendToMessage(aiMessageId, parsed.content);
                            scrollToBottom();
                        } else if (parsed.type === 'start') {
                            console.log('开始接收流式数据');
                        } else if (parsed.type === 'end') {
                            console.log('流式数据接收完成');
                        } else if (parsed.type === 'error') {
                            throw new Error(parsed.message);
                        }
                        
                    } catch (parseError) {
                        console.error('解析流式数据失败:', parseError);
                    }
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
        <div class="message assistant" id="${messageId}">
            <div class="message-avatar assistant-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="typing-indicator">
                    正在思考
                    <div class="typing-dots">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
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
 * 向消息追加内容
 */
function appendToMessage(messageId, content) {
    const messageElement = document.getElementById(messageId);
    if (!messageElement) return;
    
    const contentElement = messageElement.querySelector('.message-content');
    if (contentElement) {
        contentElement.textContent += content;
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

// 创建全局ChatInterface对象
window.ChatInterface = {
    sendMessage: sendMessage,
    clearChat: clearChat,
    initializeChatInterface: initializeChatInterface
}; 