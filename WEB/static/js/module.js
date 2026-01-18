// Module Page JavaScript - Form Handling and SSE

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('moduleForm');
    const submitBtn = document.getElementById('submitBtn');
    const progressSection = document.getElementById('progressSection');
    const progressFill = document.getElementById('progressFill');
    const progressMessages = document.getElementById('progressMessages');
    const progressStatus = document.getElementById('progressStatus');

    if (!form) return;

    form.addEventListener('submit', async function (e) {
        e.preventDefault();

        // Disable submit button
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="btn-icon">⏳</span> Running...';

        // Check if form has file inputs
        const fileInputs = form.querySelectorAll('input[type="file"]');
        const hasFiles = Array.from(fileInputs).some(input => input.files.length > 0);

        let requestData;
        let requestHeaders = {};

        if (hasFiles) {
            // Use FormData for file uploads
            const formData = new FormData(form);

            // Add unchecked checkboxes
            const checkboxes = form.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => {
                if (!formData.has(cb.name)) {
                    formData.append(cb.name, 'false');
                }
            });

            requestData = formData;
            // Don't set Content-Type, let browser set it with boundary
        } else {
            // Use JSON for non-file submissions
            const formData = new FormData(form);
            const data = {};

            for (let [key, value] of formData.entries()) {
                // Handle checkboxes
                const input = form.elements[key];
                if (input.type === 'checkbox') {
                    data[key] = input.checked;
                } else if (input.type === 'number') {
                    data[key] = parseInt(value) || 0;
                } else {
                    data[key] = value;
                }
            }

            // Also check for unchecked checkboxes
            const checkboxes = form.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => {
                if (!formData.has(cb.name)) {
                    data[cb.name] = false;
                }
            });

            requestData = JSON.stringify(data);
            requestHeaders['Content-Type'] = 'application/json';
        }

        try {
            // Show progress section
            progressSection.style.display = 'block';
            progressSection.scrollIntoView({ behavior: 'smooth' });

            // Start execution
            const response = await fetch(`/api/execute/${moduleName}`, {
                method: 'POST',
                headers: requestHeaders,
                body: requestData
            });

            const result = await response.json();

            if (!result.success) {
                throw new Error(result.error || 'Execution failed');
            }

            const taskId = result.task_id;
            progressStatus.innerHTML = '<span style="color: var(--success);">✅ Task started successfully!</span>';
            progressFill.style.width = '100%';

            // Show success message
            addProgressMessage(`Task ${taskId.substring(0, 8)}... created`, 'success');
            addProgressMessage('Redirecting to dashboard...', 'info');

            // Redirect to dashboard to monitor all tasks
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 1500);

        } catch (error) {
            console.error('Error:', error);
            progressStatus.innerHTML = `<span style="color: var(--error);">Error: ${error.message}</span>`;
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<span class="btn-icon">▶</span> Run Module';
        }
    });

    function startProgressMonitoring(taskId) {
        const eventSource = new EventSource(`/api/stream/${taskId}`);
        let progressValue = 10;

        // Simulate progress
        progressFill.style.width = progressValue + '%';

        eventSource.onmessage = function (event) {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'status':
                    progressStatus.textContent = data.message;
                    progressValue = Math.min(progressValue + 10, 90);
                    progressFill.style.width = progressValue + '%';
                    addProgressMessage(data.message, 'info');
                    break;

                case 'complete':
                    progressFill.style.width = '100%';
                    progressStatus.innerHTML = '<span style="color: var(--success);">✅ Execution completed!</span>';
                    addProgressMessage('Execution completed successfully', 'success');
                    eventSource.close();

                    // Redirect to results page after a short delay
                    setTimeout(() => {
                        window.location.href = `/results/${taskId}`;
                    }, 1500);
                    break;

                case 'error':
                    progressFill.style.width = '100%';
                    progressFill.style.background = 'var(--error)';
                    progressStatus.innerHTML = `<span style="color: var(--error);">❌ Error: ${data.message}</span>`;
                    addProgressMessage(`Error: ${data.message}`, 'error');
                    eventSource.close();

                    // Re-enable submit button
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<span class="btn-icon">▶</span> Run Module';
                    break;

                case 'heartbeat':
                    // Just keep connection alive
                    break;

                case 'done':
                    eventSource.close();
                    break;

                case 'timeout':
                    progressStatus.innerHTML = '<span style="color: var(--warning);">⚠️ Execution timeout</span>';
                    addProgressMessage('Task execution timeout', 'warning');
                    eventSource.close();
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<span class="btn-icon">▶</span> Run Module';
                    break;
            }
        };

        eventSource.onerror = function (error) {
            console.error('SSE Error:', error);
            eventSource.close();
            progressStatus.innerHTML = '<span style="color: var(--error);">Connection error. Checking status...</span>';

            // Poll for status instead
            pollTaskStatus(taskId);
        };
    }

    function addProgressMessage(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const color = {
            'info': 'var(--text-secondary)',
            'success': 'var(--success)',
            'error': 'var(--error)',
            'warning': 'var(--warning)'
        }[type] || 'var(--text-secondary)';

        const messageEl = document.createElement('div');
        messageEl.style.color = color;
        messageEl.style.marginBottom = '0.5rem';
        messageEl.textContent = `[${timestamp}] ${message}`;

        progressMessages.appendChild(messageEl);
        progressMessages.scrollTop = progressMessages.scrollHeight;
    }

    async function pollTaskStatus(taskId) {
        const maxAttempts = 60; // 5 minutes
        let attempts = 0;

        const interval = setInterval(async () => {
            attempts++;

            if (attempts > maxAttempts) {
                clearInterval(interval);
                progressStatus.innerHTML = '<span style="color: var(--error);">Timeout waiting for results</span>';
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<span class="btn-icon">▶</span> Run Module';
                return;
            }

            try {
                const response = await fetch(`/api/status/${taskId}`);
                const status = await response.json();

                if (status.status === 'complete') {
                    clearInterval(interval);
                    progressFill.style.width = '100%';
                    progressStatus.innerHTML = '<span style="color: var(--success);">✅ Execution completed!</span>';

                    setTimeout(() => {
                        window.location.href = `/results/${taskId}`;
                    }, 1500);
                } else if (status.status === 'error') {
                    clearInterval(interval);
                    progressFill.style.width = '100%';
                    progressFill.style.background = 'var(--error)';
                    progressStatus.innerHTML = '<span style="color: var(--error);">❌ Execution failed</span>';
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<span class="btn-icon">▶</span> Run Module';
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 5000); // Poll every 5 seconds
    }
});
