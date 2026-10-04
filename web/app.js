const state = {
  sessionId: `desk-${crypto.randomUUID ? crypto.randomUUID().slice(0, 8) : Date.now()}`,
  fields: {},
  currentState: 'GREET',
  listening: false,
  busy: false,
  handsFree: false,
  agentConfig: null,
};

const transcript = document.querySelector('#transcript');
const emptyState = document.querySelector('#empty-state');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#message-input');
const micButton = document.querySelector('#mic-button');
const voiceStatus = document.querySelector('#voice-status');
const resetButton = document.querySelector('#reset-button');
const sessionLabel = document.querySelector('#session-label');
const connectionLabel = document.querySelector('#connection-label');
const languageSelect = document.querySelector('#language-select');
const handsfreeToggle = document.querySelector('#handsfree-toggle');

let labels = {};

function renderAgentFields(fields = []) {
  const list = document.querySelector('#field-list');
  labels = Object.fromEntries(fields.map((field) => [field.id, field.label]));
  list.innerHTML = fields.map((field) => (
    `<div class="field-row" data-field="${field.id}"><dt>${field.label}</dt><dd>Waiting</dd></div>`
  )).join('');
}

function renderGuardrails(guardrails = []) {
  const list = document.querySelector('#guardrail-list');
  list.innerHTML = guardrails.map((guardrail) => (
    `<li><span class="check">✓</span><span>${guardrail}</span></li>`
  )).join('');
}

async function loadAgentConfig() {
  try {
    const response = await fetch('/agent-config');
    if (!response.ok) throw new Error('Agent configuration unavailable');
    const config = await response.json();
    state.agentConfig = config;
    document.title = `${config.name} | ConvoForge`;
    document.querySelector('#agent-name').textContent = config.name;
    document.querySelector('#agent-role').textContent = config.role;
    document.querySelector('#agent-avatar').textContent = config.name.slice(0, 1).toUpperCase();
    document.querySelector('#prompt-version').textContent = config.goal?.type || 'active';
    document.querySelector('#agent-presence').textContent = `${config.name} is ready`;
    renderAgentFields(config.fields || []);
    renderGuardrails(config.guardrails || []);
    const emptyState = config.ui?.empty_state || {};
    document.querySelector('#empty-eyebrow').textContent = emptyState.eyebrow || 'READY WHEN YOU ARE';
    document.querySelector('#empty-title').textContent = emptyState.title || 'How can I help?';
    document.querySelector('#empty-description').textContent = emptyState.description
      || config.goal?.description
      || 'Tell me what you need and I will help with the next useful step.';
  } catch (error) {
    connectionLabel.textContent = 'Configuration issue';
    showError(error.message);
  }
}

function addMessage(role, text) {
  emptyState?.remove();
  const item = document.createElement('div');
  item.className = `message ${role}`;
  const avatar = document.createElement('span');
  avatar.className = `mini-avatar ${role === 'user' ? 'user-avatar' : ''}`;
  avatar.textContent = role === 'user' ? 'You' : 'P';
  const content = document.createElement('div');
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = text;
  const meta = document.createElement('div');
  meta.className = 'message-meta';
  const agentName = state.agentConfig?.name || 'Agent';
  meta.textContent = role === 'user' ? 'Sent just now' : `${agentName} • Just now`;
  content.append(bubble, meta);
  item.append(avatar, content);
  transcript.append(item);
  transcript.scrollTop = transcript.scrollHeight;
}

function showError(message) {
  const note = document.createElement('div');
  note.className = 'error-note';
  note.textContent = message;
  transcript.append(note);
  transcript.scrollTop = transcript.scrollHeight;
}

function updateLead(fields = {}) {
  state.fields = { ...state.fields, ...fields };
  const total = Object.keys(labels).length;
  let complete = 0;
  Object.entries(labels).forEach(([key, label]) => {
    const row = document.querySelector(`[data-field="${key}"]`);
    const value = state.fields[key];
    if (!row) return;
    const detail = row.querySelector('dd');
    detail.textContent = value || 'Waiting';
    row.classList.toggle('filled', Boolean(value));
    if (value) complete += 1;
  });
  const percent = total ? Math.round((complete / total) * 100) : 0;
  const detailWord = complete === 1 ? 'detail' : 'details';
  document.querySelector('#completion').textContent = `${complete} ${detailWord} captured`;
  document.querySelector('#progress-bar').style.width = `${percent}%`;
}

function updateRail(nextState) {
  state.currentState = nextState;
  const labelsByState = {
    ACTIVE: 'Listening for what matters to you',
    GREET: 'Getting to know what you need',
    QUALIFY: 'Listening for what matters to you',
    HANDLE_OBJECTION: 'Working through your question',
    CLOSE: 'Preparing the next useful step',
    END: 'Conversation complete',
  };
  const mode = document.querySelector('#conversation-mode');
  if (mode) mode.textContent = labelsByState[nextState] || labelsByState.QUALIFY;
}

function setBusy(busy) {
  state.busy = busy;
  input.disabled = busy;
  form.querySelector('.send-button').disabled = busy;
  const agentName = state.agentConfig?.name || 'Agent';
  voiceStatus.textContent = busy ? `${agentName} is thinking...` : 'Text or voice input';
}

async function sendMessage(message) {
  const text = message.trim();
  if (!text || state.busy) return;
  addMessage('user', text);
  input.value = '';
  setBusy(true);
  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.sessionId,
        message: text,
        language: languageSelect.value,
      }),
    });
    const responseText = await response.text();
    let data;
    try {
      data = JSON.parse(responseText);
    } catch {
      throw new Error(
        response.ok
          ? 'The conversation service returned an invalid response.'
          : `The conversation service failed (${response.status}). Check the server terminal for details.`,
      );
    }
    if (!response.ok) throw new Error(data.detail || 'The conversation service is unavailable.');
    addMessage('assistant', data.reply);
    updateLead(data.collected || {});
    updateRail(data.state);
    sessionLabel.textContent = state.sessionId;
    connectionLabel.textContent = 'API connected';
    speak(data.reply, languageSelect.value);
  } catch (error) {
    connectionLabel.textContent = 'API issue';
    showError(error.message);
  } finally {
    setBusy(false);
    input.focus();
  }
}

function speak(text, language = 'english') {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const voiceLanguage = language === 'hindi' ? 'hi-IN' : 'en-IN';
  utterance.lang = voiceLanguage;
  utterance.rate = 0.96;
  utterance.pitch = 1;
  utterance.volume = 0.95;
  const voices = window.speechSynthesis.getVoices();
  utterance.voice = voices.find((voice) => voice.lang === voiceLanguage)
    || voices.find((voice) => voice.lang.startsWith(voiceLanguage.slice(0, 2)))
    || null;
  utterance.onstart = () => {
    if (state.handsFree) voiceStatus.textContent = 'Speaking...';
  };
  utterance.onend = () => {
    if (state.handsFree && state.currentState !== 'END' && !state.busy) {
      window.startVoiceCapture?.();
    }
  };
  window.speechSynthesis.speak(utterance);
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

resetButton.addEventListener('click', () => {
  state.sessionId = `desk-${crypto.randomUUID ? crypto.randomUUID().slice(0, 8) : Date.now()}`;
  state.fields = {};
  state.currentState = 'GREET';
  transcript.innerHTML = '';
  const fresh = document.createElement('div');
  fresh.className = 'empty-state';
  const emptyState = state.agentConfig?.ui?.empty_state || {};
  fresh.innerHTML = `<span class="empty-kicker">${emptyState.eyebrow || 'READY WHEN YOU ARE'}</span><h2>${emptyState.title || 'How can I help?'}</h2><p>${emptyState.description || 'Tell the assistant what you need help with, by voice or text.'}</p>`;
  transcript.append(fresh);
  updateLead({});
  updateRail('GREET');
  sessionLabel.textContent = 'New session';
  input.focus();
});

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  const SILENCE_TIMEOUT = 2000;
  const recognition = new SpeechRecognition();
  recognition.lang = 'en-IN';
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 3;
  let finalTranscript = '';
  let interimTranscript = '';
  let shouldKeepListening = false;
  let silenceTimer = null;
  let restartTimer = null;

  const clearListeningTimers = () => {
    window.clearTimeout(silenceTimer);
    window.clearTimeout(restartTimer);
    silenceTimer = null;
    restartTimer = null;
  };

  const currentTranscript = () => `${finalTranscript} ${interimTranscript}`.trim();

  const finishListening = (submit = false) => {
    shouldKeepListening = false;
    clearListeningTimers();
    const heard = currentTranscript();
    state.listening = false;
    micButton.classList.remove('active');
    voiceStatus.classList.remove('listening');
    try {
      recognition.stop();
    } catch {
      // The recognition engine may already have ended itself.
    }
    if (!heard || state.busy) {
      voiceStatus.textContent = 'Text or voice input';
      return;
    }
    input.value = heard;
    if (submit) {
      voiceStatus.textContent = 'Processing...';
      sendMessage(heard);
    } else {
      voiceStatus.textContent = 'Review the transcript, then press Send';
    }
  };

  const scheduleSilenceStop = () => {
    window.clearTimeout(silenceTimer);
    silenceTimer = window.setTimeout(() => finishListening(state.handsFree), SILENCE_TIMEOUT);
  };

  const startListening = () => {
    if (state.busy || state.listening) return;
    shouldKeepListening = true;
    finalTranscript = '';
    interimTranscript = '';
    input.value = '';
    try {
      recognition.start();
    } catch {
      voiceStatus.textContent = 'Still listening...';
    }
  };

  window.startVoiceCapture = startListening;

  recognition.onstart = () => {
    recognition.lang = languageSelect.value === 'hindi' ? 'hi-IN' : 'en-IN';
    state.listening = true;
    micButton.classList.add('active');
    voiceStatus.textContent = 'Listening...';
    voiceStatus.classList.add('listening');
    scheduleSilenceStop();
  };
  recognition.onresult = (event) => {
    interimTranscript = '';
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const transcriptText = result[0].transcript;
      if (result.isFinal) {
        const finalizedText = transcriptText.trim();
        const existingText = finalTranscript.trim();
        if (finalizedText && !existingText.endsWith(finalizedText)) {
          finalTranscript = `${existingText} ${finalizedText}`.trim();
        }
      }
      else interimTranscript += transcriptText;
    }
    input.value = `${finalTranscript}${interimTranscript}`.trim();
    voiceStatus.textContent = interimTranscript ? 'Still listening...' : 'Listening...';
    scheduleSilenceStop();
  };
  recognition.onerror = (event) => {
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      finishListening(false);
      voiceStatus.textContent = 'Microphone permission is required for voice input.';
      return;
    }
    if (shouldKeepListening) {
      voiceStatus.textContent = 'Still listening...';
      scheduleSilenceStop();
    }
  };
  recognition.onend = () => {
    if (shouldKeepListening && !state.busy) {
      voiceStatus.textContent = 'Still listening...';
      restartTimer = window.setTimeout(() => {
        try {
          recognition.start();
        } catch {
          scheduleSilenceStop();
        }
      }, 120);
      return;
    }
    if (!shouldKeepListening) {
      state.listening = false;
      micButton.classList.remove('active');
      voiceStatus.classList.remove('listening');
    }
  };
  micButton.addEventListener('click', () => {
    if (state.listening) finishListening(state.handsFree);
    else startListening();
  });
} else {
  micButton.disabled = true;
  micButton.title = 'Speech recognition is not supported in this browser';
  voiceStatus.textContent = 'Voice input is unavailable in this browser';
}

handsfreeToggle.addEventListener('change', () => {
  state.handsFree = handsfreeToggle.checked;
  voiceStatus.textContent = state.handsFree ? 'Hands-free mode enabled' : 'Text or voice input';
});

loadAgentConfig();
