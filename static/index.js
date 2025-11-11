// OtoBot Professional Italian Voice Assistant (Cross-Platform Optimized)
// Professional Enterprise Version: Windows/iOS/Android Compatible

let isRecording = false;
let isInitialized = false;
let audioContext = null;
let videoInitialized = false;

// UI elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');

// Device detection for iOS/Android specific handling
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
const isAndroid = /Android/.test(navigator.userAgent);
const isMobile = isIOS || isAndroid || /Mobi|Android/i.test(navigator.userAgent);

// Helper function to safely update status with professional logging
function updateStatus(text) {
    if (status) {
        status.textContent = text;
        console.log(`[OtoBot Status]: ${text}`);
    }
}

// --- Voice Synthesis via Backend Google TTS ---
// --- Cross-Platform Video Control (iOS/Android/Windows Compatible) ---
function initializeVideos() {
    return new Promise((resolve) => {
        const avatarStill = document.getElementById('avatar-still');
        const avatarMove = document.getElementById('avatar-move');
        const micVideo = document.getElementById('micVideo');
        
        if (avatarStill) {
            // iOS requires explicit play preparation
            avatarStill.muted = true;
            avatarStill.playsInline = true;
            avatarStill.preload = 'metadata';
            
            // For iOS: Prepare video for playback
            if (isIOS || isMobile) {
                avatarStill.load();
            }
        }
        
        if (avatarMove) {
            avatarMove.muted = true;
            avatarMove.playsInline = true;
            avatarMove.preload = 'metadata';
            
            if (isIOS || isMobile) {
                avatarMove.load();
            }
        }
        
        if (micVideo) {
            micVideo.muted = true;
            micVideo.playsInline = true;
            micVideo.preload = 'metadata';
            
            if (isIOS || isMobile) {
                micVideo.load();
            }
        }
        
        videoInitialized = true;
        console.log('[OtoBot]: Videos initialized for cross-platform compatibility');
        resolve();
    });
}

function showMoveZloop() {
    const avatarStill = document.getElementById('avatar-still');
    const avatarMove = document.getElementById('avatar-move');
    
    if (!avatarStill || !avatarMove) return;
    
    // Professional error handling with iOS compatibility
    try {
        // Stop still video first
        avatarStill.pause();
        avatarStill.style.opacity = '0';
        
        // Prepare move video
        avatarMove.loop = true;
        avatarMove.style.opacity = '1';
        avatarMove.currentTime = 0;
        
        // iOS-compatible play with promise handling
        const playPromise = avatarMove.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.log('[OtoBot Warning]: Avatar move video play blocked:', error.message);
                // Fallback: Just show the still video
                avatarStill.style.opacity = '1';
                avatarMove.style.opacity = '0';
            });
        }
    } catch (error) {
        console.log('[OtoBot Error]: Video control error:', error.message);
        // Ensure at least still video is visible
        if (avatarStill) avatarStill.style.opacity = '1';
    }
}

function endMoveZloop() {
    const avatarStill = document.getElementById('avatar-still');
    const avatarMove = document.getElementById('avatar-move');
    
    if (!avatarStill || !avatarMove) return;
    
    try {
        // Stop move video
        avatarMove.loop = false;
        avatarMove.pause();
        avatarMove.style.opacity = '0';
        
        // Start still video with iOS compatibility
        avatarStill.currentTime = 0;
        avatarStill.style.opacity = '1';
        
        const playPromise = avatarStill.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.log('[OtoBot Warning]: Avatar still video play blocked:', error.message);
                // Video blocked but that's okay, just show it
            });
        }
    } catch (error) {
        console.log('[OtoBot Error]: Video end control error:', error.message);
    }
}
// --- Cross-Platform Audio Context Management ---
function initializeAudioContext() {
    try {
        // Create AudioContext only within user gesture for iOS compatibility
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        
        // Resume AudioContext if suspended (iOS requirement)
        if (audioContext.state === 'suspended') {
            return audioContext.resume();
        }
        
        return Promise.resolve();
    } catch (error) {
        console.log('[OtoBot Warning]: AudioContext initialization failed:', error.message);
        return Promise.resolve(); // Continue without AudioContext
    }
}

function speakWithGoogleTTS(text) {
    micBtn.classList.remove('pulse-green');
    
    // Initialize audio context first (iOS requirement)
    initializeAudioContext().then(() => {
        return fetch('/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
    })
    .then(response => response.blob())
    .then(blob => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        
        // iOS-specific audio preparation
        if (isIOS || isMobile) {
            audio.preload = 'auto';
            audio.load();
        }
        
        let safetyTimer = setTimeout(() => {
            endMoveZloop();
            console.log('[OtoBot]: Safety timer triggered - ending avatar animation');
        }, 120000); // 2 minutes safety timer
        
        // Professional audio playback with iOS compatibility
        const playPromise = audio.play();
        if (playPromise !== undefined) {
            playPromise.then(() => {
                console.log('[OtoBot]: Audio playback started successfully');
                
                // Start avatar animation after 1 second
                setTimeout(() => {
                    if (!videoInitialized) {
                        initializeVideos().then(() => showMoveZloop());
                    } else {
                        showMoveZloop();
                    }
                }, 1000);
                
            }).catch(error => {
                console.log('[OtoBot Error]: Audio play blocked:', error.message);
                clearTimeout(safetyTimer);
                endMoveZloop();
                micBtn.classList.remove('pulse-green');
                
                // Show error to user on mobile devices
                if (isMobile) {
                    updateStatus("🔊 Tocca per attivare l'audio");
                }
            });
        }
        
        audio.onended = function() {
            clearTimeout(safetyTimer);
            endMoveZloop();
            micBtn.classList.remove('pulse-green');
            updateStatus("✅ Pronto per nuova conversazione");
        };
        
        audio.onerror = function(error) {
            console.log('[OtoBot Error]: Audio playback error:', error);
            clearTimeout(safetyTimer);
            endMoveZloop();
            micBtn.classList.remove('pulse-green');
            updateStatus("❌ Errore audio - riprova");
        };
    })
    .catch(error => {
        console.log('[OtoBot Error]: TTS fetch failed:', error);
        micBtn.classList.remove('pulse-green');
        updateStatus("❌ Errore connessione TTS");
    });
}

// --- Cross-Platform Audio Recording (iOS/Android/Windows Compatible) ---
let mediaRecorder;
let audioChunks = [];

// iOS-compatible MediaRecorder check
function checkMediaRecorderSupport() {
    if (!window.MediaRecorder) {
        return { supported: false, reason: 'MediaRecorder not available' };
    }
    
    // Check for iOS-compatible formats
    const testFormats = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/wav'];
    let supportedFormat = null;
    
    for (const format of testFormats) {
        if (MediaRecorder.isTypeSupported(format)) {
            supportedFormat = format;
            break;
        }
    }
    
    return { 
        supported: !!supportedFormat, 
        format: supportedFormat,
        reason: supportedFormat ? null : 'No supported audio formats'
    };
}

async function startRecording() {
    if (isRecording) return;

    // Initialize audio and video contexts for iOS
    if (!isInitialized) {
        await initializeAudioContext();
        if (!videoInitialized) {
            await initializeVideos();
        }
        isInitialized = true;
    }

    updateStatus("🎤 Parla ora...");
    micBtn.classList.add('recording');
    isRecording = true;
    audioChunks = [];
    
    // Start microphone video with iOS compatibility
    const micVideo = document.getElementById('micVideo');
    if (micVideo) {
        try {
            micVideo.currentTime = 0;
            micVideo.loop = true;
            
            const playPromise = micVideo.play();
            if (playPromise !== undefined) {
                playPromise.catch(error => {
                    console.log('[OtoBot Warning]: Mic video play blocked:', error.message);
                    // Continue recording even if video fails
                });
            }
        } catch (error) {
            console.log('[OtoBot Warning]: Mic video error:', error.message);
        }
    }

    try {
        // Professional cross-platform audio constraints
        const audioConstraints = {
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                sampleRate: isIOS ? 48000 : 44100, // iOS prefers 48kHz
                channelCount: 1
            }
        };
        
        const stream = await navigator.mediaDevices.getUserMedia(audioConstraints);
        
        // Check MediaRecorder support with detailed logging
        const mediaSupport = checkMediaRecorderSupport();
        if (!mediaSupport.supported) {
            throw new Error(`Recording not supported: ${mediaSupport.reason}`);
        }
        
        // Professional format selection with iOS/Android compatibility
        const recordingOptions = { mimeType: mediaSupport.format };
        
        // Add additional iOS-specific options
        if (isIOS && mediaSupport.format.includes('mp4')) {
            recordingOptions.audioBitsPerSecond = 128000;
        }
        
        console.log(`[OtoBot]: Using recording format: ${mediaSupport.format}`);
        mediaRecorder = new MediaRecorder(stream, recordingOptions);

        mediaRecorder.ondataavailable = event => {
            if (event.data && event.data.size > 0) {
                audioChunks.push(event.data);
                console.log(`[OtoBot]: Audio chunk received: ${event.data.size} bytes`);
            }
        };

        mediaRecorder.onstop = async () => {
            updateStatus("⏳ Trascrizione in corso...");
            micBtn.classList.remove('recording');
            micBtn.classList.add('processing');
            isRecording = false;
            
            // Stop microphone video with professional error handling
            const micVideo = document.getElementById('micVideo');
            if (micVideo) {
                try {
                    micVideo.pause();
                    micVideo.currentTime = 0;
                    micVideo.loop = false;
                } catch (error) {
                    console.log('[OtoBot Warning]: Mic video stop error:', error.message);
                }
            }

            // Professional blob creation with format detection
            let blobType = 'audio/webm';
            let fileName = 'input.webm';
            
            if (isIOS && mediaSupport.format.includes('mp4')) {
                blobType = 'audio/mp4';
                fileName = 'input.mp4';
            } else if (mediaSupport.format.includes('wav')) {
                blobType = 'audio/wav';
                fileName = 'input.wav';
            }
            
            console.log(`[OtoBot]: Creating audio blob with type: ${blobType}`);
            const audioBlob = new Blob(audioChunks, { type: blobType });
            
            if (audioBlob.size === 0) {
                updateStatus("❌ Nessun audio registrato");
                resetMicButton();
                return;
            }
            
            console.log(`[OtoBot]: Audio blob created: ${audioBlob.size} bytes`);
            const formData = new FormData();
            formData.append('audio', audioBlob, fileName);

            // Professional transcription with comprehensive error handling
            fetch('/transcribe', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Server error: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('[OtoBot]: Transcription response:', data);
                
                if (data.transcript && data.transcript.trim().length > 0) {
                    updateStatus("🗣️ Risposta vocale in corso...");
                    console.log(`[OtoBot]: Transcript received: "${data.transcript}"`);
                    
                    // Professional voice activation detection
                    fetch('/voice_activation', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: data.transcript
                        })
                    })
                    .then(response => response.json())
                    .then(activationData => {
                        if (activationData.activated && activationData.reply) {
                            console.log('[OtoBot]: Voice activation detected');
                            speakWithGoogleTTS(activationData.reply);
                            updateStatus("✅ OtoBot attivato! Pronto per nuova conversazione");
                            resetMicButton();
                        } else {
                            // Professional chat processing
                            fetch('/chat', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    message: data.transcript,
                                    voice: true
                                })
                            })
                            .then(response => {
                                if (!response.ok) {
                                    throw new Error(`Chat server error: ${response.status}`);
                                }
                                return response.json();
                            })
                            .then(chatData => {
                                if (chatData.reply && chatData.reply.trim().length > 0) {
                                    console.log(`[OtoBot]: Chat response: "${chatData.reply.substring(0, 100)}..."`);
                                    speakWithGoogleTTS(chatData.reply);
                                    updateStatus("✅ Pronto per nuova conversazione");
                                } else {
                                    updateStatus("❌ Nessuna risposta trovata");
                                }
                                resetMicButton();
                            })
                            .catch(error => {
                                console.log('[OtoBot Error]: Chat processing failed:', error);
                                updateStatus("❌ Errore elaborazione risposta");
                                resetMicButton();
                            });
                        }
                    })
                    .catch(error => {
                        console.log('[OtoBot Warning]: Voice activation check failed, using normal chat:', error);
                        // Professional fallback to normal chat
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
                                updateStatus("❌ Nessuna risposta trovata");
                            }
                            resetMicButton();
                        })
                        .catch(error => {
                            console.log('[OtoBot Error]: Fallback chat failed:', error);
                            updateStatus("❌ Errore sistema chat");
                            resetMicButton();
                        });
                    });
                } else {
                    console.log('[OtoBot]: No transcript received or empty transcript');
                    updateStatus("❌ Nessuna voce rilevata - riprova");
                    resetMicButton();
                }
            })
            .catch(error => {
                console.log('[OtoBot Error]: Transcription failed:', error);
                updateStatus("❌ Errore trascrizione - controlla connessione");
                resetMicButton();
            });
        };

        // Professional recording start with iOS compatibility
        try {
            mediaRecorder.start();
            console.log('[OtoBot]: Recording started successfully');
            
            // Clean event listener management
            micBtn.removeEventListener('click', toggleRecording);
            
            const stopHandler = function() {
                if (isRecording && mediaRecorder && mediaRecorder.state === "recording") {
                    console.log('[OtoBot]: Stopping recording via button click');
                    mediaRecorder.stop();
                    // Clean up temporary handler
                    micBtn.removeEventListener('click', stopHandler);
                }
            };
            micBtn.addEventListener('click', stopHandler);
            
        } catch (recordingError) {
            console.log('[OtoBot Error]: Failed to start recording:', recordingError);
            updateStatus("❌ Errore avvio registrazione");
            resetMicButton();
            isRecording = false;
        }

    } catch (error) {
        console.log('[OtoBot Error]: Microphone access failed:', error);
        
        // Professional error messages based on error type
        if (error.name === 'NotAllowedError') {
            updateStatus("❌ Permesso microfono negato - abilita nelle impostazioni");
        } else if (error.name === 'NotFoundError') {
            updateStatus("❌ Microfono non trovato");
        } else if (error.name === 'NotSupportedError') {
            updateStatus("❌ Registrazione non supportata su questo dispositivo");
        } else {
            updateStatus(`❌ Errore microfono: ${error.message}`);
        }
        
        resetMicButton();
        isRecording = false;
    }
}

function resetMicButton() {
    try {
        micBtn.classList.remove('recording', 'processing');
        micBtn.classList.add('pulse-green');
        
        // Professional event listener management
        micBtn.removeEventListener('click', toggleRecording);
        micBtn.addEventListener('click', toggleRecording);
        
        console.log('[OtoBot]: Microphone button reset successfully');
    } catch (error) {
        console.log('[OtoBot Warning]: Button reset error:', error.message);
    }
}

// Professional user interaction handler with iOS compatibility
function handleUserInteraction() {
    console.log('[OtoBot]: User interaction detected - initializing systems');
    
    // Initialize audio and video systems on first user interaction (iOS requirement)
    if (!isInitialized) {
        Promise.all([
            initializeAudioContext(),
            initializeVideos()
        ]).then(() => {
            isInitialized = true;
            console.log('[OtoBot]: All systems initialized successfully');
            updateStatus("🎧 Pronto per la registrazione vocale");
        }).catch(error => {
            console.log('[OtoBot Warning]: System initialization partial failure:', error);
            // Continue anyway - some features may still work
            isInitialized = true;
        });
    }
}

function toggleRecording() {
    // Ensure initialization on user interaction (iOS requirement)
    handleUserInteraction();
    
    if (!isRecording) {
        console.log('[OtoBot]: Starting recording session');
        startRecording();
    } else {
        console.log('[OtoBot]: Stopping recording session');
        if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
        }
    }
}

// --- Professional Cross-Platform Initialization ---
document.addEventListener('DOMContentLoaded', function() {
    console.log('[OtoBot]: Application starting - Cross-platform mode');
    console.log(`[OtoBot]: Device detected - iOS: ${isIOS}, Android: ${isAndroid}, Mobile: ${isMobile}`);
    
    // Professional capability checks
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        updateStatus("❌ Microfono non supportato dal browser");
        if (micBtn) micBtn.disabled = true;
        console.log('[OtoBot Error]: MediaDevices not supported');
        return;
    }

    // Professional security check
    if (!(location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
        updateStatus("❌ Richiesto HTTPS per funzioni vocali");
        if (micBtn) micBtn.disabled = true;
        console.log('[OtoBot Error]: HTTPS required for production');
        return;
    }

    // Professional MediaRecorder support check
    const mediaSupport = checkMediaRecorderSupport();
    if (!mediaSupport.supported) {
        updateStatus("❌ Registrazione audio non supportata");
        if (micBtn) micBtn.disabled = true;
        console.log('[OtoBot Error]: MediaRecorder not supported:', mediaSupport.reason);
        return;
    }

    console.log(`[OtoBot]: MediaRecorder supported with format: ${mediaSupport.format}`);

    if (micBtn) {
        // Professional button setup
        micBtn.addEventListener('click', toggleRecording);
        micBtn.disabled = false;
        micBtn.style.opacity = '1';
        micBtn.style.cursor = 'pointer';
        
        // Add mobile-specific touch events for better iOS/Android response
        if (isMobile) {
            micBtn.addEventListener('touchstart', function(e) {
                e.preventDefault(); // Prevent double-tap zoom on iOS
                handleUserInteraction();
            }, { passive: false });
        }
        
        console.log('[OtoBot]: Microphone button initialized successfully');
    }

    // Professional status display setup
    const connectionStatus = document.getElementById('connectionStatus');
    const activationStatus = document.getElementById('activationStatus');
    
    if (connectionStatus) {
        connectionStatus.textContent = "🟢 Pronto (TTS Google Cloud)";
        connectionStatus.className = "connection-status online";
    }

    if (activationStatus) {
        if (isMobile) {
            activationStatus.textContent = "📱 Tocca il microfono per iniziare";
        } else {
            activationStatus.textContent = "🎧 Pronto per la registrazione vocale";
        }
    }
    
    // Professional initialization status
    updateStatus(isMobile ? "📱 Tocca microfono per attivare" : "🎧 Clicca microfono per iniziare");
    
    // Pre-initialize videos on desktop (not on mobile due to autoplay policies)
    if (!isMobile) {
        initializeVideos().then(() => {
            console.log('[OtoBot]: Desktop videos pre-initialized');
        }).catch(error => {
            console.log('[OtoBot Warning]: Desktop video pre-initialization failed:', error.message);
        });
    }
    
    console.log('[OtoBot]: Application initialization completed successfully');
});
