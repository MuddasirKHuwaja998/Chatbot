// Voice Assistant Variables for VOSK + TTS Backend Integration
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let stream = null;
let lastActivationTime = 0;
const ACTIVATION_COOLDOWN = 3000;

// UI Elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const audioReply = document.getElementById('audioReply');

// Check if voice processing is available on backend
async function checkVoiceAvailability() {
    try {
        const response = await fetch('/voice_status');
        const data = await response.json();
        console.log('Voice status:', data);
        
        if (data.voice_available) {
            status.textContent = "🎤 Assistente vocale pronto - Premi e tieni premuto per parlare";
            return true;
        } else {
            status.textContent = "❌ Assistente vocale non disponibile";
            return false;
        }
    } catch (error) {
        console.error('Error checking voice status:', error);
        status.textContent = "⚠️ Errore connessione vocale";
        return false;
    }
}

// Voice Activation Detection (using Web Speech API for "otobot" detection)
let recognition = null;
let isListening = false;

function initializeVoiceActivation() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        console.warn('Speech recognition not supported');
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'it-IT';

    recognition.onresult = function(event) {
        const currentTime = Date.now();
        if (currentTime - lastActivationTime < ACTIVATION_COOLDOWN) return;

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript.toLowerCase().trim();
            
            if (event.results[i].isFinal) {
                console.log('Voice activation check:', transcript);
                
                if (isOtoBotActivation(transcript)) {
                    lastActivationTime = currentTime;
                    handleVoiceActivation();
                    break;
                }
            }
        }
    };

    recognition.onerror = function(event) {
        console.error('Speech recognition error:', event.error);
        setTimeout(() => {
            if (!isListening) startVoiceActivation();
        }, 1000);
    };

    recognition.onend = function() {
        isListening = false;
        setTimeout(() => {
            if (!isListening) startVoiceActivation();
        }, 500);
    };
}

// Precise OtoBot activation detection
function isOtoBotActivation(transcript) {
    const normalized = transcript
        .toLowerCase()
        .replace(/[^\w\s]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    
    const patterns = [
        'otobot',
        'oto bot',
        'ciao otobot',
        'salve otobot',
        'hey otobot',
        'assistente virtuale',
        'assistente otofarma'
    ];

    return patterns.some(pattern => 
        normalized === pattern || 
        normalized.includes(pattern) ||
        normalized.split(' ').includes('otobot')
    );
}

// Handle voice activation
async function handleVoiceActivation() {
    console.log('🎯 OtoBot activated via voice!');
    stopVoiceActivation();
    
    micBtn.classList.add('listening');
    status.textContent = "🤖 OtoBot attivato! Elaborazione...";
    
    try {
        // Send activation to backend
        const response = await fetch('/voice_activation', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: 'otobot'})
        });

        if (response.ok) {
            const data = await response.json();
            if (data.activated) {
                // Use your backend TTS instead of browser TTS
                await sendTextToBackendTTS(data.reply);
            }
        }
    } catch (error) {
        console.error('Activation error:', error);
    }
    
    micBtn.classList.remove('listening');
    setTimeout(() => startVoiceActivation(), 2000);
}

// Start voice activation listening
function startVoiceActivation() {
    if (!recognition || isListening) return;
    
    try {
        isListening = true;
        recognition.start();
        console.log('👂 Listening for "OtoBot" activation...');
    } catch (error) {
        console.error('Error starting voice activation:', error);
        isListening = false;
    }
}

// Stop voice activation listening
function stopVoiceActivation() {
    if (recognition && isListening) {
        recognition.stop();
        isListening = false;
    }
}

// Send text to backend TTS (for activation responses)
async function sendTextToBackendTTS(text) {
    try {
        status.textContent = "🔊 Generazione voce italiana...";
        
        // Create a FormData with text as audio (dummy audio for TTS-only)
        const formData = new FormData();
        
        // Create a minimal audio blob for the backend
        const audioBlob = new Blob(['dummy'], {type: 'audio/wav'});
        formData.append('audio', audioBlob, 'activation.wav');
        
        // Instead, use chat endpoint for activation
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                message: text,
                voice: true
            })
        });

        if (response.ok) {
            const data = await response.json();
            status.textContent = "✅ Risposta pronta";
            console.log('Backend response:', data.reply);
        }
        
    } catch (error) {
        console.error('TTS error:', error);
        status.textContent = "❌ Errore generazione voce";
    }
}

// Main microphone recording functionality
micBtn.addEventListener('mousedown', startRecording);
micBtn.addEventListener('touchstart', startRecording);
micBtn.addEventListener('mouseup', stopRecording);
micBtn.addEventListener('mouseleave', stopRecording);
micBtn.addEventListener('touchend', stopRecording);

async function startRecording(e) {
    e.preventDefault();
    if (isRecording) return;

    stopVoiceActivation(); // Stop background listening
    
    try {
        stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true
            }
        });
        
        mediaRecorder = new MediaRecorder(stream, {
            mimeType: 'audio/webm;codecs=opus'
        });
        
        audioChunks = [];
        isRecording = true;
        
        micBtn.classList.add('listening');
        status.textContent = "🎤 Sto ascoltando... (tieni premuto)";

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            await processRecordedAudio();
        };

        mediaRecorder.start(100); // Collect data every 100ms
        
    } catch (error) {
        console.error('Microphone access error:', error);
        status.textContent = "❌ Errore accesso microfono";
        isRecording = false;
        micBtn.classList.remove('listening');
    }
}

function stopRecording(e) {
    e.preventDefault();
    if (!isRecording || !mediaRecorder) return;

    status.textContent = "⏳ Elaborazione audio...";
    mediaRecorder.stop();
    isRecording = false;
    
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
}

// Process recorded audio through VOSK + TTS backend
async function processRecordedAudio() {
    if (audioChunks.length === 0) {
        status.textContent = "❌ Nessun audio registrato";
        micBtn.classList.remove('listening');
        setTimeout(() => startVoiceActivation(), 1000);
        return;
    }

    try {
        status.textContent = "🧠 Elaborazione con VOSK + TTS...";
        
        // Create audio blob
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        console.log('Audio blob size:', audioBlob.size);
        
        // Send to backend voice processing
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.wav');

        const response = await fetch('/voice', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            // Backend returns Italian male TTS audio
            const audioResponseBlob = await response.blob();
            
            if (audioResponseBlob.size > 0) {
                status.textContent = "🔊 Riproduzione risposta italiana...";
                
                // Play the Italian male TTS response
                const audioUrl = URL.createObjectURL(audioResponseBlob);
                const audio = new Audio(audioUrl);
                
                audio.onloadeddata = () => {
                    console.log('🎵 Playing Italian male TTS response');
                };
                
                audio.onended = () => {
                    status.textContent = "✅ Conversazione completata";
                    URL.revokeObjectURL(audioUrl);
                    setTimeout(() => {
                        status.textContent = "🎤 Premi per parlare o dì 'OtoBot'";
                        startVoiceActivation();
                    }, 1000);
                };
                
                audio.onerror = (error) => {
                    console.error('Audio playback error:', error);
                    status.textContent = "❌ Errore riproduzione audio";
                };
                
                await audio.play();
            } else {
                status.textContent = "❌ Risposta audio vuota";
            }
        } else {
            const errorData = await response.json();
            console.error('Voice processing error:', errorData);
            status.textContent = `❌ ${errorData.error || 'Errore elaborazione vocale'}`;
        }
        
    } catch (error) {
        console.error('Voice processing error:', error);
        status.textContent = "❌ Errore durante l'elaborazione";
    }
    
    micBtn.classList.remove('listening');
    audioChunks = [];
    
    // Restart voice activation after processing
    setTimeout(() => {
        if (!isListening) {
            status.textContent = "🎤 Premi per parlare o dì 'OtoBot'";
            startVoiceActivation();
        }
    }, 2000);
}

// Initialize everything when page loads
document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 OtoBot Voice-to-Voice Assistant initializing...');
    
    // Check if backend voice processing is available
    const voiceAvailable = await checkVoiceAvailability();
    
    if (voiceAvailable) {
        // Initialize voice activation listening
        initializeVoiceActivation();
        setTimeout(() => {
            startVoiceActivation();
            status.textContent = "🎤 Premi per parlare o dì 'OtoBot' per attivare";
        }, 1000);
        
        console.log('✅ Voice-to-Voice Assistant ready with VOSK + Italian TTS');
    } else {
        console.error('❌ Backend voice processing not available');
        micBtn.disabled = true;
    }
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopVoiceActivation();
        if (isRecording) {
            stopRecording(new Event('visibilitychange'));
        }
    } else {
        setTimeout(() => {
            if (!isListening && !isRecording) startVoiceActivation();
        }, 1000);
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopVoiceActivation();
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
});

// Debug function to test voice status
window.testVoiceStatus = async function() {
    const status = await checkVoiceAvailability();
    console.log('Voice status test result:', status);
};

console.log('🎯 OtoBot Voice Assistant JavaScript loaded - Ready for VOSK + TTS processing');
