// OtoBot Professional Italian Voice Assistant (Google Cloud Charon Voice)

let isRecording = false;
let isListening = false;
let recognition = null;
let continuousListening = true;

// UI elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const activationStatus = document.getElementById('activationStatus');
const connectionStatus = document.getElementById('connectionStatus');

// --- Voice Synthesis via Backend Google TTS ---
function speakWithGoogleTTS(text) {
    fetch('/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
    })
    .then(response => response.blob())
    .then(blob => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.play();
    });
}

// --- Hotword Detection ("Hey OtoBot") ---
function initVoiceActivation() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        activationStatus.textContent = "🎧 Hey OtoBot non supportato dal browser";
        return false;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();

    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'it-IT';
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        isListening = true;
        activationStatus.textContent = "🎧 Ascolto 'Hey OtoBot': ATTIVO";
        activationStatus.classList.add('listening');
    };

    recognition.onend = () => {
        isListening = false;
        activationStatus.textContent = "🎧 Ascolto 'Hey OtoBot': SPENTO";
        activationStatus.classList.remove('listening');
        if (continuousListening) {
            setTimeout(() => {
                startVoiceActivation();
            }, 1000);
        }
    };

    recognition.onresult = (event) => {
        const transcript = event.results[event.resultIndex][0].transcript.toLowerCase();

        // Hotword patterns
        const activationPatterns = [
            'hey otobot', 'otobot', 'oto bot', 'ciao otobot',
            'salve otobot', 'buongiorno otobot', 'assistente otofarma'
        ];

        let activated = false;
        for (const pattern of activationPatterns) {
            if (transcript.includes(pattern)) {
                activated = true;
                break;
            }
        }

        if (activated) {
            status.textContent = "🔥 Hey OtoBot attivato! Generando saluto...";
            recognition.stop();

            fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: transcript,
                    voice: true
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.reply) {
                    status.textContent = "🗣️ Risposta vocale in corso...";
                    speakWithGoogleTTS(data.reply);
                    status.textContent = "✅ Pronto per nuova conversazione";
                    setTimeout(() => {
                        if (continuousListening) {
                            startVoiceActivation();
                        }
                    }, 2000);
                }
            })
            .catch(() => {
                setTimeout(() => {
                    if (continuousListening) {
                        startVoiceActivation();
                    }
                }, 2000);
            });
        }
    };

    recognition.onerror = () => {
        setTimeout(() => {
            if (!isListening && continuousListening) {
                startVoiceActivation();
            }
        }, 2000);
    };

    return true;
}

function startVoiceActivation() {
    if (recognition && !isListening && continuousListening) {
        try {
            recognition.start();
        } catch (error) {}
    }
}

// --- Microphone Button: Record, Auto-stop, Transcribe, Send, Auto-Play ---
async function startRecording() {
    if (isRecording) return;

    continuousListening = false;
    if (recognition && isListening) recognition.stop();

    try {
        status.textContent = "🎤 Parla ora...";
        isRecording = true;
        micBtn.textContent = '🔴';
        micBtn.classList.add('recording');

        // Use browser SpeechRecognition for transcription
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recorder = new SpeechRecognition();
        recorder.lang = 'it-IT';
        recorder.interimResults = false;
        recorder.maxAlternatives = 1;

        recorder.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            status.textContent = "⏳ Risposta in corso...";
            micBtn.textContent = '⚙️';
            micBtn.classList.remove('recording');
            micBtn.classList.add('processing');
            isRecording = false;

            fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: transcript,
                    voice: true
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.reply) {
                    status.textContent = "🗣️ Risposta vocale in corso...";
                    speakWithGoogleTTS(data.reply);
                    status.textContent = "✅ Pronto per nuova conversazione";
                }
                resetMicButton();
                continuousListening = true;
                setTimeout(() => {
                    startVoiceActivation();
                }, 2000);
            });
        };

        recorder.onerror = (event) => {
            status.textContent = "❌ Errore trascrizione o nessuna voce rilevata";
            resetMicButton();
            continuousListening = true;
            setTimeout(() => {
                startVoiceActivation();
            }, 2000);
        };

        recorder.onend = () => {
            if (isRecording) {
                status.textContent = "❌ Nessuna voce rilevata";
                resetMicButton();
                continuousListening = true;
                setTimeout(() => {
                    startVoiceActivation();
                }, 2000);
            }
        };

        recorder.start();

    } catch (error) {
        status.textContent = `❌ Errore microfono: ${error.message}`;
        isRecording = false;
        micBtn.textContent = '🎤';
        micBtn.classList.remove('recording');
        continuousListening = true;
        setTimeout(() => {
            startVoiceActivation();
        }, 2000);
    }
}

function stopRecording() {
    // Not needed: browser SpeechRecognition auto-stops on silence
}

function resetMicButton() {
    micBtn.textContent = '🎤';
    micBtn.classList.remove('recording', 'processing');
}

function toggleRecording() {
    if (!isRecording) {
        startRecording();
    }
    // No manual stop needed; auto-stops on silence
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', function() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        status.textContent = "❌ Browser non supportato. Usa Chrome, Firefox o Safari aggiornati.";
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

    if (initVoiceActivation()) {
        setTimeout(() => {
            startVoiceActivation();
        }, 1000);
    }
});
