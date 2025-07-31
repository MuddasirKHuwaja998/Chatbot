// --- Mic Button & Italian Voice with VAD ---

// UI Elements
const micButton = document.getElementById('micButton');
const micNote = document.getElementById('micNote');

// Helper: Play Italian TTS via SpeechSynthesis
function speakMessage(message) {
  if (!('speechSynthesis' in window)) return;
  let synth = window.speechSynthesis;
  function speakWithVoices() {
    let voices = synth.getVoices();
    let selectedVoice = voices.find(v =>
      v.lang === 'it-IT' && (
        v.name.toLowerCase().includes("google italiano") ||
        v.name.toLowerCase().includes("alice") ||
        v.name.toLowerCase().includes("lucia") ||
        v.name.toLowerCase().includes("chiara") ||
        v.name.toLowerCase().includes("bianca") ||
        v.name.toLowerCase().includes("silvia")
      )
    );
    if (!selectedVoice) selectedVoice = voices.find(v => v.lang === 'it-IT');
    const utterance = new SpeechSynthesisUtterance(message);
    utterance.lang = 'it-IT';
    if (selectedVoice) utterance.voice = selectedVoice;
    utterance.pitch = 1.07;
    utterance.rate = 0.97;
    synth.speak(utterance);
  }
  if (synth.onvoiceschanged !== undefined) {
    synth.onvoiceschanged = speakWithVoices;
  }
  speakWithVoices();
}
// Preload voices
if ('speechSynthesis' in window) {
  window.speechSynthesis.getVoices();
}

// --- VAD Microphone Logic ---
let vadRecorder = null;
let vadStream = null;
let vadChunks = [];
let vadAudioCtx = null;
let vad = null;
let vadSilenceTimer = null;
let vadResponseTimer = null;
let vadIsRecording = false;

micButton.addEventListener('click', startVADRecording);

function startVADRecording() {
  if (vadIsRecording) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    micNote.textContent = "❌ Microfono non supportato dal browser.";
    return;
  }
  if (!(location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
    micNote.textContent = "❌ Richiesto HTTPS. Accedi tramite https:// o localhost";
    return;
  }
  if (!window.vad) {
    micNote.textContent = "❌ Errore microfono: VAD non trovato";
    return;
  }

  micButton.classList.add('listening');
  micButton.disabled = true;
  micNote.textContent = "Ascolto in corso...";

  vadIsRecording = true;
  vadChunks = [];

  navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
    vadStream = stream;
    vadAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = vadAudioCtx.createMediaStreamSource(stream);

    // Browser VAD config: sensitivity can be tuned
    vad = window.vad.createVAD(vadAudioCtx, source, { energyOffset: 0.01 });

    // Use MediaRecorder for audio chunks
    vadRecorder = new MediaRecorder(stream);
    vadRecorder.ondataavailable = e => {
      if (e.data.size > 0) vadChunks.push(e.data);
    };

    // On stop: send to backend for transcription + reply
    vadRecorder.onstop = () => {
      stopVAD();
      if (!vadChunks.length) {
        micNote.textContent = "❌ Nessuna voce rilevata.";
        resetMicButton();
        return;
      }
      micNote.textContent = "⏳ Trascrizione in corso...";
      const audioBlob = new Blob(vadChunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('audio', audioBlob, 'input.webm');

      fetch('/transcribe', {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.transcript && data.transcript.length > 0) {
          micNote.textContent = "🗣️ Risposta vocale in corso...";
          // Reply via backend (optional, fallback: local TTS)
          fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message: data.transcript,
              voice: true
            })
          })
          .then(response => response.json())
          .then(chatData => {
            if (chatData.reply) {
              speakMessage(chatData.reply);
              micNote.textContent = "✅ Pronto per nuova conversazione";
            } else {
              micNote.textContent = "❌ Nessuna risposta trovata.";
            }
            resetMicButton();
          });
        } else {
          micNote.textContent = "❌ Nessuna voce o trascrizione fallita.";
          resetMicButton();
        }
      })
      .catch(() => {
        micNote.textContent = "❌ Errore nella trascrizione.";
        resetMicButton();
      });
    };

    vadRecorder.start();

    // VAD events
    vad.on('voice_start', () => {
      if (vadSilenceTimer) {
        clearTimeout(vadSilenceTimer);
        vadSilenceTimer = null;
      }
    });

    vad.on('voice_stop', () => {
      // After 1 second silence, in 2 seconds, trigger stop (total 3s)
      if (!vadSilenceTimer) {
        vadSilenceTimer = setTimeout(() => {
          vadResponseTimer = setTimeout(() => {
            if (vadIsRecording && vadRecorder && vadRecorder.state === "recording") {
              vadRecorder.stop();
            }
          }, 2000); // 2 seconds after 1 sec silence
        }, 1000); // 1 second of silence
      }
    });

  }).catch(err => {
    micNote.textContent = `❌ Errore microfono: ${err.message}`;
    resetMicButton();
    vadIsRecording = false;
  });
}

function stopVAD() {
  vadIsRecording = false;
  if (vad) {
    vad.destroy();
    vad = null;
  }
  if (vadAudioCtx && vadAudioCtx.state !== "closed") {
    vadAudioCtx.close();
    vadAudioCtx = null;
  }
  if (vadStream) {
    vadStream.getTracks().forEach(track => track.stop());
    vadStream = null;
  }
  if (vadSilenceTimer) {
    clearTimeout(vadSilenceTimer);
    vadSilenceTimer = null;
  }
  if (vadResponseTimer) {
    clearTimeout(vadResponseTimer);
    vadResponseTimer = null;
  }
}

function resetMicButton() {
  micButton.classList.remove('listening');
  micButton.disabled = false;
  micNote.textContent = "Premi di nuovo il microfono per parlare";
}

// --- Hide advanced fields (for index.js advanced mode) ---
document.getElementById('status').classList.add('hidden');
document.getElementById('micBtn').classList.add('hidden');
document.getElementById('activationStatus').classList.add('hidden');
document.getElementById('connectionStatus').classList.add('hidden');
