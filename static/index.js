// OtoBot Professional Italian Voice Assistant (Google Cloud Charon Voice)
// Advanced VAD (Voice Activity Detection) for instant response

let isRecording = false;

// UI elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const activationStatus = document.getElementById('activationStatus');
const connectionStatus = document.getElementById('connectionStatus');

// --- Voice Synthesis via Backend Google TTS ---
function speakWithGoogleTTS(text) {
    if (typeof showMoveXloopAfterCurrentLoop === "function") showMoveXloopAfterCurrentLoop();
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
            if (typeof endMoveXloop === 'function') endMoveXloop();
        }, 10000);
        audio.play();
        audio.onended = function() {
            clearTimeout(safetyTimer);
            if (typeof endMoveXloop === 'function') endMoveXloop();
        };
        audio.onerror = function() {
            clearTimeout(safetyTimer);
            if (typeof endMoveXloop === 'function') endMoveXloop();
        };
    });
}

// --- Audio Recording and Backend Transcription with Advanced VAD ---
let mediaRecorder;
let audioChunks = [];

async function startRecording() {
    if (isRecording) return;

    status.textContent = "🎤 Parla ora...";
    micBtn.classList.add('recording');
    isRecording = true;
    audioChunks = [];

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);

        // --- ADVANCED VAD SETUP ---
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(stream);
        const vad = new VAD(audioContext, source);

        let silenceTimer = null;
        vad.on('voice_stop', () => {
            // User stopped talking, wait 1s to be sure, then stop recording
            if (!silenceTimer) {
                silenceTimer = setTimeout(() => {
                    if (isRecording && mediaRecorder.state === "recording") {
                        mediaRecorder.stop();
                        vad.destroy();
                        audioContext.close();
                    }
                }, 1000); // 1 second of silence
            }
        });
        vad.on('voice_start', () => {
            // User started talking again, clear silence timer
            if (silenceTimer) {
                clearTimeout(silenceTimer);
                silenceTimer = null;
            }
        });
        // --- END ADVANCED VAD SETUP ---

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            if (audioContext && audioContext.state !== "closed") audioContext.close();
            status.textContent = "⏳ Trascrizione in corso...";
            micBtn.classList.remove('recording');
            micBtn.classList.add('processing');
            isRecording = false;

            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('audio', audioBlob, 'input.webm');

            fetch('/transcribe', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.transcript && data.transcript.length > 0) {
                    status.textContent = "🗣️ Risposta vocale in corso...";
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

        // Remove the old setTimeout for 8 seconds!

        micBtn.onclick = () => {
            if (isRecording && mediaRecorder.state === "recording") {
                mediaRecorder.stop();
                vad.destroy();
                audioContext.close();
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

    if (connectionStatus) {
        connectionStatus.textContent = "🟢 Pronto (TTS Google Cloud)";
        connectionStatus.className = "connection-status online";
    }

    if (activationStatus) {
        activationStatus.textContent = "🎧 Pronto per la registrazione vocale";
    }
});
