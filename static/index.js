// OtoBot Professional Italian Voice Assistant (Hands-free Hotword Flow)
// Professional Enterprise Version: Windows/iOS/Android Compatible

const HOTWORD = 'ciao';
// Reduced debounce to react faster while still avoiding obvious duplicates
const HOTWORD_DEBOUNCE_MS = 900;
const HOTWORD_MATCH = HOTWORD.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const VAD_CONFIG = Object.freeze({
    silenceThreshold: 0.012,
    // Accept shorter utterances and reduce silent-hold wait so recording stops earlier
    minSpeechMs: 300,
    silenceHoldMs: 450
});

const VoiceState = Object.freeze({
    IDLE: 'Idle',
    LISTENING: 'Listening',
    RECORDING: 'Recording',
    PROCESSING: 'Processing',
    PLAYING: 'Playing'
});

let currentState = VoiceState.IDLE;
let isInitialized = false;
let audioContext = null;
let videoInitialized = false;
let micStream = null;
let micSource = null;
let vadProcessor = null;
let recordingStartAt = 0;
let lastSpeechAt = 0;
let isRecording = false;
let isProcessing = false;
let isPlaying = false;
let mediaRecorder = null;
let audioChunks = [];
let selectedRecordingFormat = null;
let recognition = null;
let recognitionAutoRestart = false;
let lastHotwordAt = 0;
let hotwordUnavailable = false;
let mediaSupport = null;

const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
const speechRecognitionSupported = Boolean(SpeechRecognitionCtor);

// Device detection for iOS/Android specific handling
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
const isAndroid = /Android/.test(navigator.userAgent);
const isMobile = isIOS || isAndroid || /Mobi|Android/i.test(navigator.userAgent);

// UI elements
const ui = {
    status: document.getElementById('status'),
    permissionError: document.getElementById('permissionError'),
    retryPermissionBtn: document.getElementById('retryPermissionBtn'),
    unsupportedNotice: document.getElementById('unsupportedNotice')
};

const stateClassMap = {
    [VoiceState.LISTENING]: 'state-listening',
    [VoiceState.RECORDING]: 'state-recording',
    [VoiceState.PROCESSING]: 'state-processing',
    [VoiceState.PLAYING]: 'state-playing'
};
const stateClassValues = Object.values(stateClassMap);

// Apple Siri-style Edge Animation
let siriEdge = null;
let siriCanvas = null;
let siriCtx = null;
let siriAnimationFrame = null;
let siriAnimationStartTime = 0;
let siriAnimationActive = false;

function initSiriEdgeAnimation() {
    siriEdge = document.getElementById('siriEdge');
    siriCanvas = document.getElementById('siriCanvas');
    
    if (!siriCanvas) return;
    
    siriCtx = siriCanvas.getContext('2d');
    
    // Set canvas size to match window
    const resizeCanvas = () => {
        const dpr = window.devicePixelRatio || 1;
        siriCanvas.width = window.innerWidth * dpr;
        siriCanvas.height = window.innerHeight * dpr;
        siriCanvas.style.width = window.innerWidth + 'px';
        siriCanvas.style.height = window.innerHeight + 'px';
        siriCtx.scale(dpr, dpr);
    };
    
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
}

function startSiriEdgeAnimation() {
    if (!siriEdge || !siriCanvas || !siriCtx) return;
    
    siriAnimationActive = true;
    siriAnimationStartTime = performance.now();
    siriEdge.classList.add('active');
    
    if (!siriAnimationFrame) {
        animateSiriEdge();
    }
}

function stopSiriEdgeAnimation() {
    siriAnimationActive = false;
    
    if (siriEdge) {
        siriEdge.classList.remove('active');
    }
    
    if (siriAnimationFrame) {
        cancelAnimationFrame(siriAnimationFrame);
        siriAnimationFrame = null;
    }
    
    if (siriCtx && siriCanvas) {
        siriCtx.clearRect(0, 0, siriCanvas.width, siriCanvas.height);
    }
}

function animateSiriEdge() {
    if (!siriAnimationActive || !siriCtx || !siriCanvas) {
        siriAnimationFrame = null;
        return;
    }
    
    const now = performance.now();
    const elapsed = now - siriAnimationStartTime;
    const time = elapsed / 1000;
    
    const w = siriCanvas.width / (window.devicePixelRatio || 1);
    const h = siriCanvas.height / (window.devicePixelRatio || 1);
    
    siriCtx.clearRect(0, 0, w, h);
    
    // Edge border thickness with initial bump effect
    const bumpDuration = 400; // ms
    const bumpIntensity = elapsed < bumpDuration 
        ? 1 + Math.sin((elapsed / bumpDuration) * Math.PI) * 0.6 
        : 1;
    const baseThickness = 4 * bumpIntensity;
    const maxThickness = 28 * bumpIntensity;
    
    // Smooth easing function for fluid animation
    const smoothstep = (x) => {
        x = Math.max(0, Math.min(1, x));
        return x * x * (3 - 2 * x);
    };
    
    const easeInOutCubic = (x) => {
        return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
    };
    
    // Dynamic color palette (Siri-inspired)
    const colors = [
        { r: 45, g: 175, b: 245 },   // Blue
        { r: 140, g: 82, b: 255 },   // Purple
        { r: 255, g: 75, b: 145 },   // Pink
        { r: 75, g: 215, b: 185 },   // Cyan
        { r: 255, g: 165, b: 75 }    // Orange
    ];
    
    // Number of gradient points along each edge (increased for smoother animation)
    const segments = 120;
    
    // Draw top edge
    for (let i = 0; i < segments; i++) {
        const x = (w / segments) * i;
        const progress = i / segments;
        const wave = (Math.sin(time * 1.5 + progress * Math.PI * 3) + 1) / 2;
        const smoothWave = smoothstep(wave);
        const thickness = baseThickness + smoothWave * (maxThickness - baseThickness);
        
        const colorIndex = (Math.floor(time * 0.8 + progress * colors.length)) % colors.length;
        const nextColorIndex = (colorIndex + 1) % colors.length;
        const colorMix = (time * 0.8 + progress * colors.length) % 1;
        
        const c1 = colors[colorIndex];
        const c2 = colors[nextColorIndex];
        const r = Math.floor(c1.r + (c2.r - c1.r) * colorMix);
        const g = Math.floor(c1.g + (c2.g - c1.g) * colorMix);
        const b = Math.floor(c1.b + (c2.b - c1.b) * colorMix);
        
        const gradient = siriCtx.createLinearGradient(x, 0, x, thickness * 2);
        gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.9)`);
        gradient.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, 0.6)`);
        gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);
        
        siriCtx.fillStyle = gradient;
        siriCtx.globalCompositeOperation = 'lighter';
        siriCtx.fillRect(x - 0.5, 0, w / segments + 1.5, thickness * 2);
    }
    
    // Draw bottom edge
    for (let i = 0; i < segments; i++) {
        const x = (w / segments) * i;
        const progress = i / segments;
        const wave = (Math.sin(time * 1.5 + progress * Math.PI * 3 + Math.PI) + 1) / 2;
        const smoothWave = easeInOutCubic(wave);
        const thickness = baseThickness + smoothWave * (maxThickness - baseThickness);
        
        const colorIndex = (Math.floor(time * 0.8 + progress * colors.length + 2)) % colors.length;
        const nextColorIndex = (colorIndex + 1) % colors.length;
        const colorMix = (time * 0.8 + progress * colors.length + 2) % 1;
        
        const c1 = colors[colorIndex];
        const c2 = colors[nextColorIndex];
        const r = Math.floor(c1.r + (c2.r - c1.r) * colorMix);
        const g = Math.floor(c1.g + (c2.g - c1.g) * colorMix);
        const b = Math.floor(c1.b + (c2.b - c1.b) * colorMix);
        
        const gradient = siriCtx.createLinearGradient(x, h, x, h - thickness * 2);
        gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.9)`);
        gradient.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, 0.6)`);
        gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);
        
        siriCtx.fillStyle = gradient;
        siriCtx.globalCompositeOperation = 'lighter';
        siriCtx.fillRect(x - 0.5, h - thickness * 2, w / segments + 1.5, thickness * 2);
    }
    
    // Draw left edge
    for (let i = 0; i < segments; i++) {
        const y = (h / segments) * i;
        const progress = i / segments;
        const wave = (Math.sin(time * 1.5 + progress * Math.PI * 3 + Math.PI * 0.5) + 1) / 2;
        const smoothWave = smoothstep(wave);
        const thickness = baseThickness + smoothWave * (maxThickness - baseThickness);
        
        const colorIndex = (Math.floor(time * 0.8 + progress * colors.length + 1)) % colors.length;
        const nextColorIndex = (colorIndex + 1) % colors.length;
        const colorMix = (time * 0.8 + progress * colors.length + 1) % 1;
        
        const c1 = colors[colorIndex];
        const c2 = colors[nextColorIndex];
        const r = Math.floor(c1.r + (c2.r - c1.r) * colorMix);
        const g = Math.floor(c1.g + (c2.g - c1.g) * colorMix);
        const b = Math.floor(c1.b + (c2.b - c1.b) * colorMix);
        
        const gradient = siriCtx.createLinearGradient(0, y, thickness * 2, y);
        gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.9)`);
        gradient.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, 0.6)`);
        gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);
        
        siriCtx.fillStyle = gradient;
        siriCtx.globalCompositeOperation = 'lighter';
        siriCtx.fillRect(0, y - 0.5, thickness * 2, h / segments + 1.5);
    }
    
    // Draw right edge
    for (let i = 0; i < segments; i++) {
        const y = (h / segments) * i;
        const progress = i / segments;
        const wave = (Math.sin(time * 1.5 + progress * Math.PI * 3 + Math.PI * 1.5) + 1) / 2;
        const smoothWave = easeInOutCubic(wave);
        const thickness = baseThickness + smoothWave * (maxThickness - baseThickness);
        
        const colorIndex = (Math.floor(time * 0.8 + progress * colors.length + 3)) % colors.length;
        const nextColorIndex = (colorIndex + 1) % colors.length;
        const colorMix = (time * 0.8 + progress * colors.length + 3) % 1;
        
        const c1 = colors[colorIndex];
        const c2 = colors[nextColorIndex];
        const r = Math.floor(c1.r + (c2.r - c1.r) * colorMix);
        const g = Math.floor(c1.g + (c2.g - c1.g) * colorMix);
        const b = Math.floor(c1.b + (c2.b - c1.b) * colorMix);
        
        const gradient = siriCtx.createLinearGradient(w, y, w - thickness * 2, y);
        gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.9)`);
        gradient.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, 0.6)`);
        gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);
        
        siriCtx.fillStyle = gradient;
        siriCtx.globalCompositeOperation = 'lighter';
        siriCtx.fillRect(w - thickness * 2, y - 0.5, thickness * 2, h / segments + 1.5);
    }
    
    siriAnimationFrame = requestAnimationFrame(animateSiriEdge);
}

// Activation Sound (Ultra-modern Siri-style)
function playActivationSound() {
    if (!audioContext) return;
    
    try {
        const now = audioContext.currentTime;
        const duration = 0.2; // Slightly longer for smoother feel
        
        // Create three oscillators for richer harmony
        const osc1 = audioContext.createOscillator();
        const osc2 = audioContext.createOscillator();
        const osc3 = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        // Create a subtle filter for warmth
        const filter = audioContext.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(2000, now);
        filter.Q.setValueAtTime(1, now);
        
        // Modern gentle chord (C5, E5, G5 - C major triad)
        osc1.frequency.setValueAtTime(523.25, now); // C5
        osc2.frequency.setValueAtTime(659.25, now); // E5
        osc3.frequency.setValueAtTime(783.99, now); // G5
        
        // Ultra-smooth sine waves
        osc1.type = 'sine';
        osc2.type = 'sine';
        osc3.type = 'sine';
        
        // Very gentle volume envelope with smooth exponential curves
        gainNode.gain.setValueAtTime(0, now);
        gainNode.gain.linearRampToValueAtTime(0.08, now + 0.04); // Softer, gentle attack
        gainNode.gain.exponentialRampToValueAtTime(0.001, now + duration); // Ultra-smooth decay
        
        // Connect audio nodes with filter for warmth
        osc1.connect(gainNode);
        osc2.connect(gainNode);
        osc3.connect(gainNode);
        gainNode.connect(filter);
        filter.connect(audioContext.destination);
        
        // Play the sound
        osc1.start(now);
        osc2.start(now);
        osc3.start(now);
        osc1.stop(now + duration);
        osc2.stop(now + duration);
        osc3.stop(now + duration);
    } catch (error) {
        console.log('[OtoBot Warning]: Could not play activation sound:', error.message);
    }
}

function setVoiceState(state) {
    currentState = state;
    const body = document.body;
    if (!body) return;

    stateClassValues.forEach(cls => body.classList.remove(cls));
    const nextClass = stateClassMap[state];
    if (nextClass) {
        body.classList.add(nextClass);
    }
    
    // Control Siri edge animation based on state
    if (state === VoiceState.RECORDING || state === VoiceState.PROCESSING || state === VoiceState.PLAYING) {
        startSiriEdgeAnimation();
    } else {
        stopSiriEdgeAnimation();
    }
}

function updateStatus(text) {
    if (ui.status) {
        ui.status.textContent = text;
    }
    console.log(`[OtoBot Status]: ${text}`);
}

function showPermissionError(message) {
    if (ui.permissionError) {
        ui.permissionError.classList.remove('hidden');
        const paragraph = ui.permissionError.querySelector('p');
        if (paragraph) {
            paragraph.textContent = message;
        }
    }
}

function hidePermissionError() {
    if (ui.permissionError) {
        ui.permissionError.classList.add('hidden');
    }
}

function showUnsupportedNotice(message) {
    if (ui.unsupportedNotice) {
        ui.unsupportedNotice.classList.remove('hidden');
        const paragraph = ui.unsupportedNotice.querySelector('p');
        if (paragraph && message) {
            paragraph.textContent = message;
        }
    }
}

function hideUnsupportedNotice() {
    if (ui.unsupportedNotice) {
        ui.unsupportedNotice.classList.add('hidden');
    }
}

// --- Voice Synthesis via Backend Google TTS ---
// --- Cross-Platform Video Control (iOS/Android/Windows Compatible) ---
function initializeVideos() {
    return new Promise((resolve) => {
        const avatarStill = document.getElementById('avatar-still');
        const avatarMove = document.getElementById('avatar-move');
        
        if (avatarStill) {
            avatarStill.muted = true;
            avatarStill.playsInline = true;
            avatarStill.preload = 'metadata';
            
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
        
        videoInitialized = true;
        console.log('[OtoBot]: Videos initialized for cross-platform compatibility');
        resolve();
    });
}

function showMoveZloop() {
    const avatarStill = document.getElementById('avatar-still');
    const avatarMove = document.getElementById('avatar-move');
    
    if (!avatarStill || !avatarMove) return;
    
    try {
        avatarStill.pause();
        avatarStill.style.opacity = '0';
        
        avatarMove.loop = true;
        avatarMove.style.opacity = '1';
        avatarMove.currentTime = 0;
        
        const playPromise = avatarMove.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.log('[OtoBot Warning]: Avatar move video play blocked:', error.message);
                avatarStill.style.opacity = '1';
                avatarMove.style.opacity = '0';
            });
        }
    } catch (error) {
        console.log('[OtoBot Error]: Video control error:', error.message);
        if (avatarStill) avatarStill.style.opacity = '1';
    }
}

function endMoveZloop() {
    const avatarStill = document.getElementById('avatar-still');
    const avatarMove = document.getElementById('avatar-move');
    
    if (!avatarStill || !avatarMove) return;
    
    try {
        avatarMove.loop = false;
        avatarMove.pause();
        avatarMove.style.opacity = '0';
        
        avatarStill.currentTime = 0;
        avatarStill.style.opacity = '1';
        
        const playPromise = avatarStill.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.log('[OtoBot Warning]: Avatar still video play blocked:', error.message);
            });
        }
    } catch (error) {
        console.log('[OtoBot Error]: Video end control error:', error.message);
    }
}

// --- Cross-Platform Audio Context Management ---
function initializeAudioContext() {
    try {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        
        if (audioContext.state === 'suspended') {
            return audioContext.resume();
        }
        
        return Promise.resolve();
    } catch (error) {
        console.log('[OtoBot Warning]: AudioContext initialization failed:', error.message);
        return Promise.resolve();
    }
}

function speakWithGoogleTTS(text) {
    pauseHotwordRecognition();
    setVoiceState(VoiceState.PLAYING);
    updateStatus('🔊 Riproduzione risposta...');
    isPlaying = true;
    
    return initializeAudioContext().then(() => {
        return fetch('/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
    }).then(response => response.blob())
    .then(blob => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        
        if (isIOS || isMobile) {
            audio.preload = 'auto';
            audio.load();
        }
        
        return new Promise((resolve, reject) => {
            let safetyTimer = setTimeout(() => {
                endMoveZloop();
                console.log('[OtoBot]: Safety timer triggered - ending avatar animation');
            }, 120000);
            
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise.then(() => {
                    console.log('[OtoBot]: Audio playback started successfully');
                    
                    // Start avatar move immediately (no artificial 1s delay)
                    if (!videoInitialized) {
                        initializeVideos().then(() => showMoveZloop());
                    } else {
                        showMoveZloop();
                    }
                }).catch(error => {
                    console.log('[OtoBot Error]: Audio play blocked:', error.message);
                    clearTimeout(safetyTimer);
                    endMoveZloop();
                    isPlaying = false;
                    reject(error);
                });
            }
            
            audio.onended = function() {
                clearTimeout(safetyTimer);
                endMoveZloop();
                isPlaying = false;
                resolve();
            };
            
            audio.onerror = function(error) {
                clearTimeout(safetyTimer);
                endMoveZloop();
                isPlaying = false;
                reject(error);
            };
        });
    });
}

// --- Cross-Platform Audio Recording (Hotword + VAD) ---
function checkMediaRecorderSupport() {
    if (!window.MediaRecorder) {
        return { supported: false, reason: 'MediaRecorder not available' };
    }
    
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

async function requestMicrophoneAccess(isRetry = false) {
    try {
        updateStatus(isRetry ? '🔁 Nuovo tentativo accesso microfono...' : '🎙️ Richiesta accesso microfono...');
        setVoiceState(VoiceState.IDLE);
        
        const audioConstraints = {
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                sampleRate: isIOS ? 48000 : 44100,
                channelCount: 1
            }
        };
        
        const stream = await navigator.mediaDevices.getUserMedia(audioConstraints);
        micStream = stream;
        await initializeAudioContext();
        
        if (audioContext) {
            if (micSource) {
                try {
                    micSource.disconnect();
                } catch (_) {}
            }
            micSource = audioContext.createMediaStreamSource(stream);
        }
        
        hidePermissionError();
        updateStatus('✅ Microfono pronto');
        return true;
    } catch (error) {
        console.log('[OtoBot Error]: Microphone access failed:', error);
        
        let message = 'Errore microfono sconosciuto.';
        if (error.name === 'NotAllowedError') {
            message = 'Permesso microfono negato - abilita dalle impostazioni del browser.';
        } else if (error.name === 'NotFoundError') {
            message = 'Microfono non trovato.';
        } else if (error.name === 'NotSupportedError') {
            message = 'Registrazione non supportata su questo dispositivo.';
        } else if (error.message) {
            message = error.message;
        }
        
        showPermissionError(message);
        setVoiceState(VoiceState.IDLE);
        return false;
    }
}

function normalizeTranscript(text) {
    return text.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function startHotwordRecognition() {
    if (!speechRecognitionSupported || hotwordUnavailable) {
        return;
    }
    
    if (recognition) {
        try {
            recognitionAutoRestart = false;
            recognition.stop();
        } catch (_) {}
    }
    
    recognition = new SpeechRecognitionCtor();
    recognition.lang = 'it-IT';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognitionAutoRestart = true;
    
    recognition.onresult = handleHotwordResult;
    recognition.onerror = event => {
        console.log('[OtoBot Warning]: SpeechRecognition error:', event.error);
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
            disableHotwordFlow('Il browser ha bloccato il riconoscimento vocale.');
            return;
        }
        if (!hotwordUnavailable) {
            setTimeout(() => {
                try {
                    recognition.start();
                } catch (error) {
                    console.log('[OtoBot Warning]: SpeechRecognition restart failed:', error.message);
                }
            }, 500);
        }
    };
    
    recognition.onend = () => {
        if (recognitionAutoRestart && !hotwordUnavailable && !document.hidden) {
            try {
                recognition.start();
            } catch (error) {
                console.log('[OtoBot Warning]: SpeechRecognition restart error:', error.message);
            }
        }
    };
    
    try {
        hotwordUnavailable = false;
        hideUnsupportedNotice();
        recognition.start();
        console.log('[OtoBot]: Hotword recognition started');
    } catch (error) {
        console.log('[OtoBot Warning]: SpeechRecognition start failed:', error.message);
        disableHotwordFlow('Riconoscimento vocale non disponibile.');
    }
}

function handleHotwordResult(event) {
    if (hotwordUnavailable || isRecording || isProcessing || isPlaying) return;
    
    for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = normalizeTranscript(result[0].transcript || '');
        
        if (!transcript) continue;
        if (!transcript.includes(HOTWORD_MATCH)) continue;
        
        const now = Date.now();
        if (now - lastHotwordAt < HOTWORD_DEBOUNCE_MS) {
            continue;
        }
        
        lastHotwordAt = now;
        console.log('[OtoBot]: Hotword detected');
        playActivationSound();
        startActiveRecording('hotword');
        break;
    }
}

function pauseHotwordRecognition() {
    if (recognition) {
        recognitionAutoRestart = false;
        try {
            recognition.stop();
        } catch (error) {
            console.log('[OtoBot Warning]: SpeechRecognition stop failed:', error.message);
        }
    }
}

function resumeHotwordRecognition() {
    if (!speechRecognitionSupported || hotwordUnavailable) return;
    if (!recognition) {
        startHotwordRecognition();
        return;
    }
    recognitionAutoRestart = true;
    try {
        recognition.start();
    } catch (error) {
        console.log('[OtoBot Warning]: SpeechRecognition resume failed:', error.message);
    }
}

function startActiveRecording(triggerSource = 'hotword') {
    if (isRecording || !micStream) return;
    
    pauseHotwordRecognition();
    setVoiceState(VoiceState.RECORDING);
    updateStatus(triggerSource === 'hotword' ? '🎤 Hotword rilevata: sto registrando...' : '🎤 Registrazione in corso...');
    isRecording = true;
    audioChunks = [];
    recordingStartAt = 0;
    lastSpeechAt = 0;
    selectedRecordingFormat = mediaSupport?.format || 'audio/webm;codecs=opus';
    
    try {
        mediaRecorder = new MediaRecorder(micStream, { mimeType: selectedRecordingFormat });
    } catch (error) {
        console.log('[OtoBot Error]: Failed to create MediaRecorder:', error);
        updateStatus('❌ Impossibile avviare la registrazione.');
        isRecording = false;
        enterPassiveListening();
        return;
    }
    
    mediaRecorder.ondataavailable = event => {
        if (event.data && event.data.size > 0) {
            audioChunks.push(event.data);
        }
    };
    
    mediaRecorder.onstop = handleRecordingStop;
    
    try {
        mediaRecorder.start();
        startVADMonitor();
    } catch (error) {
        console.log('[OtoBot Error]: Failed to start MediaRecorder:', error);
        updateStatus('❌ Errore avvio registrazione.');
        isRecording = false;
        enterPassiveListening();
    }
}

function startVADMonitor() {
    if (!audioContext || !micSource) return;
    
    if (vadProcessor) {
        try {
            micSource.disconnect(vadProcessor);
            vadProcessor.disconnect();
        } catch (_) {}
    }
    
    vadProcessor = audioContext.createScriptProcessor(2048, 1, 1);
    recordingStartAt = performance.now();
    lastSpeechAt = recordingStartAt;
    
    vadProcessor.onaudioprocess = handleVADProcess;
    micSource.connect(vadProcessor);
    vadProcessor.connect(audioContext.destination);
}

function handleVADProcess(event) {
    if (!isRecording) return;
    
    const channelData = event.inputBuffer.getChannelData(0);
    let sum = 0;
    for (let i = 0; i < channelData.length; i++) {
        sum += channelData[i] * channelData[i];
    }
    const rms = Math.sqrt(sum / channelData.length);
    const now = performance.now();
    
    if (rms > VAD_CONFIG.silenceThreshold) {
        lastSpeechAt = now;
    }
    
    const elapsed = now - recordingStartAt;
    const silenceElapsed = now - lastSpeechAt;
    
    if (elapsed >= VAD_CONFIG.minSpeechMs && silenceElapsed >= VAD_CONFIG.silenceHoldMs) {
        stopActiveRecording();
    }
}

function stopActiveRecording() {
    if (!isRecording) return;
    isRecording = false;
    
    try {
        if (vadProcessor) {
            micSource.disconnect(vadProcessor);
            vadProcessor.disconnect();
            vadProcessor.onaudioprocess = null;
            vadProcessor = null;
        }
    } catch (error) {
        console.log('[OtoBot Warning]: VAD cleanup failed:', error.message);
    }
    
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        try {
            mediaRecorder.stop();
        } catch (error) {
            console.log('[OtoBot Warning]: MediaRecorder stop failed:', error.message);
        }
    }
}

function handleRecordingStop() {
    const blobType = (mediaRecorder && mediaRecorder.mimeType) || selectedRecordingFormat || 'audio/webm';
    const fileName = blobType.includes('mp4') ? 'input.mp4' : blobType.includes('wav') ? 'input.wav' : 'input.webm';
    const audioBlob = new Blob(audioChunks, { type: blobType });
    
    if (!audioBlob || audioBlob.size === 0) {
        updateStatus('❌ Nessun audio registrato.');
        enterPassiveListening();
        return;
    }
    
    isProcessing = true;
    setVoiceState(VoiceState.PROCESSING);
    updateStatus('⏳ Trascrizione in corso...');
    
    sendAudioForTranscription(audioBlob, fileName)
        .then(() => enterPassiveListening('✅ Pronto per nuova conversazione.'))
        .catch(error => {
            console.log('[OtoBot Error]: Audio processing failed:', error);
            updateStatus('❌ Errore durante l\'elaborazione della risposta.');
            enterPassiveListening();
        })
        .finally(() => {
            isProcessing = false;
        });
}

function sendAudioForTranscription(audioBlob, fileName) {
    const formData = new FormData();
    formData.append('audio', audioBlob, fileName);
    
    return fetch('/transcribe', {
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
        if (data.transcript && data.transcript.trim().length > 0) {
            return handleTranscript(data.transcript.trim());
        }
        throw new Error('Transcript vuoto');
    })
    .catch(error => {
        console.log('[OtoBot Error]: Transcription failed:', error);
        updateStatus('❌ Errore trascrizione - controlla la connessione.');
        throw error;
    });
}

function handleTranscript(transcript) {
    updateStatus('🗣️ Elaborazione della richiesta...');
    
    return fetch('/voice_activation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: transcript })
    })
    .then(response => response.json())
    .then(activationData => {
        if (activationData.activated && activationData.reply) {
            updateStatus('✅ OtoBot attivato! Riproduzione risposta...');
            return speakWithGoogleTTS(activationData.reply);
        }
        return sendChatRequest(transcript);
    })
    .catch(error => {
        console.log('[OtoBot Warning]: Voice activation check failed, falling back to chat:', error);
        return sendChatRequest(transcript);
    });
}

function sendChatRequest(message) {
    return fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message,
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
            updateStatus('✅ Riproduzione risposta...');
            return speakWithGoogleTTS(chatData.reply);
        }
        updateStatus('❌ Nessuna risposta trovata.');
        return Promise.resolve();
    })
    .catch(error => {
        console.log('[OtoBot Error]: Chat processing failed:', error);
        updateStatus('❌ Errore elaborazione risposta.');
        throw error;
    });
}

function enterPassiveListening(message) {
    if (hotwordUnavailable) {
        setVoiceState(VoiceState.IDLE);
        updateStatus(message || '❌ Funzione hotword non disponibile su questo browser.');
        return;
    }
    
    setVoiceState(VoiceState.LISTENING);
    resumeHotwordRecognition();
    updateStatus(message || `🎧 In ascolto: pronuncia “${HOTWORD}”.`);
}

function disableHotwordFlow(reason) {
    if (hotwordUnavailable) return;
    
    hotwordUnavailable = true;
    pauseHotwordRecognition();
    showUnsupportedNotice(reason || 'Funzione hotword non disponibile su questo browser.');
    updateStatus(reason || '❌ Funzione hotword non disponibile.');
    setVoiceState(VoiceState.IDLE);
}

function handleVisibilityChange() {
    if (document.hidden) {
        pauseHotwordRecognition();
    } else if (!isRecording && !isProcessing && !isPlaying) {
        enterPassiveListening();
    }
}

async function initializeHandsFreeFlow() {
    setVoiceState(VoiceState.IDLE);
    updateStatus('🚀 Inizializzazione assistente vocale...');
    
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        updateStatus('❌ Microfono non supportato dal browser.');
        showPermissionError('Il tuo browser non consente l\'uso del microfono.');
        disableHotwordFlow('Microfono non disponibile.');
        return;
    }
    
    if (!(location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
        updateStatus('❌ È richiesto HTTPS per le funzioni vocali.');
        showPermissionError('Apri la pagina tramite HTTPS per proseguire.');
        return;
    }
    
    mediaSupport = checkMediaRecorderSupport();
    if (!mediaSupport.supported) {
        updateStatus('❌ Registrazione audio non supportata.');
        showPermissionError('Questo browser non supporta i formati audio richiesti.');
        return;
    }
    
    if (ui.retryPermissionBtn) {
        ui.retryPermissionBtn.addEventListener('click', () => {
            requestMicrophoneAccess(true).then(success => {
                if (success && !hotwordUnavailable) {
                    enterPassiveListening();
                }
            });
        });
    }
    
    if (!videoInitialized) {
        initializeVideos().catch(error => {
            console.log('[OtoBot Warning]: Video initialization failed:', error.message);
        });
    }
    
    const micReady = await requestMicrophoneAccess();
    if (!micReady) {
        return;
    }
    
    isInitialized = true;
    
    if (speechRecognitionSupported) {
        hideUnsupportedNotice();
        startHotwordRecognition();
    } else {
        disableHotwordFlow('Il tuo browser non supporta l\'hotword automatica.');
    }
    
    enterPassiveListening();
    document.addEventListener('visibilitychange', handleVisibilityChange);
}

// --- Professional Cross-Platform Initialization ---
document.addEventListener('DOMContentLoaded', function() {
    console.log('[OtoBot]: Application starting - Hands-free mode');
    console.log(`[OtoBot]: Device detected - iOS: ${isIOS}, Android: ${isAndroid}, Mobile: ${isMobile}`);
    initSiriEdgeAnimation();
    initializeHandsFreeFlow();
});
