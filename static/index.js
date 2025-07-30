// OtoBot Professional Italian Voice Assistant (Google Cloud Charon Voice)
// Medical/Enterprise Version: Backend Speech-to-Text

let isRecording = false;

// UI elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const activationStatus = document.getElementById('activationStatus');
const connectionStatus = document.getElementById('connectionStatus');

// --- Voice Synthesis via Backend Google TTS ---
function speakWithGoogleTTS(text) {
    showMoveXloopAfterCurrentLoop();
    fetch('/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
    })
    .then(response => response.blob())
    .then(blob => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        let safetyTimer = setTimeout(() => {
            if (typeof endMoveXloop === 'function') {
                endMoveXloop();
            }
        }, 30000); // 30 secondi
        audio.play();
        audio.onended = function() {
            clearTimeout(safetyTimer);
            if (typeof endMoveXloop === 'function') {
                endMoveXloop();
            }
        };
        audio.onerror = function() {
            clearTimeout(safetyTimer);
            if (typeof endMoveXloop === 'function') {
                endMoveXloop();
            }
        };
    });
}

// --- Audio Recording and Backend Transcription ---
let mediaRecorder;
let audioChunks = [];

async function startRecording() {
    if (isRecording) return;

    status.textContent = "🎤 Parla ora...";
    micBtn.classList.add('recording');
    isRecording = true;
    audioChunks = [];

    // Request microphone access
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            status.textContent = "⏳ Trascrizione in corso...";
            micBtn.classList.remove('recording');
            micBtn.classList.add('processing');
            isRecording = false;

            // Combine audio chunks into a single blob
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('audio', audioBlob, 'input.webm');

            // Send audio to backend for transcription
            fetch('/transcribe', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.transcript && data.transcript.length > 0) {
                    status.textContent = "🗣️ Risposta vocale in corso...";
                    // Send transcript to chat endpoint
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
                            speakWithGoogleTTS(chatData.reply);
                            status.textContent = "✅ Pronto per nuova conversazione";
                        } else {
                            status.textContent = "❌ Nessuna risposta trovata.";
                        }
                        resetMicButton();
                    });
                } else {
                    status.textContent = "❌ Nessuna voce rilevata o trascrizione fallita.";
                    resetMicButton();
                }
            })
            .catch(() => {
                status.textContent = "❌ Errore nella trascrizione.";
                resetMicButton();
            });
        };

        mediaRecorder.start();

        // Auto-stop after 8 seconds or on silence
        setTimeout(() => {
            if (isRecording && mediaRecorder.state === "recording") {
                mediaRecorder.stop();
            }
        }, 8000);

        // Optional: stop on button click again
        micBtn.onclick = () => {
            if (isRecording && mediaRecorder.state === "recording") {
                mediaRecorder.stop();
            }
        };

    } catch (error) {
        status.textContent = `❌ Errore microfono: ${error.message}`;
        resetMicButton();
        isRecording = false;
    }
}

function resetMicButton() {
    micBtn.classList.remove('recording', 'processing');
    micBtn.onclick = toggleRecording;
}

function toggleRecording() {
    if (!isRecording) {
        startRecording();
    }
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', function() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        status.textContent = "❌ Microfono non supportato dal browser.";
        if (micBtn) micBtn.disabled = true;
        return;
    }

    if (!(location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
        status.textContent = "❌ Richiesto HTTPS. Accedi tramite https:// o localhost";
        if (micBtn) micBtn.disabled = true;
        return;
    }

    if (micBtn) {
        micBtn.addEventListener('click', toggleRecording);
        micBtn.disabled = false;
        micBtn.style.opacity = '1';
        micBtn.style.cursor = 'pointer';
    }

    connectionStatus.textContent = "🟢 Pronto (TTS Google Cloud)";
    connectionStatus.className = "connection-status online";

    if (activationStatus) {
        activationStatus.textContent = "🎧 Pronto per la registrazione vocale";
    }
});
