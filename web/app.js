const state = {
  sessionId: `desk-${crypto.randomUUID ? crypto.randomUUID().slice(0, 8) : Date.now()}`,
  fields: {},
  currentState: 'GREET',
  listening: false,
  busy: false,
  handsFree: false,
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

const labels = {
  name: 'Name',
  city: 'City',
  monthly_income: 'Monthly income',
  loan_amount: 'Loan amount',
  employment_type: 'Employment',
};

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
  meta.textContent = role === 'user' ? 'Sent just now' : 'Priya • Just now';
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
  const percent = Math.round((complete / total) * 100);
  document.querySelector('#completion').textContent = `${percent}%`;
  document.querySelector('#progress-bar').style.width = `${percent}%`;
}

function updateRail(nextState) {
  state.currentState = nextState;
  const order = ['GREET', 'QUALIFY', 'HANDLE_OBJECTION', 'CLOSE'];
  const activeIndex = order.indexOf(nextState);
  document.querySelectorAll('.state-step').forEach((step) => {
    const index = order.indexOf(step.dataset.state);
    step.classList.toggle('current', step.dataset.state === nextState);
    step.classList.toggle('done', index >= 0 && index < activeIndex);
  });
}

function setBusy(busy) {
  state.busy = busy;
  input.disabled = busy;
  form.querySelector('.send-button').disabled = busy;
  voiceStatus.textContent = busy ? 'Priya is thinking...' : 'Text or voice input';
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
  utterance.lang = language === 'hindi' ? 'hi-IN' : 'en-IN';
  utterance.rate = 1;
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
  fresh.innerHTML = '<span class="empty-kicker">Ready when you are</span><h2>Start the qualification call.</h2><p>Type a message or use the microphone. Priya will collect the five details needed for a specialist follow-up.</p>';
  transcript.append(fresh);
  updateLead({});
  updateRail('GREET');
  sessionLabel.textContent = 'New session';
  input.focus();
});

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  const recognition = new SpeechRecognition();
  recognition.lang = 'en-IN';
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 3;
  let finalTranscript = '';
  recognition.onstart = () => {
    recognition.lang = languageSelect.value === 'hindi' ? 'hi-IN' : 'en-IN';
    finalTranscript = '';
    input.value = '';
    state.listening = true;
    micButton.classList.add('active');
    voiceStatus.textContent = 'Listening...';
    voiceStatus.classList.add('listening');
  };
  recognition.onresult = (event) => {
    let interimTranscript = '';
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const transcriptText = result[0].transcript;
      if (result.isFinal) finalTranscript += `${transcriptText} `;
      else interimTranscript += transcriptText;
    }
    input.value = `${finalTranscript}${interimTranscript}`.trim();
    voiceStatus.textContent = interimTranscript ? 'Hearing you...' : 'Reviewing your words...';
  };
  recognition.onerror = () => {
    voiceStatus.textContent = 'Could not hear that. Try again or type instead.';
  };
  recognition.onend = () => {
    const heard = finalTranscript.trim();
    state.listening = false;
    micButton.classList.remove('active');
    voiceStatus.classList.remove('listening');
    if (heard && !state.busy && state.handsFree) sendMessage(heard);
    else if (heard && !state.busy) voiceStatus.textContent = 'Review the transcript, then press Send';
    else if (!state.busy) voiceStatus.textContent = 'Text or voice input';
  };
  micButton.addEventListener('click', () => {
    if (state.listening) recognition.stop();
    else recognition.start();
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
