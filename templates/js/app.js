/**
 * PDF智能文件管理系统 - 全局JavaScript功能
 */

// 全局应用对象
window.App = {
    currentPage: 'file-management',
    config: {
        apiBase: '/api',
        uploadMaxSize: 100 * 1024 * 1024, // 100MB
        allowedTypes: ['application/pdf']
    }
};

// HTTP请求工具
window.Http = {
    async get(url, options = {}) {
        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            return await response.json();
        } catch (error) {
            console.error('GET请求失败:', error);
            throw error;
        }
    },

    async post(url, data = {}, options = {}) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                body: JSON.stringify(data),
                ...options
            });
            return await response.json();
        } catch (error) {
            console.error('POST请求失败:', error);
            throw error;
        }
    },

    async postFile(url, formData, options = {}) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                body: formData,
                ...options
            });
            return await response.json();
        } catch (error) {
            console.error('文件上传失败:', error);
            throw error;
        }
    },

    async put(url, data = {}, options = {}) {
        try {
            const response = await fetch(url, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                body: JSON.stringify(data),
                ...options
            });
            return await response.json();
        } catch (error) {
            console.error('PUT请求失败:', error);
            throw error;
        }
    },

    async delete(url, options = {}) {
        try {
            const response = await fetch(url, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            return await response.json();
        } catch (error) {
            console.error('DELETE请求失败:', error);
            throw error;
        }
    }
};

// DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('PDF智能文件管理系统启动...');
    
    // 初始化全局功能
    initializeApp();
    
    // 根据hash设置当前页面
    handleHashChange();
    
    // 监听hash变化
    window.addEventListener('hashchange', handleHashChange);
});

/**
 * 初始化应用程序
 */
function initializeApp() {
    // 初始化侧边栏导航
    initializeSidebar();
    
    // 初始化模态窗口
    initializeModals();
    
    // 初始化通知系统
    initializeNotifications();
}

/**
 * 初始化侧边栏导航
 */
function initializeSidebar() {
    const menuItems = document.querySelectorAll('.nav-link');
    
    menuItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            
            // 移除所有活跃状态
            menuItems.forEach(mi => mi.classList.remove('active'));
            
            // 添加当前活跃状态
            this.classList.add('active');
            
            // 获取目标页面
            const targetPage = this.getAttribute('data-page');
            if (targetPage) {
                window.location.hash = '#' + targetPage;
            }
        });
    });
}

/**
 * 处理页面hash变化
 */
function handleHashChange() {
    const hash = window.location.hash.slice(1) || 'file-management';
    const pages = document.querySelectorAll('.page-content');
    const menuItems = document.querySelectorAll('.nav-link');
    
    // 移除所有页面的active类
    pages.forEach(page => {
        page.classList.remove('active');
    });
    
    // 显示目标页面
    const targetPage = document.getElementById(hash);
    if (targetPage) {
        targetPage.classList.add('active');
        App.currentPage = hash;
        
        // 页面切换后的特殊处理
        if (hash === 'file-management') {
            // 切换到文件管理页面时，确保文件上传功能正确初始化
            setTimeout(() => {
                if (window.FileManager && window.FileManager.initializeFileManager) {
                    console.log('重新初始化文件管理功能');
                    window.FileManager.initializeFileManager();
                }
            }, 100);
        }
    }
    
    // 更新菜单状态
    menuItems.forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-page') === hash) {
            item.classList.add('active');
        }
    });
}

/**
 * 显示帮助弹窗
 */
function showHelp() {
    console.log('显示帮助弹窗');
    const modal = document.getElementById('helpModal');
    if (modal) {
        modal.style.display = 'block';
    }
}

/**
 * 显示模态窗口
 */
function showModal(modalId) {
    console.log('显示模态窗口:', modalId);
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('show');
        modal.style.display = 'flex';
    }
}

/**
 * 关闭模态窗口
 */
function closeModal(modalId) {
    console.log('关闭模态窗口:', modalId);
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('show');
        modal.style.display = 'none';
    }
}

/**
 * 初始化模态窗口
 */
function initializeModals() {
    // 点击模态窗口外部关闭
    window.addEventListener('click', function(event) {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
    });
}

/**
 * 触发文件选择
 */
function triggerFileSelect() {
    console.log('触发文件选择');
    const fileInput = document.getElementById('fileInput');
    console.log('fileInput元素:', fileInput);
    
    if (fileInput) {
        console.log('点击fileInput元素');
        fileInput.click();
    } else {
        console.error('找不到fileInput元素');
    }
}

/**
 * 刷新文件列表
 */
function refreshFileList() {
    console.log('刷新文件列表');
    if (typeof window.FileManager !== 'undefined' && window.FileManager.refreshFileList) {
        window.FileManager.refreshFileList();
    } else {
        showNotification('正在刷新文件列表...', 'info');
        // 如果FileManager还没有加载，延迟执行
        setTimeout(() => {
            if (typeof window.FileManager !== 'undefined' && window.FileManager.refreshFileList) {
                window.FileManager.refreshFileList();
            }
        }, 100);
    }
}

/**
 * 确认重命名
 */
function confirmRename() {
    console.log('确认重命名');
    const newName = document.getElementById('newFileName');
    if (newName && newName.value.trim()) {
        if (typeof window.FileManager !== 'undefined' && window.FileManager.confirmRename) {
            window.FileManager.confirmRename(newName.value.trim());
        }
    } else {
        showNotification('请输入新的文件名', 'error');
    }
}

/**
 * 发送消息
 */
function sendMessage() {
    console.log('发送消息');
    if (typeof window.ChatInterface !== 'undefined' && window.ChatInterface.sendMessage) {
        window.ChatInterface.sendMessage();
    }
}

/**
 * 清空聊天
 */
function clearChat() {
    console.log('清空聊天');
    if (typeof window.ChatInterface !== 'undefined' && window.ChatInterface.clearChat) {
        window.ChatInterface.clearChat();
    }
}

/**
 * 显示通知
 */
function showNotification(message, type = 'info') {
    console.log('显示通知:', message, type);
    
    const notification = document.getElementById('notification');
    const notificationText = document.getElementById('notificationMessage');
    
    if (notification && notificationText) {
        notificationText.textContent = message;
        notification.className = `notification ${type} show`;
        
        // 自动隐藏
        setTimeout(() => {
            hideNotification();
        }, 5000);
    }
}

/**
 * 隐藏通知
 */
function hideNotification() {
    const notification = document.getElementById('notification');
    if (notification) {
        notification.classList.remove('show');
    }
}

/**
 * 初始化通知系统
 */
function initializeNotifications() {
    // 通知会自动显示和隐藏
}

/**
 * 显示加载覆盖层
 */
function showLoading(message = '加载中...') {
    const loading = document.getElementById('loadingOverlay');
    const loadingText = loading ? loading.querySelector('.loading-spinner p') : null;
    
    if (loading) {
        if (loadingText) {
            loadingText.textContent = message;
        }
        loading.classList.add('show');
        loading.style.display = 'flex';
    }
}

/**
 * 隐藏加载覆盖层
 */
function hideLoading() {
    const loading = document.getElementById('loadingOverlay');
    if (loading) {
        loading.classList.remove('show');
        loading.style.display = 'none';
    }
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * 格式化时间
 */
function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) { // 1分钟内
        return '刚刚';
    } else if (diff < 3600000) { // 1小时内
        return Math.floor(diff / 60000) + '分钟前';
    } else if (diff < 86400000) { // 1天内
        return Math.floor(diff / 3600000) + '小时前';
    } else {
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    }
}

/**
 * 验证文件类型
 */
function validateFile(file) {
    if (!file) {
        return { valid: false, message: '请选择文件' };
    }
    
    if (file.size > App.config.uploadMaxSize) {
        return { valid: false, message: '文件大小超过限制' };
    }
    
    if (!App.config.allowedTypes.includes(file.type)) {
        return { valid: false, message: '只支持PDF文件' };
    }
    
    return { valid: true };
}

// 导出全局函数供HTML使用
window.showHelp = showHelp;
window.closeModal = closeModal;
window.triggerFileSelect = triggerFileSelect;
window.refreshFileList = refreshFileList;
window.confirmRename = confirmRename;
window.sendMessage = sendMessage;
window.clearChat = clearChat;
window.hideNotification = hideNotification;
window.showNotification = showNotification;
window.showLoading = showLoading;
window.hideLoading = hideLoading; 