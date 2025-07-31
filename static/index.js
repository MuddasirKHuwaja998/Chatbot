// OtoBot Professional Italian Voice Assistant (Google Cloud Charon Voice)
// Medical/Enterprise Version: Backend Speech-to-Text

let isRecording = false;

// UI elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const activationStatus = document.getElementById('activationStatus');
const connectionStatus = document.getElementById('connectionStatus');

// --- Voice Synthesis via Backend Google TTS ---
// --- Avatar video control ---
function showMoveZloop() {
    const avatarStill = document.getElementById('avatar-still');
    const avatarMove = document.getElementById('avatar-move');
    if (avatarStill && avatarMove) {
        avatarStill.pause();
        avatarStill.style.opacity = '0';
        avatarMove.loop = true;
        avatarMove.style.opacity = '1';
        avatarMove.currentTime = 0;
        avatarMove.play();
    }
}

function endMoveZloop() {
    const avatarStill = document.getElementById('avatar-still');
    const avatarMove = document.getElementById('avatar-move');
    if (avatarStill && avatarMove) {
        avatarMove.loop = false;
        avatarMove.pause();
        avatarMove.style.opacity = '0';
        avatarStill.currentTime = 0;
        avatarStill.play();
        avatarStill.style.opacity = '1';
    }
}
function speakWithGoogleTTS(text) {
    micBtn.classList.remove('pulse-green');
    showMoveZloop();
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
            endMoveZloop();
        }, 20000); // 20 secondi
        audio.play();
        audio.onended = function() {
            clearTimeout(safetyTimer);
            endMoveZloop();
        };
        audio.onerror = function() {
            clearTimeout(safetyTimer);
            endMoveZloop();
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
    
    // Avvia il video miclogo.mov in loop
    const micVideo = document.getElementById('micVideo');
    if (micVideo) {
        micVideo.currentTime = 0;
        micVideo.loop = true;
        micVideo.play();
    }

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
            
            // Ferma il video miclogo.mov
            const micVideo = document.getElementById('micVideo');
            if (micVideo) {
                micVideo.pause();
                micVideo.currentTime = 0;
                micVideo.loop = false;
            }

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
        // la registrazione viene fermata solo da un secondo click
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
    micBtn.classList.add('pulse-green');
    micBtn.onclick = toggleRecording;
}

function toggleRecording() {
    if (!isRecording) {
        startRecording();
    } else {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
        }
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
