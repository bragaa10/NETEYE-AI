/**
 * NetEye — Main JavaScript
 * Handles real-time logs (SSE) and dashboard interactions.
 */

document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('toggle-assistant');
    const logsContainer = document.getElementById('logs-container');
    const clearLogsBtn = document.getElementById('clear-terminal');

    let eventSource = null;
    let reconnectAttempts = 0;
    let reconnectTimer = null;

    // ------------------------------------------------------------------
    // CONTROLO DO ASSISTENTE
    // ------------------------------------------------------------------

    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const isRunning = toggleBtn.classList.contains('btn-danger');

            if (!isRunning) {
                // Iniciar
                fetch('/api/start')
                    .then(r => r.json())
                    .then(data => {
                        if (data.status === 'started' || data.status === 'already_running') {
                            setAssistantState(true);
                            startLogStream();
                        } else if (data.status === 'error') {
                            alert("Erro ao iniciar o NetEye: " + data.message);
                            setAssistantState(false);
                        }
                    })
                    .catch(err => {
                        alert("Falha na comunicação com o servidor.");
                        console.error(err);
                    });


            } else {
                // Parar
                fetch('/api/stop')
                    .then(r => r.json())
                    .then(data => {
                        if (data.status === 'stopped') {
                            setAssistantState(false);
                            stopLogStream();
                        }
                    });
            }
        });
    }

    function setAssistantState(running) {
        if (!toggleBtn) return;
        const statusIndicator = document.getElementById('status-indicator');
        
        if (running) {
            toggleBtn.textContent = 'Parar NetEye';
            toggleBtn.classList.remove('btn-primary');
            toggleBtn.classList.add('btn-danger');
            if (statusIndicator) statusIndicator.classList.remove('d-none');
            updateIndicator('browser', true, 'Aberto');
            updateIndicator('mic', true, 'A escutar...');
        } else {
            toggleBtn.textContent = 'Iniciar NetEye';
            toggleBtn.classList.remove('btn-danger');
            toggleBtn.classList.add('btn-primary');
            if (statusIndicator) statusIndicator.classList.add('d-none');
            updateIndicator('browser', false, 'Fechado');
            updateIndicator('mic', false, 'Inativo');
        }
    }

    function updateIndicator(id, active, text) {
        const item = document.getElementById(`status-${id}`);
        if (!item) return;
        const dot = item.querySelector('.status-dot');
        const val = item.querySelector('.value');
        
        if (active) {
            dot.classList.add('online');
        } else {
            dot.classList.remove('online');
        }
        val.textContent = text;
    }

    // ------------------------------------------------------------------
    // LOGS EM TEMPO REAL (SSE)
    // ------------------------------------------------------------------

    function startLogStream() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }

        eventSource = new EventSource('/logs');
        reconnectAttempts = 0;

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                appendLog(data.time, data.text);
            } catch (err) {
                console.error('Falha ao analisar mensagem SSE:', err, event.data);
            }
        };

        eventSource.onerror = () => {
            console.log('SSE Connection error. Tentando reconexão...');
            scheduleReconnect();
            eventSource.close();
            eventSource = null;
        };
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectAttempts += 1;
        const backoff = Math.min(30000, 1000 * Math.pow(2, reconnectAttempts));
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            startLogStream();
        }, backoff);
    }

    function stopLogStream() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    }

    function appendLog(time, text) {
        if (!logsContainer) return;

        const line = document.createElement('div');
        line.className = 'log-line';
        
        // Detetar tipo de log por conteúdo
        const lower = text.toLowerCase();
        if (lower.includes('erro') || lower.includes('failed') || lower.includes('exception')) {
            line.classList.add('error');
        } else if (lower.includes('aviso') || lower.includes('warning') || lower.includes('waiting')) {
            line.classList.add('warning');
        } else if (lower.includes('---')) {
            line.classList.add('system');
        }

        line.innerHTML = `
            <span class="log-time">${time}</span>
            <span class="log-text">${escapeHtml(text)}</span>
        `;
        
        logsContainer.appendChild(line);
        logsContainer.scrollTop = logsContainer.scrollHeight;
    }

    if (clearLogsBtn) {
        clearLogsBtn.onclick = () => {
            logsContainer.innerHTML = '<div class="log-line system">Terminal limpo.</div>';
        };
    }

    function escapeHtml(text) {
        const p = document.createElement('p');
        p.textContent = text;
        return p.innerHTML;
    }

    // Se já estiver a correr ao carregar a página (reconectar SSE)
    if (toggleBtn && toggleBtn.classList.contains('btn-danger')) {
        startLogStream();
    }
});
