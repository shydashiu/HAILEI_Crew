class SinglePersonaChat {
    constructor() {
        this.apiBaseUrl = 'http://localhost:8002';
        this.wsBaseUrl = 'ws://localhost:8000';
        this.websocket = null;
        this.threadId = null;
        this.websocketPath = null;
        this.connectionAttempts = 0;
        this.reconnectTimer = null;
        this.pendingTurns = new Map();
        this.handledAssistantMessages = new Set();
        this.activeDecision = null;
        this.stillWorkingDelay = 15000;

        this.initializeElements();
        this.bindEvents();
        this.setConnectionStatus('offline', 'Offline');
    }

    initializeElements() {
        this.startScreen = document.getElementById('start-screen');
        this.buildScreen = document.getElementById('build-screen');
        this.newSessionBtn = document.getElementById('new-session-btn');
        this.threadBadge = document.getElementById('thread-badge');
        this.statusDot = document.getElementById('status-dot');
        this.statusLabel = document.getElementById('status-label');
        this.connectionBanner = document.getElementById('connection-banner');
        this.connectionBannerText = document.getElementById('connection-banner-text');
        this.messages = document.getElementById('messages');
        this.typingLiveRegion = document.getElementById('typing-live-region');
        this.composer = document.getElementById('composer');
        this.messageInput = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
    }

    bindEvents() {
        this.newSessionBtn.addEventListener('click', () => {
            this.startNewSession();
        });

        this.composer.addEventListener('submit', (event) => {
            event.preventDefault();
            this.sendMessage();
        });

        this.messageInput.addEventListener('input', () => {
            this.sendBtn.disabled = !this.messageInput.value.trim();
        });
    }

    setConnectionStatus(state, label) {
        this.statusDot.classList.remove('online', 'offline', 'connecting');
        this.statusDot.classList.add(state);
        this.statusLabel.textContent = label;
    }

    async startNewSession() {
        this.setConnectionStatus('connecting', 'Starting session…');
        this.newSessionBtn.disabled = true;
        this.hideConnectionBanner();

        try {
            const response = await fetch(`${this.apiBaseUrl}/frontend/new-session`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`Failed to start session (${response.status})`);
            }

            const payload = await response.json();
            this.threadId = payload.session_id;
            this.websocketPath = payload.websocket_url;
            this.threadBadge.textContent = this.threadId.slice(0, 8);

            this.showBuildScreen();
            this.appendWelcomeMessage();

            await this.connectWebSocket();
        } catch (error) {
            console.error('Unable to create session', error);
            this.setConnectionStatus('offline', 'Offline');
            this.newSessionBtn.disabled = false;
            this.showConnectionBanner('Something went wrong. Try again.');
        }
    }

    showBuildScreen() {
        this.startScreen.classList.add('hidden');
        this.buildScreen.classList.remove('hidden');
    }

    appendWelcomeMessage() {
        const turn = document.createElement('div');
        turn.className = 'turn';
        const message = this.buildAssistantMessage('Welcome! I am your HAILEI Assistant. Ask anything about designing your course and I will respond in a single voice.');
        turn.appendChild(message);
        this.messages.appendChild(turn);
    }

    async connectWebSocket() {
        if (!this.threadId || !this.websocketPath) {
            return;
        }

        const wsUrl = `${this.wsBaseUrl}${this.websocketPath}`;
        this.setConnectionStatus('connecting', 'Connecting…');
        this.showConnectionBanner('Connecting to live conversation…');

        if (this.websocket) {
            this.websocket.close(1000, 'Reconnecting');
        }

        this.websocket = new WebSocket(wsUrl);

        this.websocket.onopen = () => {
            this.connectionAttempts = 0;
            this.setConnectionStatus('online', 'Connected');
            this.hideConnectionBanner();
            this.enableComposer();
            this.clearReconnectTimer();
        };

        this.websocket.onmessage = (event) => {
            this.processServerEvent(event.data);
        };

        this.websocket.onerror = (event) => {
            console.error('WebSocket error', event);
            this.setConnectionStatus('offline', 'Connection issue');
            this.showConnectionBanner('Something went wrong. Try again.');
        };

        this.websocket.onclose = (event) => {
            console.warn('WebSocket closed', event.code, event.reason);
            this.disableComposer();
            this.setConnectionStatus('offline', 'Disconnected');
            this.showConnectionBanner('Connection lost. Reconnecting…');
            this.scheduleReconnect();
        };
    }

    scheduleReconnect() {
        if (!this.threadId) {
            return;
        }

        if (this.reconnectTimer) {
            return;
        }

        const delay = Math.min(10000, 1000 * Math.pow(2, this.connectionAttempts));
        this.connectionAttempts += 1;
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connectWebSocket();
        }, delay);
    }

    clearReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    enableComposer() {
        this.messageInput.disabled = false;
        this.messageInput.placeholder = 'Type your message...';
        this.sendBtn.disabled = !this.messageInput.value.trim();
        this.messageInput.focus();
    }

    disableComposer() {
        this.messageInput.disabled = true;
        this.sendBtn.disabled = true;
        this.messageInput.placeholder = 'Reconnecting…';
    }

    showConnectionBanner(message) {
        this.connectionBannerText.textContent = message;
        this.connectionBanner.classList.remove('hidden');
    }

    hideConnectionBanner() {
        this.connectionBanner.classList.add('hidden');
        this.connectionBannerText.textContent = '';
    }

    sendMessage() {
        const text = this.messageInput.value.trim();
        if (!text) {
            return;
        }

        if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
            this.showConnectionBanner('Still connecting… please wait.');
            return;
        }

        this.messageInput.value = '';
        this.sendBtn.disabled = true;
        this.sendMessageText(text);
        this.messageInput.focus();
    }

    sendMessageText(text) {
        if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
            this.showConnectionBanner('Still connecting… please wait.');
            return;
        }

        const messageId = this.generateMessageId();
        const turn = document.createElement('div');
        turn.className = 'turn';
        turn.dataset.turnId = messageId;

        const userMessage = this.buildUserMessage(text);
        turn.appendChild(userMessage);

        const indicator = this.buildTypingIndicator();
        turn.appendChild(indicator);

        this.messages.appendChild(turn);
        this.scrollToBottom();
        this.announceTyping();

        const pending = {
            id: messageId,
            text,
            turnElement: turn,
            indicator,
            stillWorkingTimer: this.startStillWorkingTimer(indicator),
        };

        this.pendingTurns.set(messageId, pending);

        const payload = {
            type: 'user_message',
            thread_id: this.threadId,
            message_id: messageId,
            text,
        };

        try {
            this.websocket.send(JSON.stringify(payload));
        } catch (error) {
            console.error('Failed to send message', error);
            this.showConnectionBanner('Something went wrong. Try again.');
        }
    }

    processServerEvent(raw) {
        let data = raw;
        try {
            data = JSON.parse(raw);
        } catch (error) {
            console.warn('Received non-JSON payload', raw);
            data = raw;
        }

        const event = this.normalizeEvent(data);
        if (!event) {
            return;
        }

        switch (event.kind) {
            case 'status':
                this.handleStatusEvent(event);
                break;
            case 'final':
                this.handleFinalEvent(event);
                break;
            case 'error':
                this.handleErrorEvent(event);
                break;
            case 'system':
                this.appendSystemMessage(event.text);
                break;
            default:
                break;
        }
    }

    normalizeEvent(message) {
        if (!message) {
            return null;
        }

        if (typeof message === 'string') {
            return {
                kind: 'final',
                assistantMessageId: this.generateAssistantMessageId(),
                text: message,
                artifacts: [],
                replyTo: this.oldestPendingTurnId(),
            };
        }

        switch (message.type) {
            case 'status':
                return {
                    kind: 'status',
                    messageId: message.message_id || message.turn_id || message.reply_to || null,
                    text: message.text || message.message || '',
                };
            case 'final':
                return {
                    kind: 'final',
                    assistantMessageId: message.message_id || message.id || this.generateAssistantMessageId(),
                    text: message.text || message.content || '',
                    artifacts: message.artifacts || [],
                    replyTo: message.reply_to || message.user_message_id || null,
                };
            case 'error':
                return {
                    kind: 'error',
                    messageId: message.message_id || message.turn_id || message.reply_to || null,
                    hint: message.hint || message.text || 'Something went wrong. Try again.',
                };
            case 'agent_message':
                return {
                    kind: 'final',
                    assistantMessageId: message.message_id || this.generateAssistantMessageId(),
                    text: message.content || '',
                    artifacts: message.artifacts || [],
                    replyTo: message.reply_to || message.user_message_id || null,
                };
            case 'system_message':
                return {
                    kind: 'system',
                    text: message.content || message.message || '',
                };
            case 'conversation_started':
            case 'connection_established':
                return {
                    kind: 'status',
                    messageId: null,
                    text: message.message || '',
                };
            default:
                return null;
        }
    }

    handleStatusEvent(event) {
        const pendingId = event.messageId || this.latestPendingTurnId();
        if (!pendingId) {
            return;
        }

        const pending = this.pendingTurns.get(pendingId);
        if (!pending) {
            return;
        }

        if (!pending.indicator.isConnected) {
            const indicator = this.buildTypingIndicator();
            pending.turnElement.appendChild(indicator);
            pending.indicator = indicator;
        }

        if (pending.stillWorkingTimer) {
            clearTimeout(pending.stillWorkingTimer);
        }
        pending.stillWorkingTimer = this.startStillWorkingTimer(pending.indicator);

        this.announceTyping();
    }

    handleFinalEvent(event) {
        if (this.handledAssistantMessages.has(event.assistantMessageId)) {
            return;
        }
        this.handledAssistantMessages.add(event.assistantMessageId);

        const replyTo = event.replyTo || this.oldestPendingTurnId();
        const turn = replyTo ? this.pendingTurns.get(replyTo) : null;

        const assistantMessage = this.buildAssistantMessage(event.text, event.assistantMessageId, event.artifacts);

        if (turn) {
            if (turn.indicator && turn.indicator.isConnected) {
                turn.indicator.remove();
            }
            if (turn.stillWorkingTimer) {
                clearTimeout(turn.stillWorkingTimer);
            }
            turn.turnElement.appendChild(assistantMessage);
            this.pendingTurns.delete(replyTo);
        } else {
            const container = document.createElement('div');
            container.className = 'turn';
            container.appendChild(assistantMessage);
            this.messages.appendChild(container);
        }

        this.scrollToBottom();
        this.showDecisionBar(assistantMessage, event.assistantMessageId);
    }

    handleErrorEvent(event) {
        const pendingId = event.messageId || this.oldestPendingTurnId();
        const pending = pendingId ? this.pendingTurns.get(pendingId) : null;
        if (!pending) {
            this.appendSystemMessage(event.hint || 'Something went wrong. Try again.');
            return;
        }

        if (pending.indicator && pending.indicator.isConnected) {
            pending.indicator.remove();
        }
        if (pending.stillWorkingTimer) {
            clearTimeout(pending.stillWorkingTimer);
        }

        const errorBlock = document.createElement('div');
        errorBlock.className = 'error-message';
        errorBlock.innerHTML = `<span>${this.escapeHtml(event.hint || 'Something went wrong. Try again.')}</span>`;
        const retryButton = document.createElement('button');
        retryButton.type = 'button';
        retryButton.textContent = 'Try again';
        retryButton.addEventListener('click', () => {
            if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
                this.showConnectionBanner('Still connecting… please wait.');
                return;
            }
            retryButton.disabled = true;
            errorBlock.remove();
            this.sendMessageText(pending.text);
        });
        errorBlock.appendChild(retryButton);
        pending.turnElement.appendChild(errorBlock);
        this.pendingTurns.delete(pending.id);
        this.scrollToBottom();
    }

    showDecisionBar(messageElement, assistantMessageId) {
        if (this.activeDecision && !this.activeDecision.submitted) {
            this.activeDecision.element.remove();
        }

        const decisionElement = this.buildDecisionBlock(assistantMessageId);
        messageElement.appendChild(decisionElement);
        this.activeDecision = {
            element: decisionElement,
            messageId: assistantMessageId,
            submitted: false,
        };

        const firstRadio = decisionElement.querySelector('input[type="radio"]');
        if (firstRadio) {
            requestAnimationFrame(() => firstRadio.focus());
        }
    }

    buildDecisionBlock(assistantMessageId) {
        const wrapper = document.createElement('div');
        wrapper.className = 'decision-block';

        const form = document.createElement('form');
        form.className = 'decision-form';
        form.setAttribute('data-assistant-id', assistantMessageId);

        const fieldset = document.createElement('fieldset');

        const legend = document.createElement('legend');
        legend.textContent = 'What do you want to do with this result?';
        fieldset.appendChild(legend);

        const options = document.createElement('div');
        options.className = 'decision-options';

        const approveId = `decision-approve-${assistantMessageId}`;
        const feedbackId = `decision-feedback-${assistantMessageId}`;

        const approveLabel = document.createElement('label');
        const approveRadio = document.createElement('input');
        approveRadio.type = 'radio';
        approveRadio.name = 'decision';
        approveRadio.value = 'approved';
        approveRadio.id = approveId;
        approveLabel.htmlFor = approveId;
        approveLabel.appendChild(approveRadio);
        approveLabel.append('Approve');

        const feedbackLabel = document.createElement('label');
        const feedbackRadio = document.createElement('input');
        feedbackRadio.type = 'radio';
        feedbackRadio.name = 'decision';
        feedbackRadio.value = 'feedback';
        feedbackRadio.id = feedbackId;
        feedbackLabel.htmlFor = feedbackId;
        feedbackLabel.appendChild(feedbackRadio);
        feedbackLabel.append('Give feedback');

        options.appendChild(approveLabel);
        options.appendChild(feedbackLabel);

        fieldset.appendChild(options);

        const feedbackWrapper = document.createElement('div');
        feedbackWrapper.className = 'decision-feedback hidden';

        const feedbackLabelElement = document.createElement('label');
        feedbackLabelElement.setAttribute('for', `feedback-text-${assistantMessageId}`);
        feedbackLabelElement.textContent = 'Tell us what to change…';

        const feedbackTextarea = document.createElement('textarea');
        feedbackTextarea.id = `feedback-text-${assistantMessageId}`;
        feedbackTextarea.placeholder = 'Tell us what to change…';
        feedbackTextarea.disabled = true;

        feedbackWrapper.appendChild(feedbackLabelElement);
        feedbackWrapper.appendChild(feedbackTextarea);

        const actions = document.createElement('div');
        actions.className = 'decision-actions';

        const submitButton = document.createElement('button');
        submitButton.type = 'submit';
        submitButton.className = 'primary-btn';
        submitButton.textContent = 'Submit';
        submitButton.disabled = true;

        const confirmation = document.createElement('span');
        confirmation.className = 'decision-confirmation hidden';
        confirmation.textContent = 'Thanks! We’ll take it from here.';

        actions.appendChild(submitButton);
        actions.appendChild(confirmation);

        fieldset.appendChild(feedbackWrapper);
        fieldset.appendChild(actions);

        form.appendChild(fieldset);
        wrapper.appendChild(form);

        const toggleFeedback = () => {
            if (feedbackRadio.checked) {
                feedbackWrapper.classList.remove('hidden');
                feedbackTextarea.required = true;
                feedbackTextarea.disabled = false;
                submitButton.disabled = !feedbackTextarea.value.trim();
            } else {
                feedbackWrapper.classList.add('hidden');
                feedbackTextarea.required = false;
                feedbackTextarea.disabled = true;
                submitButton.disabled = !approveRadio.checked;
            }
        };

        form.addEventListener('change', () => {
            toggleFeedback();
            if (!approveRadio.checked && !feedbackRadio.checked) {
                submitButton.disabled = true;
            }
        });

        feedbackTextarea.addEventListener('input', () => {
            if (feedbackRadio.checked) {
                submitButton.disabled = !feedbackTextarea.value.trim();
            }
        });

        form.addEventListener('submit', (event) => {
            event.preventDefault();
            const decisionValue = approveRadio.checked ? 'approved' : feedbackRadio.checked ? 'feedback' : null;
            if (!decisionValue) {
                return;
            }

            if (decisionValue === 'feedback' && !feedbackTextarea.value.trim()) {
                feedbackTextarea.focus();
                return;
            }

            submitButton.disabled = true;
            approveRadio.disabled = true;
            feedbackRadio.disabled = true;
            feedbackTextarea.disabled = true;

            this.submitDecision(assistantMessageId, decisionValue, feedbackTextarea.value.trim())
                .then(() => {
                    confirmation.classList.remove('hidden');
                    submitButton.disabled = true;
                    submitButton.textContent = 'Submitted';
                    this.activeDecision.submitted = true;
                })
                .catch((error) => {
                    console.error('Failed to submit decision', error);
                    approveRadio.disabled = false;
                    feedbackRadio.disabled = false;
                    feedbackTextarea.disabled = !feedbackRadio.checked;
                    submitButton.disabled = false;
                });
        });

        // Ensure initial state
        toggleFeedback();

        return wrapper;
    }

    async submitDecision(assistantMessageId, decision, feedbackText) {
        const payload = {
            thread_id: this.threadId,
            assistant_message_id: assistantMessageId,
            decision,
        };

        if (decision === 'feedback' && feedbackText) {
            payload.feedback_text = feedbackText;
        }

        const response = await fetch(`${this.apiBaseUrl}/frontend/decisions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`Decision submission failed (${response.status})`);
        }

        return response.json();
    }

    appendSystemMessage(text) {
        if (!text) {
            return;
        }
        const container = document.createElement('div');
        container.className = 'turn';
        const message = document.createElement('div');
        message.className = 'message assistant';
        message.textContent = text;
        container.appendChild(message);
        this.messages.appendChild(container);
        this.scrollToBottom();
    }

    buildUserMessage(text) {
        const element = document.createElement('div');
        element.className = 'message user';
        element.textContent = text;
        const timestamp = document.createElement('span');
        timestamp.className = 'timestamp';
        timestamp.textContent = this.formatTime(new Date());
        element.appendChild(timestamp);
        return element;
    }

    buildAssistantMessage(text, assistantMessageId, artifacts = []) {
        const element = document.createElement('div');
        element.className = 'message assistant';
        element.setAttribute('data-assistant-id', assistantMessageId || '');
        element.textContent = text;

        if (artifacts && Array.isArray(artifacts) && artifacts.length > 0) {
            const list = document.createElement('ul');
            list.className = 'artifact-list';
            artifacts.forEach((artifact) => {
                const item = document.createElement('li');
                if (artifact && artifact.url) {
                    const link = document.createElement('a');
                    link.href = artifact.url;
                    link.textContent = artifact.label || artifact.url;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    item.appendChild(link);
                } else if (artifact && artifact.label) {
                    item.textContent = artifact.label;
                }
                list.appendChild(item);
            });
            element.appendChild(list);
        }

        const timestamp = document.createElement('span');
        timestamp.className = 'timestamp';
        timestamp.textContent = this.formatTime(new Date());
        element.appendChild(timestamp);

        return element;
    }

    buildTypingIndicator() {
        const wrapper = document.createElement('div');
        wrapper.className = 'typing-indicator';
        wrapper.setAttribute('role', 'status');
        wrapper.setAttribute('aria-live', 'polite');

        const label = document.createElement('div');
        label.textContent = 'Thinking…';

        const dots = document.createElement('div');
        dots.className = 'typing-dots';
        dots.innerHTML = '<span></span><span></span><span></span>';

        wrapper.appendChild(label);
        wrapper.appendChild(dots);

        return wrapper;
    }

    startStillWorkingTimer(indicator) {
        return setTimeout(() => {
            if (!indicator.isConnected) {
                return;
            }
            let note = indicator.querySelector('.typing-note');
            if (!note) {
                note = document.createElement('div');
                note.className = 'typing-note';
                note.textContent = 'Still working…';
                indicator.appendChild(note);
            }
        }, this.stillWorkingDelay);
    }

    announceTyping() {
        this.typingLiveRegion.textContent = 'Thinking…';
        setTimeout(() => {
            this.typingLiveRegion.textContent = '';
        }, 1000);
    }

    scrollToBottom() {
        this.messages.scrollTop = this.messages.scrollHeight;
    }

    generateMessageId() {
        if (window.crypto && window.crypto.randomUUID) {
            return window.crypto.randomUUID();
        }
        return `msg_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    }

    generateAssistantMessageId() {
        if (window.crypto && window.crypto.randomUUID) {
            return `assistant_${window.crypto.randomUUID()}`;
        }
        return `assistant_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    }

    latestPendingTurnId() {
        const ids = Array.from(this.pendingTurns.keys());
        return ids.length ? ids[ids.length - 1] : null;
    }

    oldestPendingTurnId() {
        const iterator = this.pendingTurns.keys();
        const first = iterator.next();
        return first.done ? null : first.value;
    }

    formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

window.addEventListener('DOMContentLoaded', () => {
    window.singlePersonaChat = new SinglePersonaChat();
});

window.addEventListener('beforeunload', () => {
    if (window.singlePersonaChat && window.singlePersonaChat.websocket) {
        window.singlePersonaChat.websocket.close(1000, 'Page unload');
    }
});
