const state = {
  sessionId: `desk-${crypto.randomUUID ? crypto.randomUUID().slice(0, 8) : Date.now()}`,
  fields: {},
  currentState: 'GREET',
  listening: false,
  busy: false,
  handsFree: false,
  agentConfig: null,
  voiceState: 'IDLE',
  voiceGeneration: 0,
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

function renderLanguages(languages = []) {
  languageSelect.innerHTML = languages.map((language) => (
    `<option value="${language.id}">${language.label}</option>`
  )).join('');
  if (!languages.length) languageSelect.innerHTML = '<option value="default">Default</option>';
}

function activeLanguage() {
  return state.agentConfig?.languages?.find((language) => language.id === languageSelect.value)
    || state.agentConfig?.languages?.[0]
    || { id: 'default', stt_locale: navigator.language, tts_locale: navigator.language };
}

function setVoiceState(nextState) {
  state.voiceState = nextState;
  const labelsByState = {
    IDLE: 'Conversation ready',
    LISTENING: 'Listening...',
    PROCESSING: 'Processing...',
    SPEAKING: 'Speaking...',
    ERROR: 'Voice unavailable',
    COMPLETED: 'Conversation complete',
  };
  if (!state.busy || nextState !== 'IDLE') voiceStatus.textContent = labelsByState[nextState] || 'Conversation ready';
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
    document.querySelector('#agent-avatar').textContent = config.avatar?.initial
      || config.name.slice(0, 1).toUpperCase();
    document.querySelector('#prompt-version').textContent = config.goal?.type || 'active';
    document.querySelector('#agent-presence').textContent = `${config.name} is ready`;
    renderAgentFields(config.fields || []);
    renderGuardrails(config.guardrails || []);
    renderLanguages(config.languages || []);
    const emptyState = config.ui?.empty_state || {};
    document.querySelector('#empty-eyebrow').textContent = emptyState.eyebrow || 'READY WHEN YOU ARE';
    document.querySelector('#empty-title').textContent = emptyState.title || 'How can I help?';
    document.querySelector('#empty-description').textContent = emptyState.description
      || config.goal?.description
      || 'Tell me what you need and I will help with the next useful step.';
  } catch (error) {
    connectionLabel.textContent = 'Configuration issue';
    setVoiceState('ERROR');
    showError(error.message);
  }
}

function addMessage(role, text) {
  emptyState?.remove();
  const item = document.createElement('div');
  item.className = `message ${role}`;
  const avatar = document.createElement('span');
  avatar.className = `mini-avatar ${role === 'user' ? 'user-avatar' : ''}`;
  avatar.textContent = role === 'user'
    ? 'You'
    : state.agentConfig?.avatar?.initial || state.agentConfig?.name?.slice(0, 1).toUpperCase() || 'A';
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
  if (busy) {
    state.voiceState = 'PROCESSING';
    voiceStatus.textContent = `${agentName} is thinking...`;
  } else if (state.voiceState === 'PROCESSING') {
    setVoiceState('IDLE');
  }
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
        agent_id: state.agentConfig?.id,
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
  const generation = state.voiceGeneration;
  const languageConfig = state.agentConfig?.languages?.find((item) => item.id === language)
    || activeLanguage();
  const utterance = new SpeechSynthesisUtterance(text);
  const voiceLanguage = languageConfig.tts_locale;
  utterance.lang = voiceLanguage;
  utterance.rate = 0.96;
  utterance.pitch = 1;
  utterance.volume = 0.95;
  const voices = window.speechSynthesis.getVoices();
  utterance.voice = voices.find((voice) => voice.lang === voiceLanguage)
    || voices.find((voice) => voice.lang.startsWith(voiceLanguage.slice(0, 2)))
    || null;
  utterance.onstart = () => {
    if (generation !== state.voiceGeneration) return;
    setVoiceState('SPEAKING');
    if (state.handsFree && state.currentState !== 'END' && !state.busy) {
      window.startVoiceCapture?.(false);
    }
  };
  utterance.onend = () => {
    if (generation !== state.voiceGeneration) return;
    if (state.handsFree && state.currentState !== 'END' && !state.busy) {
      window.startVoiceCapture?.(true);
    } else if (state.currentState === 'END') {
      setVoiceState('COMPLETED');
    } else {
      setVoiceState('IDLE');
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
  window.resetVoiceRuntime?.();
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
  const SILENCE_TIMEOUT = Number(state.agentConfig?.voice?.silence_timeout_ms) || 2000;
  const recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 3;
  let finalTranscript = '';
  let interimTranscript = '';
  let recognitionStarted = false;
  let speechDetected = false;
  let shouldKeepListening = false;
  let userExplicitlyStopped = false;
  let silenceTimer = null;
  let restartTimer = null;

  const clearListeningTimers = () => {
    window.clearTimeout(silenceTimer);
    window.clearTimeout(restartTimer);
    silenceTimer = null;
    restartTimer = null;
  };

  const currentTranscript = () => `${finalTranscript} ${interimTranscript}`.trim();

  const cancelAgentSpeech = () => {
    if ('speechSynthesis' in window && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
    }
  };

  const finishListening = (submit = false, explicitStop = true) => {
    shouldKeepListening = false;
    userExplicitlyStopped = explicitStop;
    clearListeningTimers();
    const heard = currentTranscript();
    recognitionStarted = false;
    speechDetected = false;
    state.listening = false;
    micButton.classList.remove('active');
    voiceStatus.classList.remove('listening');
    try {
      if (explicitStop) recognition.stop();
      else recognition.abort();
    } catch {
      // The recognition engine may already have ended.
    }
    if (!heard || state.busy) {
      setVoiceState('IDLE');
      return;
    }
    input.value = heard;
    if (submit) {
      setVoiceState('PROCESSING');
      sendMessage(heard);
    } else {
      voiceStatus.textContent = 'Review the transcript, then press Send';
    }
  };

  const scheduleSilenceStop = () => {
    if (!speechDetected) return;
    window.clearTimeout(silenceTimer);
    silenceTimer = window.setTimeout(() => finishListening(state.handsFree), silenceTimeout());
  };

  const startListening = (continueTranscript = false) => {
    if (state.busy || state.listening) return;
    shouldKeepListening = true;
    userExplicitlyStopped = false;
    if (!continueTranscript) {
      finalTranscript = '';
      interimTranscript = '';
      input.value = '';
    }
    setVoiceState('LISTENING');
    try {
      recognition.lang = activeLanguage().stt_locale;
      recognition.start();
    } catch {
      voiceStatus.textContent = 'Still listening...';
    }
  };

  window.startVoiceCapture = startListening;

  window.resetVoiceRuntime = () => {
    state.voiceGeneration += 1;
    shouldKeepListening = false;
    userExplicitlyStopped = true;
    recognitionStarted = false;
    speechDetected = false;
    clearListeningTimers();
    cancelAgentSpeech();
    try {
      recognition.abort();
    } catch {
      // The recognition engine may already have ended.
    }
    finalTranscript = '';
    interimTranscript = '';
    state.listening = false;
    micButton.classList.remove('active');
    voiceStatus.classList.remove('listening');
    setVoiceState('IDLE');
  };

  recognition.onstart = () => {
    recognitionStarted = true;
    state.listening = true;
    micButton.classList.add('active');
    setVoiceState('LISTENING');
    voiceStatus.classList.add('listening');
  };
  recognition.onspeechstart = () => {
    speechDetected = true;
    cancelAgentSpeech();
    setVoiceState('LISTENING');
    scheduleSilenceStop();
  };
  recognition.onresult = (event) => {
    speechDetected = true;
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
    setVoiceState('LISTENING');
    scheduleSilenceStop();
  };
  recognition.onspeechend = () => {
    scheduleSilenceStop();
  };
  recognition.onerror = (event) => {
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed' || event.error === 'audio-capture') {
      finishListening(false, true);
      setVoiceState('ERROR');
      voiceStatus.textContent = event.error === 'audio-capture'
        ? 'Microphone could not be captured.'
        : 'Microphone permission is required for voice input.';
      return;
    }
    if (shouldKeepListening) {
      voiceStatus.textContent = 'Still listening...';
      if (event.error === 'audio-capture') setVoiceState('ERROR');
    }
  };
  recognition.onend = () => {
    recognitionStarted = false;
    if (shouldKeepListening && !userExplicitlyStopped && !state.busy) {
      voiceStatus.textContent = 'Still listening...';
      restartTimer = window.setTimeout(() => {
        try {
          recognition.lang = activeLanguage().stt_locale;
          recognition.start();
        } catch {
          if (shouldKeepListening) restartTimer = window.setTimeout(() => recognition.start(), 250);
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
    if (state.listening) finishListening(state.handsFree, true);
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
