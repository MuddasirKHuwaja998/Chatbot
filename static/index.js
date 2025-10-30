// OtoBot Professional Italian Voice Assistant (Google Cloud Charon Voice)
// Medical/Enterprise Version: Backend Speech-to-Text

let isRecording = false;

// UI elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');

// Helper function to safely update status
function updateStatus(text) {
    if (status) status.textContent = text;
}

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
        }, 1200000); // 2 minuti
        audio.play();
        
        // Aspetta 1 secondo prima di far partire il video move
        setTimeout(() => {
            showMoveZloop();
        }, 1000);
        
        audio.onended = function() {
            clearTimeout(safetyTimer);
            endMoveZloop();
            micBtn.classList.remove('pulse-green');
        };
        audio.onerror = function() {
            clearTimeout(safetyTimer);
            endMoveZloop();
            micBtn.classList.remove('pulse-green');
        };
    });
}

// --- Audio Recording and Backend Transcription ---
let mediaRecorder;
let audioChunks = [];

async function startRecording() {
    if (isRecording) return;

    updateStatus("🎤 Parla ora...");
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
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: { 
                echoCancellation: true,
                noiseSuppression: true,
                sampleRate: 44100 
            } 
        });
        
        // iOS Safari compatibility check
        let options = {};
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
            options = { mimeType: 'audio/webm;codecs=opus' };
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
            options = { mimeType: 'audio/mp4' };
        }
        
        mediaRecorder = new MediaRecorder(stream, options);

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            updateStatus("⏳ Trascrizione in corso...");
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
                    updateStatus("🗣️ Risposta vocale in corso...");
                    
                    // ENHANCED: Check for voice activation first (Hey OtoBot detection)
                    fetch('/voice_activation', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: data.transcript
                        })
                    })
                    .then(response => response.json())
                    .then(activationData => {
                        // If voice activation detected, use that response
                        if (activationData.activated && activationData.reply) {
                            speakWithGoogleTTS(activationData.reply);
                            updateStatus("✅ OtoBot attivato! Pronto per nuova conversazione");
                            resetMicButton();
                        } else {
                            // Otherwise, proceed with normal chat flow
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
                                    updateStatus("✅ Pronto per nuova conversazione");
                                } else {
                                    updateStatus("❌ Nessuna risposta trovata.");
                                }
                                resetMicButton();
                            });
                        }
                    })
                    .catch(() => {
                        // Fallback to normal chat if voice activation fails
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
                                updateStatus("✅ Pronto per nuova conversazione");
                            } else {
                                updateStatus("❌ Nessuna risposta trovata.");
                            }
                            resetMicButton();
                        });
                    });
                } else {
                    updateStatus("❌ Nessuna voce rilevata o trascrizione fallita.");
                    resetMicButton();
                }
            })
            .catch(() => {
                updateStatus("❌ Errore nella trascrizione.");
                resetMicButton();
            });
        };

         mediaRecorder.start();
        // Store reference for proper cleanup
        micBtn.removeEventListener('click', toggleRecording);
        
        const stopHandler = function() {
            if (isRecording && mediaRecorder.state === "recording") {
                mediaRecorder.stop();
                // Remove this temporary handler
                micBtn.removeEventListener('click', stopHandler);
            }
        };
        micBtn.addEventListener('click', stopHandler);

    } catch (error) {
        updateStatus(`❌ Errore microfono: ${error.message}`);
        resetMicButton();
        isRecording = false;
    }
}

function resetMicButton() {
    micBtn.classList.remove('recording', 'processing');
    micBtn.classList.add('pulse-green');
    
    // iOS fix: Just remove and re-add the event listener
    micBtn.removeEventListener('click', toggleRecording);
    micBtn.addEventListener('click', toggleRecording);
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
        updateStatus("❌ Microfono non supportato dal browser.");
        if (micBtn) micBtn.disabled = true;
        return;
    }

    if (!(location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
        updateStatus("❌ Richiesto HTTPS. Accedi tramite https:// o localhost");
        if (micBtn) micBtn.disabled = true;
        return;
    }

        if (micBtn) {
        // iOS audio context initialization
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        if (audioContext.state === 'suspended') {
            audioContext.resume();
        }
        
        micBtn.addEventListener('click', toggleRecording);
        micBtn.disabled = false;
        micBtn.style.opacity = '1';
        micBtn.style.cursor = 'pointer';
    }

    // Optional status elements
    const connectionStatus = document.getElementById('connectionStatus');
    const activationStatus = document.getElementById('activationStatus');
    
    if (connectionStatus) {
        connectionStatus.textContent = "🟢 Pronto (TTS Google Cloud)";
        connectionStatus.className = "connection-status online";
    }

    if (activationStatus) {
        activationStatus.textContent = "🎧 Pronto per la registrazione vocale";
    }
});
