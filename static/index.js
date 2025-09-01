// OtoBot Professional Italian Voice Assistant (Google Cloud Enhanced)
// Medical/Enterprise Version: Backend Speech-to-Text with Professional UI

let isRecording = false;

// UI elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const activationStatus = document.getElementById('activationStatus');
const connectionStatus = document.getElementById('connectionStatus');

// Professional status management
class StatusManager {
    static updateStatus(message, type = 'default') {
        if (!status) return;
        
        status.textContent = message;
        status.className = type;
        
        // Auto-hide success messages
        if (type === 'success') {
            setTimeout(() => {
                if (status.className === 'success') {
                    status.textContent = '🎧 Pronto per nuova conversazione';
                    status.className = 'default';
                }
            }, 3000);
        }
    }

    static showError(message) {
        this.updateStatus(`❌ ${message}`, 'error');
    }

    static showSuccess(message) {
        this.updateStatus(`✅ ${message}`, 'success');
    }

    static showProcessing(message) {
        this.updateStatus(`⏳ ${message}`, 'processing');
    }
}

// Enhanced avatar video control with error handling
function showMoveZloop() {
    const avatarStill = document.getElementById('avatar-still');
    const avatarMove = document.getElementById('avatar-move');
    
    if (avatarStill && avatarMove) {
        try {
            avatarStill.pause();
            avatarStill.style.opacity = '0';
            avatarMove.loop = true;
            avatarMove.style.opacity = '1';
            avatarMove.currentTime = 0;
            avatarMove.play().catch(error => {
                console.warn('⚠️ Avatar move video play failed:', error);
            });
        } catch (error) {
            console.warn('⚠️ Avatar transition failed:', error);
        }
    }
}

function endMoveZloop() {
    const avatarStill = document.getElementById('avatar-still');
    const avatarMove = document.getElementById('avatar-move');
    
    if (avatarStill && avatarMove) {
        try {
            avatarMove.loop = false;
            avatarMove.pause();
            avatarMove.style.opacity = '0';
            avatarStill.currentTime = 0;
            avatarStill.style.opacity = '1';
            avatarStill.play().catch(error => {
                console.warn('⚠️ Avatar still video play failed:', error);
            });
        } catch (error) {
            console.warn('⚠️ Avatar transition failed:', error);
        }
    }
}

// Professional TTS with enhanced feedback
function speakWithGoogleTTS(text) {
    micBtn.classList.remove('pulse-green');
    
    StatusManager.showProcessing('Generazione vocale in corso...');
    
    fetch('/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.blob();
    })
    .then(blob => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        
        let safetyTimer = setTimeout(() => {
            console.warn('⚠️ TTS safety timeout triggered');
            endMoveZloop();
            StatusManager.updateStatus('🎧 Pronto per nuova conversazione');
        }, 120000); // 2 minutes safety
        
        audio.play().then(() => {
            StatusManager.updateStatus('🗣️ Riproduzione in corso...');
            // Start avatar animation after 1 second
            setTimeout(showMoveZloop, 1000);
        }).catch(error => {
            console.error('❌ Audio play failed:', error);
            StatusManager.showError('Errore riproduzione audio');
            clearTimeout(safetyTimer);
        });
        
        audio.onended = function() {
            clearTimeout(safetyTimer);
            endMoveZloop();
            micBtn.classList.remove('pulse-green');
            StatusManager.showSuccess('Conversazione completata');
            URL.revokeObjectURL(url); // Clean up
        };
        
        audio.onerror = function(error) {
            console.error('❌ Audio error:', error);
            clearTimeout(safetyTimer);
            endMoveZloop();
            micBtn.classList.remove('pulse-green');
            StatusManager.showError('Errore durante la riproduzione');
            URL.revokeObjectURL(url); // Clean up
        };
    })
    .catch(error => {
        console.error('❌ TTS request failed:', error);
        StatusManager.showError('Errore nel servizio vocale');
        endMoveZloop();
        micBtn.classList.remove('pulse-green');
    });
}

// Enhanced audio recording with professional feedback
let mediaRecorder;
let audioChunks = [];

async function startRecording() {
    if (isRecording) return;

    StatusManager.updateStatus('🎤 Parla chiaramente...', 'processing');
    micBtn.classList.add('recording');
    micBtn.classList.remove('pulse-green');
    isRecording = true;
    audioChunks = [];
    
    // Enhanced mic video handling
    const micVideo = document.getElementById('micVideo');
    if (micVideo) {
        try {
            micVideo.currentTime = 0;
            micVideo.loop = true;
            micVideo.play().catch(error => {
                console.warn('⚠️ Mic video play failed:', error);
            });
        } catch (error) {
            console.warn('⚠️ Mic video error:', error);
        }
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                sampleRate: 44100
            }
        });
        
        mediaRecorder = new MediaRecorder(stream, {
            mimeType: 'audio/webm;codecs=opus'
        });

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            StatusManager.showProcessing('Elaborazione riconoscimento vocale...');
            micBtn.classList.remove('recording');
            micBtn.classList.add('processing');
            isRecording = false;
            
            // Stop mic video
            if (micVideo) {
                try {
                    micVideo.pause();
                    micVideo.currentTime = 0;
                    micVideo.loop = false;
                } catch (error) {
                    console.warn('⚠️ Mic video stop error:', error);
                }
            }

            // Stop all tracks to release microphone
            stream.getTracks().forEach(track => track.stop());

            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('audio', audioBlob, 'input.webm');

            try {
                const response = await fetch('/transcribe', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                
                if (data.transcript && data.transcript.length > 0) {
                    StatusManager.showProcessing('Generazione risposta intelligente...');
                    
                    const chatResponse = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: data.transcript,
                            voice: true
                        })
                    });

                    if (!chatResponse.ok) {
                        throw new Error(`Chat HTTP ${chatResponse.status}`);
                    }

                    const chatData = await chatResponse.json();
                    
                    if (chatData.reply) {
                        speakWithGoogleTTS(chatData.reply);
                    } else {
                        StatusManager.showError('Nessuna risposta disponibile');
                        resetMicButton();
                    }
                } else {
                    StatusManager.showError('Messaggio vocale non rilevato');
                    resetMicButton();
                }
            } catch (error) {
                console.error('❌ Processing error:', error);
                StatusManager.showError('Errore nell\'elaborazione vocale');
                resetMicButton();
            }
        };

        mediaRecorder.onerror = (error) => {
            console.error('❌ MediaRecorder error:', error);
            StatusManager.showError('Errore nella registrazione');
            resetMicButton();
        };

        mediaRecorder.start();
        
        // Override click handler during recording
        micBtn.onclick = () => {
            if (isRecording && mediaRecorder.state === "recording") {
                mediaRecorder.stop();
            }
        };

    } catch (error) {
        console.error('❌ Microphone access error:', error);
        StatusManager.showError(`Errore microfono: ${error.message}`);
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

// Professional initialization with enhanced error handling
document.addEventListener('DOMContentLoaded', function() {
    // Check browser compatibility
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        StatusManager.showError('Browser non supportato per registrazione audio');
        if (micBtn) micBtn.disabled = true;
        return;
    }

    // Check HTTPS requirement
    if (!(location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
        StatusManager.showError('Richiesto HTTPS per funzionalità audio');
        if (micBtn) micBtn.disabled = true;
        return;
    }

    // Initialize microphone button
    if (micBtn) {
        micBtn.addEventListener('click', toggleRecording);
        micBtn.disabled = false;
        micBtn.style.opacity = '1';
        micBtn.style.cursor = 'pointer';
        micBtn.classList.add('pulse-green');
    }

    // Update connection status
    if (connectionStatus) {
        connectionStatus.textContent = "🟢 Sistema Professionale Attivo";
        connectionStatus.className = "connection-status online";
    }

    if (activationStatus) {
        activationStatus.textContent = "🎧 Assistente vocale pronto";
    }

    // Initialize with success status
    StatusManager.showSuccess('Sistema inizializzato correttamente');
    
    console.log('🚀 OtoBot Professional Assistant initialized');
});
