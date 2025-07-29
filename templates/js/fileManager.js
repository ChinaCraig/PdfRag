/**
 * 文件管理模块
 */

// 初始化文件管理功能
document.addEventListener('DOMContentLoaded', function() {
    initializeFileManager();
});

/**
 * 初始化文件管理器
 */
function initializeFileManager() {
    console.log('初始化文件管理器...');
    
    // 初始化文件上传
    initializeFileUpload();
    
    // 初始化加载文件列表
    refreshFileList();
    
    // 定期刷新文件状态
    setInterval(updateFileStatus, 5000);
}

// 用于追踪是否已经初始化
let fileUploadInitialized = false;

/**
 * 初始化文件上传
 */
function initializeFileUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    
    console.log('初始化文件上传，uploadArea:', uploadArea, 'fileInput:', fileInput);
    console.log('当前页面:', window.location.hash);
    
    if (!uploadArea || !fileInput) {
        console.error('找不到文件上传元素，uploadArea:', uploadArea, 'fileInput:', fileInput);
        return;
    }
    
    // 如果已经初始化过，只检查事件监听器是否还在
    if (fileUploadInitialized) {
        console.log('文件上传功能已初始化，检查事件监听器...');
        // 移除旧的监听器（通过添加标记来避免重复）
        if (fileInput._changeListenerAdded) {
            console.log('跳过重复初始化');
            return;
        }
    }
    
    // 拖拽上传
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });
    
    // 文件输入变化监听
    const changeHandler = function(e) {
        console.log('文件输入变化事件触发，文件数量:', e.target.files.length);
        console.log('事件对象:', e);
        
        if (e.target.files.length > 0) {
            console.log('选择的文件:', e.target.files[0].name);
            handleFileUpload(e.target.files[0]);
        } else {
            console.log('没有选择文件');
        }
    };
    
    fileInput.addEventListener('change', changeHandler);
    fileInput._changeListenerAdded = true; // 标记已添加监听器
    
    fileUploadInitialized = true;
    console.log('文件上传功能初始化完成');
}

/**
 * 处理文件上传
 */
async function handleFileUpload(file) {
    console.log('开始上传文件:', file.name);
    
    // 验证文件类型
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showNotification('只支持PDF格式文件', 'error');
        return;
    }
    
    // 验证文件大小 (100MB)
    const maxSize = 100 * 1024 * 1024;
    if (file.size > maxSize) {
        showNotification('文件大小不能超过100MB', 'error');
        return;
    }
    
    try {
        showLoading('正在上传文件...');
        
        // 创建FormData
        const formData = new FormData();
        formData.append('file', file);
        
        // 上传文件
        const result = await window.Http.postFile('/api/file/upload', formData);
        
        hideLoading();
        
        if (result.success) {
            showNotification('文件上传成功，开始处理...', 'success');
            
            // 清空文件输入
            document.getElementById('fileInput').value = '';
            
            // 刷新文件列表
            await refreshFileList();
            
        } else {
            showNotification(result.message || '文件上传失败', 'error');
        }
        
    } catch (error) {
        hideLoading();
        console.error('文件上传失败:', error);
        showNotification('文件上传失败，请重试', 'error');
    }
}

/**
 * 刷新文件列表
 */
async function refreshFileList() {
    console.log('刷新文件列表...');
    
    try {
        const result = await window.Http.get('/api/file/list');
        
        if (result.success) {
            renderFileList(result.files);
        } else {
            console.error('获取文件列表失败:', result.message);
            showNotification('获取文件列表失败', 'error');
        }
        
    } catch (error) {
        console.error('获取文件列表失败:', error);
        showNotification('网络请求失败', 'error');
    }
}

/**
 * 渲染文件列表
 */
function renderFileList(files) {
    const fileList = document.getElementById('fileList');
    if (!fileList) return;
    
    if (!files || files.length === 0) {
        fileList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-file-pdf"></i>
                <h3>暂无PDF文件</h3>
                <p>请上传PDF文件开始使用智能检索功能</p>
            </div>
        `;
        return;
    }
    
    const fileItems = files.map(file => createFileItem(file)).join('');
    fileList.innerHTML = fileItems;
}

/**
 * 创建文件项HTML
 */
function createFileItem(file) {
    const statusClass = getStatusClass(file.status);
    const statusText = getStatusText(file.status);
    const progress = file.processing_progress || 0;
    
    return `
        <div class="file-item" data-file-id="${file.file_id}">
            <div class="file-icon">
                <i class="fas fa-file-pdf"></i>
            </div>
            <div class="file-info">
                <div class="file-name">${file.original_filename}</div>
                <div class="file-meta">
                    <span>${formatFileSize(file.file_size)}</span>
                    <span>${formatTime(file.upload_time)}</span>
                </div>
            </div>
            <div class="file-status">
                <span class="status-badge ${statusClass}">${statusText}</span>
                ${file.status === 'processing' ? `
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                    </div>
                ` : ''}
            </div>
            <div class="file-actions">
                <button class="action-btn" onclick="showFileDetail('${file.file_id}')" title="查看详情">
                    <i class="fas fa-info-circle"></i>
                </button>
                <button class="action-btn" onclick="showRenameModal('${file.file_id}', '${file.original_filename}')" title="重命名">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="action-btn danger" onclick="confirmDeleteFile('${file.file_id}', '${file.original_filename}')" title="删除">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `;
}

/**
 * 获取状态样式类
 */
function getStatusClass(status) {
    const statusMap = {
        'uploaded': 'uploaded',
        'processing': 'processing',
        'completed': 'completed',
        'failed': 'failed'
    };
    return statusMap[status] || 'uploaded';
}

/**
 * 获取状态文本
 */
function getStatusText(status) {
    const statusMap = {
        'uploaded': '已上传',
        'processing': '处理中',
        'completed': '已完成',
        'failed': '处理失败'
    };
    return statusMap[status] || '未知';
}

/**
 * 更新文件状态
 */
async function updateFileStatus() {
    const processingFiles = document.querySelectorAll('.status-badge.processing');
    
    for (const badge of processingFiles) {
        const fileItem = badge.closest('.file-item');
        const fileId = fileItem.getAttribute('data-file-id');
        
        try {
            const result = await window.Http.get(`/api/file/status/${fileId}`);
            
            if (result.success) {
                updateFileItemStatus(fileItem, result.status);
            }
            
        } catch (error) {
            console.error(`更新文件 ${fileId} 状态失败:`, error);
        }
    }
}

/**
 * 更新文件项状态
 */
function updateFileItemStatus(fileItem, status) {
    const statusBadge = fileItem.querySelector('.status-badge');
    const statusClass = getStatusClass(status.status);
    const statusText = getStatusText(status.status);
    
    // 更新状态样式
    statusBadge.className = `status-badge ${statusClass}`;
    statusBadge.textContent = statusText;
    
    // 更新进度条
    const progressFill = fileItem.querySelector('.progress-fill');
    if (progressFill && status.progress !== undefined) {
        progressFill.style.width = `${status.progress}%`;
    }
    
    // 如果处理完成，移除进度条
    if (status.status === 'completed' || status.status === 'failed') {
        const progressBar = fileItem.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.remove();
        }
    }
}

/**
 * 显示文件详情
 */
async function showFileDetail(fileId) {
    console.log('显示文件详情:', fileId);
    
    try {
        console.log('开始获取文件详情，显示loading...', fileId);
        showLoading('加载文件详情...');
        
        console.log('发送文件详情API请求...');
        const result = await window.Http.get(`/api/file/info/${fileId}`);
        
        console.log('文件详情API请求完成，隐藏loading...', result);
        hideLoading();
        
        if (result.success) {
            console.log('文件详情获取成功，显示模态框...');
            // 显示文件详情模态框
            const modalContent = document.getElementById('fileDetailContent');
            if (modalContent) {
                const fileInfo = result.file_info;
                const stats = result.statistics;
                const statusText = getStatusText(fileInfo.status);
                const statusClass = getStatusClass(fileInfo.status);
                
                modalContent.innerHTML = `
                    <div class="file-detail">
                        <div class="detail-section">
                            <h4>基本信息</h4>
                            <div class="info-grid">
                                <div class="info-item">
                                    <label>文件名：</label>
                                    <span>${fileInfo.original_filename}</span>
                                </div>
                                <div class="info-item">
                                    <label>文件大小：</label>
                                    <span>${formatFileSize(fileInfo.file_size)}</span>
                                </div>
                                <div class="info-item">
                                    <label>上传时间：</label>
                                    <span>${formatTime(fileInfo.upload_time)}</span>
                                </div>
                                <div class="info-item">
                                    <label>处理状态：</label>
                                    <span class="status-badge ${statusClass}">${statusText}</span>
                                </div>
                                <div class="info-item">
                                    <label>处理进度：</label>
                                    <span>${fileInfo.processing_progress}%</span>
                                </div>
                                <div class="info-item">
                                    <label>文件ID：</label>
                                    <span class="file-id">${fileInfo.file_id}</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="detail-section">
                            <h4>处理统计</h4>
                            <div class="stats-grid">
                                <div class="stat-item">
                                    <div class="stat-number">${stats.chunks_count}</div>
                                    <div class="stat-label">文本块</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-number">${stats.entities_count}</div>
                                    <div class="stat-label">实体</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-number">${stats.relations_count}</div>
                                    <div class="stat-label">关系</div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                
                console.log('模态框内容设置完成，准备显示...');
                // 确保模态框内容设置完成后再显示
                setTimeout(() => {
                    showModal('fileDetailModal');
                    console.log('文件详情模态框已显示');
                }, 10);
            } else {
                console.error('找不到fileDetailContent元素');
            }
        } else {
            console.error('文件详情API返回失败:', result.message);
            showNotification(result.message || '获取文件详情失败', 'error');
        }
        
    } catch (error) {
        console.error('文件详情过程中发生错误:', error);
        hideLoading();
        console.error('获取文件详情失败:', error);
        showNotification('获取文件详情失败', 'error');
    }
}

/**
 * 显示重命名模态框
 */
function showRenameModal(fileId, currentName) {
    window.App.currentFileId = fileId;
    
    const newFileNameInput = document.getElementById('newFileName');
    if (newFileNameInput) {
        newFileNameInput.value = currentName;
        newFileNameInput.focus();
        newFileNameInput.select();
    }
    
    showModal('renameModal');
}

/**
 * 确认重命名
 */
async function confirmRename() {
    const newFileName = document.getElementById('newFileName').value.trim();
    const fileId = window.App.currentFileId;
    
    if (!newFileName) {
        showNotification('文件名不能为空', 'error');
        return;
    }
    
    if (!fileId) {
        showNotification('文件ID无效', 'error');
        return;
    }
    
    try {
        console.log('开始重命名，显示loading...');
        showLoading('正在重命名...');
        
        console.log('发送重命名请求...');
        const result = await window.Http.put(`/api/file/rename/${fileId}`, {
            new_filename: newFileName
        });
        
        console.log('重命名请求完成，隐藏loading...', result);
        hideLoading();
        closeModal('renameModal');
        
        if (result.success) {
            showNotification('文件重命名成功', 'success');
            console.log('开始刷新文件列表...');
            await refreshFileList();
            console.log('文件列表刷新完成');
        } else {
            showNotification(result.message || '重命名失败', 'error');
        }
        
    } catch (error) {
        console.error('重命名过程中发生错误:', error);
        hideLoading();
        console.error('重命名失败:', error);
        showNotification('重命名失败，请重试', 'error');
    }
}

/**
 * 确认删除文件
 */
function confirmDeleteFile(fileId, fileName) {
    if (confirm(`确定要删除文件"${fileName}"吗？\n\n此操作不可撤销，同时会删除相关的检索数据。`)) {
        deleteFile(fileId);
    }
}

/**
 * 删除文件
 */
async function deleteFile(fileId) {
    try {
        showLoading('正在删除文件...');
        
        const result = await window.Http.delete(`/api/file/delete/${fileId}`);
        
        hideLoading();
        
        if (result.success) {
            showNotification('文件删除成功', 'success');
            await refreshFileList();
        } else {
            showNotification(result.message || '删除失败', 'error');
        }
        
    } catch (error) {
        hideLoading();
        console.error('删除文件失败:', error);
        showNotification('删除失败，请重试', 'error');
    }
}

// 创建全局FileManager对象
window.FileManager = {
    refreshFileList: refreshFileList,
    confirmRename: confirmRename,
    handleFileUpload: handleFileUpload,
    initializeFileManager: initializeFileManager,
    initializeFileUpload: initializeFileUpload
};

// 将函数暴露到全局作用域以便HTML的onclick事件调用
window.showFileDetail = showFileDetail;
window.showRenameModal = showRenameModal;
window.confirmRename = confirmRename;
window.confirmDeleteFile = confirmDeleteFile; 