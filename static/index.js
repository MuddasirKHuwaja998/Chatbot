// Voice Recognition Variables
let recognition = null;
let isListening = false;
let lastActivationTime = 0;
const ACTIVATION_COOLDOWN = 3000; // 3 seconds cooldown between activations

// Current speech management
let currentUtterance = null;
let isCurrentlySpeaking = false;
let speechInterrupted = false;

// Microphone button elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const audioReply = document.getElementById('audioReply');

// Enhanced Professional Italian Voice Selection
function getBestProfessionalItalianVoice() {
  const voices = window.speechSynthesis.getVoices();
  
  // Priority for MODERN, CLEAR, PROFESSIONAL voices (avoid old/robotic ones)
  const professionalVoices = [
    // Modern Microsoft Neural voices (highest quality)
    'Microsoft Elsa - Italian (Italy)',
    'Microsoft Isabella - Italian (Italy)',
    'Microsoft Cosimo - Italian (Italy)',
    
    // Google voices (natural sounding)
    'Google italiano',
    'Google Italiano',
    
    // Modern system voices
    'Luca',
    'Paola',
    'Alice',
    
    // Fallback professional voices
    'it-IT-Standard-A',
    'it-IT-Standard-B',
    'it-IT-Wavenet-A',
    'it-IT-Wavenet-B'
  ];

  // Find the best professional voice
  for (const voiceName of professionalVoices) {
    const voice = voices.find(v => 
      v.name.toLowerCase().includes(voiceName.toLowerCase()) && 
      v.lang.includes('it') &&
      !v.name.toLowerCase().includes('compact') &&  // Avoid compact/compressed voices
      !v.name.toLowerCase().includes('enhanced') &&  // Sometimes these are older
      !v.name.toLowerCase().includes('premium')      // Premium doesn't always mean better
    );
    if (voice) {
      console.log('Selected professional voice:', voice.name);
      return voice;
    }
  }

  // Smart fallback: prefer female voices (often clearer for customer service)
  const femaleVoice = voices.find(v => 
    v.lang.includes('it-IT') && 
    (v.name.toLowerCase().includes('elsa') || 
     v.name.toLowerCase().includes('isabella') ||
     v.name.toLowerCase().includes('paola') ||
     v.name.toLowerCase().includes('alice'))
  );
  
  if (femaleVoice) {
    console.log('Using female professional voice:', femaleVoice.name);
    return femaleVoice;
  }

  // Last resort: any modern Italian voice
  const modernVoice = voices.find(v => 
    v.lang.includes('it-IT') && 
    !v.name.toLowerCase().includes('compact')
  );
  
  return modernVoice || voices.find(v => v.lang.includes('it'));
}

// Enhanced Voice Detection with Continuous Monitoring
function initializeVoiceRecognition() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    console.warn('Speech recognition not supported');
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  
  // Enhanced settings for better activation detection
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'it-IT';
  recognition.maxAlternatives = 5; // More alternatives for better accuracy

  recognition.onresult = function(event) {
    const currentTime = Date.now();
    
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript.toLowerCase().trim();
      
      // Check for interruption phrases while speaking
      if (isCurrentlySpeaking && detectInterruption(transcript)) {
        console.log('Speech interruption detected:', transcript);
        stopCurrentSpeech();
        return;
      }
      
      // Check for activation (with cooldown)
      if (currentTime - lastActivationTime > ACTIVATION_COOLDOWN) {
        if (isExactOtoBotActivation(transcript)) {
          console.log('Voice activation detected:', transcript);
          lastActivationTime = currentTime;
          activateOtoBot();
          break;
        }
      }
    }
  };

  recognition.onerror = function(event) {
    console.error('Speech recognition error:', event.error);
    
    // Handle specific errors gracefully
    if (event.error === 'no-speech') {
      // Normal - just continue listening
      setTimeout(restartRecognition, 1000);
    } else if (event.error === 'audio-capture') {
      console.log('Microphone access issue');
      setTimeout(restartRecognition, 2000);
    } else if (event.error === 'not-allowed') {
      console.log('Microphone permission denied');
      status.textContent = "Permetti l'accesso al microfono per l'attivazione vocale";
    } else {
      setTimeout(restartRecognition, 1500);
    }
  };

  recognition.onend = function() {
    console.log('Speech recognition ended - restarting...');
    isListening = false;
    setTimeout(restartRecognition, 500);
  };
}

// Restart recognition function
function restartRecognition() {
  if (!isListening && recognition) {
    startVoiceRecognition();
  }
}

// Enhanced interruption detection
function detectInterruption(transcript) {
  const interruptionPhrases = [
    'basta', 'stop', 'fermati', 'silenzio', 'zitto', 'smetti',
    'taci', 'finisci', 'interruzione', 'pausa', 'aspetta',
    'ferma', 'chiudi', 'spegni', 'cancella', 'annulla'
  ];
  
  return interruptionPhrases.some(phrase => transcript.includes(phrase));
}

// Stop current speech immediately
function stopCurrentSpeech() {
  speechInterrupted = true;
  isCurrentlySpeaking = false;
  
  // Cancel speech synthesis
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
  }
  
  // Reset current utterance
  currentUtterance = null;
  
  // Update UI
  status.textContent = "Discorso interrotto. Dì 'OtoBot' per riattivare.";
  stopMicrophoneAnimation();
  
  console.log('Speech interrupted by user command');
}

// Extremely precise OtoBot activation detection
function isExactOtoBotActivation(transcript) {
  const normalized = normalizeForActivation(transcript);
  
  // Exact activation phrases
  const activationPhrases = [
    'otobot',
    'oto bot',
    'otto bot',
    'ottobot',
    'hey otobot',
    'ciao otobot',
    'salve otobot',
    'assistente virtuale',
    'assistente otofarma'
  ];

  // Check for exact matches at word boundaries
  for (const phrase of activationPhrases) {
    // Complete match
    if (normalized === phrase) return true;
    
    // Word boundary match
    const regex = new RegExp(`\\b${phrase.replace(/\s+/g, '\\s+')}\\b`);
    if (regex.test(normalized)) return true;
    
    // Start or end of sentence
    if (normalized.startsWith(phrase + ' ') || normalized.endsWith(' ' + phrase)) {
      return true;
    }
  }

  return false;
}

// Enhanced text normalization
function normalizeForActivation(text) {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s]/g, ' ') // Replace punctuation with spaces
    .replace(/\s+/g, ' ') // Normalize whitespace
    .replace(/otto/g, 'oto') // Handle mispronunciation
    .replace(/òto/g, 'oto')
    .replace(/óto/g, 'oto')
    .trim();
}

// Start voice recognition with error handling
function startVoiceRecognition() {
  if (!recognition || isListening) return;
  
  try {
    isListening = true;
    recognition.start();
    console.log('Voice recognition started - listening for "OtoBot"');
    if (!isCurrentlySpeaking) {
      status.textContent = "Dì 'OtoBot' per attivare l'assistente o premi il microfono";
    }
  } catch (error) {
    console.error('Error starting voice recognition:', error);
    isListening = false;
    setTimeout(restartRecognition, 2000);
  }
}

// Stop voice recognition
function stopVoiceRecognition() {
  if (recognition && isListening) {
    recognition.stop();
    isListening = false;
    console.log('Voice recognition stopped');
  }
}

// Activate OtoBot with professional response
async function activateOtoBot() {
  console.log('OtoBot activated by voice!');
  
  // Stop listening temporarily to avoid feedback
  stopVoiceRecognition();
  
  // Visual feedback
  micBtn.classList.add('listening');
  status.textContent = "OtoBot attivato! Elaborazione...";
  
  try {
    // Send activation request to backend
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: 'otobot',
        voice: true
      })
    });

    if (response.ok) {
      const data = await response.json();
      speakWithProfessionalVoice(data.reply);
    } else {
      console.error('Backend communication error');
      speakWithProfessionalVoice('Buongiorno, sono OtoBot, il vostro assistente virtuale professionale di Otofarma. Come posso aiutarvi oggi?');
    }
  } catch (error) {
    console.error('Network error:', error);
    speakWithProfessionalVoice('Buongiorno, sono OtoBot, il vostro assistente virtuale di Otofarma. Come posso aiutarvi?');
  }
  
  // Remove visual feedback
  micBtn.classList.remove('listening');
  
  // Restart listening after speech ends
  setTimeout(() => {
    if (!isCurrentlySpeaking) {
      startVoiceRecognition();
    }
  }, 2000);
}

// Professional speech synthesis with interruption handling
function speakWithProfessionalVoice(text) {
  if (!window.speechSynthesis || !text) return;
  
  // Stop any current speech first
  stopCurrentSpeech();
  
  // Reset interruption flag
  speechInterrupted = false;
  isCurrentlySpeaking = true;
  
  // Wait for voices to load if needed
  if (window.speechSynthesis.getVoices().length === 0) {
    window.speechSynthesis.addEventListener('voiceschanged', () => {
      speakWithProfessionalVoice(text);
    }, { once: true });
    return;
  }

  const utterance = new SpeechSynthesisUtterance(text);
  currentUtterance = utterance;
  
  const professionalVoice = getBestProfessionalItalianVoice();
  if (professionalVoice) {
    utterance.voice = professionalVoice;
    console.log('Using professional voice:', professionalVoice.name);
  }
  
  // PROFESSIONAL SETTINGS for clear, natural speech
  utterance.lang = 'it-IT';
  utterance.pitch = 1.0;   // Natural pitch (not too low)
  utterance.rate = 0.9;    // Slightly slower for clarity
  utterance.volume = 0.85; // Clear but not overwhelming
  
  status.textContent = "OtoBot sta parlando... (dì 'basta' per interrompere)";

  utterance.onstart = () => {
    if (speechInterrupted) return;
    console.log('Professional speech started');
    animateMicrophone();
  };

  utterance.onend = () => {
    isCurrentlySpeaking = false;
    currentUtterance = null;
    
    if (!speechInterrupted) {
      status.textContent = "Dì 'OtoBot' per attivare l'assistente o premi il microfono";
      stopMicrophoneAnimation();
      
      // Restart voice recognition
      setTimeout(() => {
        startVoiceRecognition();
      }, 1000);
    }
    
    console.log('Professional speech ended');
  };

  utterance.onerror = (event) => {
    console.error('Speech synthesis error:', event.error);
    isCurrentlySpeaking = false;
    currentUtterance = null;
    status.textContent = "Errore nella sintesi vocale";
    stopMicrophoneAnimation();
    
    // Restart recognition
    setTimeout(() => {
      startVoiceRecognition();
    }, 1000);
  };

  // Small delay to ensure proper initialization
  setTimeout(() => {
    if (!speechInterrupted) {
      window.speechSynthesis.speak(utterance);
    }
  }, 100);
}

// Microphone animation during speech
function animateMicrophone() {
  micBtn.classList.add('listening');
  micBtn.style.animation = 'pulse 1.5s infinite';
}

function stopMicrophoneAnimation() {
  micBtn.classList.remove('listening');
  micBtn.style.animation = '';
}

// Microphone button functionality
let mediaRecorder, audioChunks = [];
let recording = false;
let stream = null;

// Enhanced button event listeners
micBtn.addEventListener('mousedown', handleMicStart);
micBtn.addEventListener('touchstart', handleMicStart);
micBtn.addEventListener('mouseup', handleMicStop);
micBtn.addEventListener('mouseleave', handleMicStop);
micBtn.addEventListener('touchend', handleMicStop);

function handleMicStart(e) {
  e.preventDefault();
  if (!recording && !isCurrentlySpeaking) {
    startRecording();
  }
}

function handleMicStop(e) {
  e.preventDefault();
  if (recording) {
    stopRecording();
  }
}

async function startRecording() {
  if (recording || isCurrentlySpeaking) return;
  
  // Stop voice activation listening while recording
  stopVoiceRecognition();
  
  recording = true;
  micBtn.classList.add('listening');
  status.textContent = "Sto ascoltando la tua domanda...";

  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

    mediaRecorder.onstop = async () => {
      status.textContent = "Elaborazione della domanda...";
      await processVoiceInput();
      cleanup();
    };

    mediaRecorder.start();
  } catch (error) {
    console.error('Microphone access error:', error);
    status.textContent = "Errore accesso microfono. Controlla i permessi.";
    cleanup();
  }
}

function stopRecording() {
  if (recording && mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
}

function cleanup() {
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
    stream = null;
  }
  micBtn.classList.remove('listening');
  recording = false;
  
  // Restart voice activation after a delay
  setTimeout(() => {
    if (!isCurrentlySpeaking) {
      startVoiceRecognition();
    }
  }, 1000);
}

// Process voice input with enhanced recognition
async function processVoiceInput() {
  try {
    const userRecognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    userRecognition.lang = 'it-IT';
    userRecognition.continuous = false;
    userRecognition.interimResults = false;
    userRecognition.maxAlternatives = 3;

    userRecognition.onresult = async function(event) {
      const transcript = event.results[0][0].transcript;
      console.log('User question:', transcript);
      
      // Send to backend
      await sendMessageToBackend(transcript);
    };

    userRecognition.onerror = function(event) {
      console.error('User input recognition error:', event.error);
      status.textContent = "Non ho capito. Riprova premendo il microfono.";
      setTimeout(() => {
        startVoiceRecognition();
      }, 2000);
    };

    userRecognition.start();

  } catch (error) {
    console.error('Voice input processing error:', error);
    status.textContent = "Errore elaborazione vocale. Riprova.";
    setTimeout(() => {
      startVoiceRecognition();
    }, 2000);
  }
}

// Send message to backend
async function sendMessageToBackend(message) {
  try {
    status.textContent = "Sto preparando la risposta...";
    
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: message,
        voice: true
      })
    });

    if (response.ok) {
      const data = await response.json();
      speakWithProfessionalVoice(data.reply);
    } else {
      status.textContent = "Errore comunicazione server. Riprova.";
      setTimeout(() => {
        startVoiceRecognition();
      }, 2000);
    }
  } catch (error) {
    console.error('Backend communication error:', error);
    status.textContent = "Errore di rete. Riprova.";
    setTimeout(() => {
      startVoiceRecognition();
    }, 2000);
  }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
  console.log('Professional OtoBot Voice Assistant initializing...');
  
  // Initialize speech synthesis
  if (window.speechSynthesis) {
    // Load voices
    if (window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.addEventListener('voiceschanged', () => {
        console.log('Professional voices loaded:', window.speechSynthesis.getVoices().length);
        initializeVoiceRecognition();
        setTimeout(startVoiceRecognition, 1000);
      }, { once: true });
    } else {
      initializeVoiceRecognition();
      setTimeout(startVoiceRecognition, 1000);
    }
  }
  
  status.textContent = "Dì 'OtoBot' per attivare l'assistente o premi il microfono";
  console.log('Professional OtoBot ready - Voice activation active');
});

// Handle page visibility for better performance
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    // Page hidden - pause voice recognition
    if (!isCurrentlySpeaking) {
      stopVoiceRecognition();
    }
  } else {
    // Page visible - resume voice recognition
    setTimeout(() => {
      if (!isListening && !isCurrentlySpeaking) {
        startVoiceRecognition();
      }
    }, 1000);
  }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  stopVoiceRecognition();
  stopCurrentSpeech();
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
  }
});

// Global functions for external access
window.testProfessionalVoice = function() {
  speakWithProfessionalVoice('Salve, sono OtoBot, il vostro assistente professionale di Otofarma. Test della voce professionale italiana.');
};

window.stopOtoBotSpeech = function() {
  stopCurrentSpeech();
};

window.otoBotSpeak = function(text) {
  speakWithProfessionalVoice(text);
};

console.log('Professional OtoBot Voice Assistant loaded - Enhanced voice quality and interruption handling active');
