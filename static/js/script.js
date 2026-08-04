(function() {
    'use strict';

    // ============================================
    // STATE
    // ============================================
    let currentDownload = null;
    let isDriveConnected = false;
    let selectedFolderId = null;
    let selectedFolderName = null;
    let currentVideoUrl = null;
    let totalDownloads = parseInt(localStorage.getItem('totalDownloads') || '0');

    // ============================================
    // DOM REFS
    // ============================================
    const urlInput = document.getElementById('urlInput');
    const previewBtn = document.getElementById('previewBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const resultDiv = document.getElementById('result');
    const previewContainer = document.getElementById('previewContainer');
    const previewContent = document.getElementById('previewContent');
    const saveGalleryBtn = document.getElementById('saveGalleryBtn');
    const saveDriveBtn = document.getElementById('saveDriveBtn');
    const bulkUrls = document.getElementById('bulkUrls');
    const bulkDownloadBtn = document.getElementById('bulkDownloadBtn');
    const clearBtn = document.getElementById('clearBtn');
    const bulkResult = document.getElementById('bulkResult');
    const connectDriveBtn = document.getElementById('connectDriveBtn');
    const selectFolderBtn = document.getElementById('selectFolderBtn');
    const createFolderBtn = document.getElementById('createFolderBtn');
    const refreshFoldersBtn = document.getElementById('refreshFoldersBtn');
    const driveStatusText = document.getElementById('driveStatusText');
    const folderList = document.getElementById('folderList');
    const totalDownloadsEl = document.getElementById('totalDownloads');

    // ============================================
    // INIT
    // ============================================
    if (totalDownloadsEl) totalDownloadsEl.textContent = totalDownloads;
    checkDriveStatus();

    // ============================================
    // UTILITY FUNCTIONS
    // ============================================
    function showResult(message, type, container) {
        container = container || resultDiv;
        container.className = type;
        container.style.display = 'block';
        container.innerHTML = message;
        if (window.innerWidth < 600) {
            container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    function hideResult(container) {
        container = container || resultDiv;
        container.style.display = 'none';
        container.className = '';
        container.innerHTML = '';
    }

    function getSaveOption() {
        const radios = document.querySelectorAll('input[name="saveTo"]');
        for (let radio of radios) {
            if (radio.checked) return radio.value;
        }
        return 'local';
    }

    function formatBytes(bytes) {
        if (!bytes || bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function setLoading(btn, loading) {
        if (loading) {
            btn.classList.add('loading');
            btn.disabled = true;
        } else {
            btn.classList.remove('loading');
            btn.disabled = false;
        }
    }

    function updateTotalDownloads() {
        totalDownloads++;
        localStorage.setItem('totalDownloads', totalDownloads);
        if (totalDownloadsEl) totalDownloadsEl.textContent = totalDownloads;
    }

    function escapeHtml(text) {
        if (!text) return 'Unknown';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Triggers a real browser file download (lands in the device's own
    // Downloads folder). This is the ONLY way a web app can get a file
    // onto the user's phone/laptop - there is no API that lets a server
    // write directly into someone's personal Gallery/Photos app.
    function triggerBrowserDownload(filename) {
        const a = document.createElement('a');
        a.href = '/download-file/' + encodeURIComponent(filename);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    // ============================================
    // CHECK DRIVE STATUS
    // ============================================
    async function checkDriveStatus() {
        try {
            const response = await fetch('/drive/status');
            const data = await response.json();

            const dot = document.querySelector('.drive-status .status-dot');
            if (data.connected) {
                isDriveConnected = true;
                driveStatusText.textContent = 'Connected to ' + data.email;
                if (dot) dot.className = 'status-dot connected';
                connectDriveBtn.textContent = '✅ Connected';
                connectDriveBtn.disabled = true;

                // Sync selected folder from server (persists across reloads
                // and server restarts, since it's now saved server-side).
                if (data.selected_folder_id) {
                    selectedFolderId = data.selected_folder_id;
                    selectedFolderName = data.selected_folder_name;
                }
            } else {
                isDriveConnected = false;
                driveStatusText.textContent = 'Not connected';
                if (dot) dot.className = 'status-dot disconnected';
                connectDriveBtn.textContent = '🔗 Connect';
                connectDriveBtn.disabled = false;
            }
        } catch (error) {
            console.error('Drive status check failed:', error);
        }
    }

    // ============================================
    // PREVIEW FUNCTION
    // ============================================
    async function previewVideo() {
        const url = urlInput.value.trim();
        if (!url) {
            showResult('Please enter a URL', 'error');
            return;
        }

        setLoading(previewBtn, true);
        showResult('⏳ Loading preview...', 'loading');

        try {
            const response = await fetch('/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            const data = await response.json();

            if (data.status === 'success') {
                currentVideoUrl = url;
                showPreview(data);
                showResult('✅ Video preview loaded', 'success');
            } else {
                showResult('❌ ' + (data.message || 'Preview failed'), 'error');
            }
        } catch (error) {
            showResult('❌ Error: ' + error.message, 'error');
        } finally {
            setLoading(previewBtn, false);
        }
    }

    function showPreview(data) {
        previewContainer.classList.add('active');

        let html = '';

        // Video player or thumbnail
        if (data.video_url) {
            html += '<video controls autoplay muted playsinline>';
            html += '<source src="' + data.video_url + '" type="video/mp4">';
            html += 'Your browser does not support the video tag.';
            html += '</video>';
        } else if (data.thumbnail) {
            html += '<img src="' + data.thumbnail + '" class="preview-thumbnail" alt="Thumbnail" loading="lazy" />';
        } else {
            html += '<div style="padding:20px;text-align:center;color:var(--text-muted);">No preview available</div>';
        }

        // Info
        html += '<div class="preview-info">';
        if (data.title) {
            html += '<div class="info-item"><label>Title</label><span>' + escapeHtml(data.title) + '</span></div>';
        }
        if (data.uploader) {
            html += '<div class="info-item"><label>Uploader</label><span>' + escapeHtml(data.uploader) + '</span></div>';
        }
        if (data.duration) {
            const mins = Math.floor(data.duration / 60);
            const secs = data.duration % 60;
            html += '<div class="info-item"><label>Duration</label><span>' + mins + ':' + String(secs).padStart(2, '0') + '</span></div>';
        }
        if (data.views) {
            html += '<div class="info-item"><label>Views</label><span>' + Number(data.views).toLocaleString() + '</span></div>';
        }
        if (data.likes) {
            html += '<div class="info-item"><label>Likes</label><span>' + Number(data.likes).toLocaleString() + '</span></div>';
        }
        if (data.platform) {
            html += '<div class="info-item"><label>Platform</label><span>' + data.platform.toUpperCase() + '</span></div>';
        }
        html += '</div>';

        previewContent.innerHTML = html;

        currentDownload = {
            title: data.title || 'Video',
            uploader: data.uploader || 'Unknown',
            platform: data.platform || 'unknown',
            filename: null
        };
    }

    // ============================================
    // DOWNLOAD FUNCTION
    // ============================================
    async function downloadVideo() {
        const url = urlInput.value.trim();
        if (!url) {
            showResult('Please enter a URL', 'error');
            return;
        }

        const saveTo = getSaveOption();
        setLoading(downloadBtn, true);
        showResult('⏳ Downloading... Please wait', 'loading');

        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, save_to: saveTo })
            });

            const data = await response.json();

            // 'partial_success' happens when the video downloaded fine on the
            // server but a follow-up step (e.g. Drive upload) failed - still
            // worth showing the file to the user instead of a bare error.
            if (data.status === 'success' || data.status === 'partial_success') {
                updateTotalDownloads();

                const isPartial = data.status === 'partial_success';
                let html = '<strong>' + (isPartial ? '⚠️ ' : '✅ ') + (data.message || 'Download successful') + '</strong>';

                // Metadata
                html += '<div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:6px;">';
                if (data.title) html += '<div style="background:rgba(255,255,255,0.04);padding:6px 8px;border-radius:6px;"><small style="color:var(--text-muted);">Title</small><br><strong style="font-size:13px;">' + escapeHtml(data.title) + '</strong></div>';
                if (data.uploader) html += '<div style="background:rgba(255,255,255,0.04);padding:6px 8px;border-radius:6px;"><small style="color:var(--text-muted);">Uploader</small><br><strong style="font-size:13px;">' + escapeHtml(data.uploader) + '</strong></div>';
                if (data.platform) html += '<div style="background:rgba(255,255,255,0.04);padding:6px 8px;border-radius:6px;"><small style="color:var(--text-muted);">Platform</small><br><strong style="font-size:13px;">' + data.platform.toUpperCase() + '</strong></div>';
                if (data.size) html += '<div style="background:rgba(255,255,255,0.04);padding:6px 8px;border-radius:6px;"><small style="color:var(--text-muted);">Size</small><br><strong style="font-size:13px;">' + formatBytes(data.size) + '</strong></div>';
                html += '</div>';

                // Gallery: actually trigger the browser download here, since
                // there is no server-side "gallery" to save into.
                if (saveTo === 'gallery' && data.filename) {
                    triggerBrowserDownload(data.filename);
                    html += '<div style="color:var(--success);margin-top:8px;">🖼️ File download started — check your device\'s Downloads/Gallery.</div>';
                } else if (data.gallery && data.gallery.status === 'success') {
                    html += '<div style="color:var(--success);margin-top:8px;">🖼️ ' + data.gallery.message + '</div>';
                }

                // Drive upload result
                if (data.drive) {
                    if (data.drive.status === 'success') {
                        html += '<div style="color:#4caf50;margin-top:8px;">☁️ ' + data.drive.message + '</div>';
                        if (data.drive.web_link) {
                            html += '<a href="' + data.drive.web_link + '" target="_blank" rel="noopener" style="color:#4caf50;display:inline-block;margin-top:4px;">🔗 View in Drive</a>';
                        }
                    } else {
                        html += '<div style="color:var(--error);margin-top:8px;">☁️ Drive upload failed: ' + escapeHtml(data.drive.message) + '</div>';
                    }
                }

                // Download buttons
                if (data.filename) {
                    currentDownload.filename = data.filename;
                    html += '<div style="margin-top:10px;display:flex;flex-direction:column;gap:6px;">';
                    html += '<button class="btn btn-success btn-sm" onclick="window.downloadFile(\'' + data.filename + '\')">⬇️ Download File</button>';
                    html += '<button class="btn btn-gallery btn-sm" onclick="window.saveToGallery(\'' + data.filename + '\')">🖼️ Save to Gallery</button>';
                    html += '<button class="btn btn-drive btn-sm" onclick="window.uploadToDrive(\'' + data.filename + '\')">☁️ Upload to Drive</button>';
                    html += '</div>';
                }

                showResult(html, isPartial ? 'info' : 'success');
            } else {
                showResult('❌ ' + (data.message || 'Download failed'), 'error');
            }
        } catch (error) {
            showResult('❌ Error: ' + error.message, 'error');
        } finally {
            setLoading(downloadBtn, false);
        }
    }

    // ============================================
    // FILE OPERATIONS (Global for onclick)
    // ============================================
    window.downloadFile = function(filename) {
        triggerBrowserDownload(filename);
    };

    // "Save to Gallery" = trigger an actual browser download. A web app
    // cannot write into a phone's Gallery/Photos app directly; the browser
    // download is the real save. On Android, Chrome downloads land in
    // Downloads and video files are usually picked up by the gallery app.
    window.saveToGallery = function(filename) {
        triggerBrowserDownload(filename);
        showResult('🖼️ File download started — check your device\'s Downloads/Gallery.', 'success');
    };

    window.uploadToDrive = async function(filename) {
        if (!selectedFolderId) {
            showResult('Please select a Drive folder first', 'error');
            return;
        }

        try {
            showResult('⏳ Uploading to Drive...', 'loading');
            const response = await fetch('/drive/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, folder_id: selectedFolderId })
            });
            const data = await response.json();
            if (data.status === 'success') {
                let msg = '✅ ' + data.message;
                if (data.web_link) {
                    msg += '<br><a href="' + data.web_link + '" target="_blank" rel="noopener" style="color:#4caf50;">🔗 View in Drive</a>';
                }
                showResult(msg, 'success');
            } else {
                showResult('❌ ' + data.message, 'error');
            }
        } catch (error) {
            showResult('❌ ' + error.message, 'error');
        }
    };

    // ============================================
    // GOOGLE DRIVE FUNCTIONS
    // ============================================
    async function connectDrive() {
        showResult('⏳ Connecting to Google Drive...', 'loading');
        setLoading(connectDriveBtn, true);

        try {
            const response = await fetch('/drive/auth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });

            const data = await response.json();

            if (data.status === 'success' && data.auth_url) {
                const authWindow = window.open(data.auth_url, '_blank', 'width=600,height=700');
                if (!authWindow) {
                    showResult(
                        '<strong>🔗 Please authorize manually:</strong><br>' +
                        '<a href="' + data.auth_url + '" target="_blank" rel="noopener" style="color:#4caf50;word-break:break-all;">' + data.auth_url + '</a>' +
                        '<br><br><button class="btn btn-success btn-sm" onclick="window.checkDriveStatus()">✅ Verify Connection</button>',
                        'info'
                    );
                } else {
                    showResult('✅ Authorization window opened. Complete the process and then click "Verify".', 'success');
                    setTimeout(checkDriveStatus, 10000);
                }
            } else if (data.status === 'success' && data.connected) {
                showResult('✅ ' + data.message, 'success');
                checkDriveStatus();
                listFolders();
            } else {
                showResult('❌ ' + (data.message || 'Something went wrong'), 'error');
            }
        } catch (error) {
            showResult('❌ Error: ' + error.message, 'error');
        } finally {
            setLoading(connectDriveBtn, false);
        }
    }

    async function listFolders() {
        if (!isDriveConnected) {
            showResult('Please connect to Google Drive first', 'error');
            return;
        }

        setLoading(selectFolderBtn, true);

        try {
            const response = await fetch('/drive/folders');
            const data = await response.json();

            if (data.status === 'success' && data.folders) {
                if (data.folders.length > 0) {
                    let html = '';
                    data.folders.forEach(function(folder) {
                        const isSelected = selectedFolderId === folder.id;
                        html += '<div class="folder-item">';
                        html += '<div class="folder-name">';
                        html += '<span class="icon">📁</span> ' + folder.name;
                        if (isSelected) html += '<span class="selected-badge">✅ Selected</span>';
                        html += '</div>';
                        html += '<div class="folder-actions">';
                        if (!isSelected) {
                            html += '<button class="btn btn-sm btn-secondary" onclick="window.selectFolder(\'' + folder.id + '\',\'' + folder.name + '\')">Select</button>';
                        }
                        html += '<span class="text-muted text-xs">' + new Date(folder.createdTime).toLocaleDateString() + '</span>';
                        html += '</div></div>';
                    });
                    folderList.innerHTML = html;
                } else {
                    folderList.innerHTML = '<div class="folder-empty"><span class="icon">📁</span><p>No folders found</p><span class="text-sm text-muted">Create a new folder to get started</span></div>';
                }
            } else {
                folderList.innerHTML = '<div class="folder-empty"><span class="icon">❌</span><p>' + (data.message || 'Failed to load folders') + '</p></div>';
            }
        } catch (error) {
            folderList.innerHTML = '<div class="folder-empty"><span class="icon">❌</span><p>Error: ' + error.message + '</p></div>';
        } finally {
            setLoading(selectFolderBtn, false);
        }
    }

    window.selectFolder = async function(folderId, folderName) {
        try {
            const response = await fetch('/drive/folder/select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_id: folderId, folder_name: folderName })
            });
            const data = await response.json();
            if (data.status === 'success') {
                selectedFolderId = folderId;
                selectedFolderName = folderName;
                showResult('✅ ' + data.message, 'success');
                listFolders();
            } else {
                showResult('❌ ' + data.message, 'error');
            }
        } catch (error) {
            showResult('❌ ' + error.message, 'error');
        }
    };

    async function createFolder() {
        const folderName = prompt('Enter folder name:');
        if (!folderName) return;

        try {
            const response = await fetch('/drive/folder/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_name: folderName })
            });
            const data = await response.json();
            if (data.status === 'success') {
                showResult('✅ Folder created: ' + data.folder_name, 'success');
                listFolders();
            } else {
                showResult('❌ ' + data.message, 'error');
            }
        } catch (error) {
            showResult('❌ ' + error.message, 'error');
        }
    }

    // ============================================
    // BULK DOWNLOAD
    // ============================================
    async function bulkDownload() {
        const urls = bulkUrls.value.split('\n').filter(function(u) { return u.trim(); });
        if (urls.length === 0) {
            showResult('Please enter at least one URL', 'error', bulkResult);
            return;
        }

        const saveTo = getSaveOption();
        setLoading(bulkDownloadBtn, true);
        showResult('⏳ Downloading ' + urls.length + ' items...', 'loading', bulkResult);

        try {
            const response = await fetch('/bulk-download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ urls, save_to: saveTo })
            });

            const data = await response.json();

            if (data.status === 'success') {
                let html = '<strong>✅ ' + data.message + '</strong>';
                if (data.results) {
                    const successes = data.results.filter(function(r) { return r.status === 'success' || r.status === 'partial_success'; }).length;
                    const errors = data.results.filter(function(r) { return r.status === 'error'; }).length;
                    html += '<div style="margin-top:10px;display:flex;gap:16px;flex-wrap:wrap;">';
                    html += '<span style="color:var(--success);">✅ Success: ' + successes + '</span>';
                    html += '<span style="color:var(--error);">❌ Failed: ' + errors + '</span>';
                    html += '</div>';
                    html += '<div style="margin-top:10px;max-height:200px;overflow-y:auto;">';
                    data.results.forEach(function(r) {
                        const icon = r.status === 'error' ? '❌' : (r.status === 'partial_success' ? '⚠️' : '✅');
                        const color = r.status === 'error' ? 'var(--error)' : (r.status === 'partial_success' ? '#e0a800' : 'var(--success)');
                        html += '<div style="padding:4px 0;border-bottom:1px solid var(--border);font-size:12px;color:' + color + ';word-break:break-word;">' + icon + ' ' + r.message + '</div>';

                        // In bulk mode with "gallery" selected, auto-trigger a
                        // download for each successfully fetched file too.
                        if (saveTo === 'gallery' && r.filename && (r.status === 'success' || r.status === 'partial_success')) {
                            triggerBrowserDownload(r.filename);
                        }
                    });
                    html += '</div>';
                }
                showResult(html, 'success', bulkResult);
            } else {
                showResult('❌ ' + data.message, 'error', bulkResult);
            }
        } catch (error) {
            showResult('❌ ' + error.message, 'error', bulkResult);
        } finally {
            setLoading(bulkDownloadBtn, false);
        }
    }

    // ============================================
    // CLEAR DOWNLOADS
    // ============================================
    async function clearDownloads() {
        if (!confirm('Are you sure you want to clear all downloads?')) return;
        try {
            const response = await fetch('/clear-downloads', { method: 'POST' });
            const data = await response.json();
            showResult(data.status === 'success' ? '✅ ' + data.message : '❌ ' + data.message,
                      data.status === 'success' ? 'success' : 'error');
        } catch (error) {
            showResult('❌ ' + error.message, 'error');
        }
    }

    // ============================================
    // EXPOSE FUNCTIONS TO WINDOW
    // ============================================
    window.checkDriveStatus = checkDriveStatus;
    window.selectFolder = window.selectFolder;
    window.downloadFile = window.downloadFile;
    window.saveToGallery = window.saveToGallery;
    window.uploadToDrive = window.uploadToDrive;

    // ============================================
    // EVENT LISTENERS
    // ============================================
    if (previewBtn) previewBtn.addEventListener('click', previewVideo);
    if (downloadBtn) downloadBtn.addEventListener('click', downloadVideo);

    if (urlInput) {
        urlInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') downloadVideo();
        });
        urlInput.addEventListener('input', function() {
            if (previewContainer.classList.contains('active')) {
                previewContainer.classList.remove('active');
            }
        });
    }

    if (bulkDownloadBtn) bulkDownloadBtn.addEventListener('click', bulkDownload);
    if (clearBtn) clearBtn.addEventListener('click', clearDownloads);

    if (connectDriveBtn) connectDriveBtn.addEventListener('click', connectDrive);
    if (selectFolderBtn) selectFolderBtn.addEventListener('click', listFolders);
    if (createFolderBtn) createFolderBtn.addEventListener('click', createFolder);
    if (refreshFoldersBtn) refreshFoldersBtn.addEventListener('click', listFolders);

    if (saveGalleryBtn) {
        saveGalleryBtn.addEventListener('click', function() {
            if (currentDownload && currentDownload.filename) {
                window.saveToGallery(currentDownload.filename);
            } else {
                showResult('Please download a video first', 'error');
            }
        });
    }

    if (saveDriveBtn) {
        saveDriveBtn.addEventListener('click', async function() {
            if (currentDownload && currentDownload.filename) {
                await window.uploadToDrive(currentDownload.filename);
            } else {
                showResult('Please download a video first', 'error');
            }
        });
    }

    // ============================================
    // KEYBOARD SHORTCUTS
    // ============================================
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            downloadVideo();
        }
        if (e.key === 'Escape') {
            hideResult();
            hideResult(bulkResult);
        }
    });

    // ============================================
    // CONSOLE LOG
    // ============================================
    console.log('🌿 Social Downloader Pro v2.1 (Dark Green Edition)');
    console.log('💾 Save options: Local | Gallery (browser download) | Google Drive');
    console.log('📊 Total downloads:', totalDownloads);
    console.log('🔗 Connect Drive to enable cloud storage');

})();
