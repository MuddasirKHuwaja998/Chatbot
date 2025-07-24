// Voice Recognition Variables
let recognition = null;
let isListening = false;
let lastActivationTime = 0;
const ACTIVATION_COOLDOWN = 3000; // 3 seconds cooldown between activations

// Microphone button elements
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const audioReply = document.getElementById('audioReply');

// Voice Settings for Professional Italian Male Voice
function getBestItalianMaleVoice() {
  const voices = window.speechSynthesis.getVoices();
  
  // Priority order for best Italian male voices
  const preferredMaleVoices = [
    'Microsoft Cosimo - Italian (Italy)',
    'Cosimo',
    'Microsoft Riccardo - Italian (Italy)', 
    'Riccardo',
    'Paolo',
    'Marco',
    'Andrea',
    'Luca',
    'Google Italiano'
  ];

  // First try to find exact matches for male voices
  for (const voiceName of preferredMaleVoices) {
    const voice = voices.find(v => 
      v.name.toLowerCase().includes(voiceName.toLowerCase()) && 
      v.lang.includes('it')
    );
    if (voice) return voice;
  }

  // Fallback: find any Italian voice with male characteristics
  const italianVoice = voices.find(v => 
    v.lang.includes('it-IT') && 
    (v.name.toLowerCase().includes('cosimo') || 
     v.name.toLowerCase().includes('riccardo') ||
     v.name.toLowerCase().includes('paolo') ||
     v.name.toLowerCase().includes('marco') ||
     v.name.toLowerCase().includes('luca'))
  );
  
  if (italianVoice) return italianVoice;

  // Last resort: any Italian voice
  return voices.find(v => v.lang.includes('it-IT')) || voices.find(v => v.lang.includes('it'));
}

// Enhanced Voice Detection with Precise "OtoBot" Matching
function initializeVoiceRecognition() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    console.warn('Speech recognition not supported');
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'it-IT';
  recognition.maxAlternatives = 3;

  recognition.onresult = function(event) {
    const currentTime = Date.now();
    if (currentTime - lastActivationTime < ACTIVATION_COOLDOWN) {
      return; // Prevent rapid fire activations
    }

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript.toLowerCase().trim();
      
      if (event.results[i].isFinal) {
        console.log('Final transcript:', transcript);
        
        // Very precise "OtoBot" detection
        if (isExactOtoBotActivation(transcript)) {
          lastActivationTime = currentTime;
          activateOtoBot();
          break;
        }
      } else {
        // Even for interim results, check for activation
        if (isExactOtoBotActivation(transcript)) {
          lastActivationTime = currentTime;
          activateOtoBot();
          break;
        }
      }
    }
  };

  recognition.onerror = function(event) {
    console.error('Speech recognition error:', event.error);
    if (event.error === 'no-speech' || event.error === 'audio-capture') {
      // Restart recognition after a brief delay
      setTimeout(() => {
        if (!isListening) startVoiceRecognition();
      }, 1000);
    }
  };

  recognition.onend = function() {
    console.log('Speech recognition ended');
    isListening = false;
    // Auto-restart recognition
    setTimeout(() => {
      if (!isListening) startVoiceRecognition();
    }, 500);
  };
}

// Extremely precise OtoBot activation detection
function isExactOtoBotActivation(transcript) {
  const normalized = normalizeForActivation(transcript);
  
  // Exact word matching patterns
  const exactPatterns = [
    'otobot',
    'oto bot',
    'otto bot',
    'ottobot'
  ];

  // Check for exact matches
  for (const pattern of exactPatterns) {
    // Complete word match
    if (normalized === pattern) return true;
    
    // Word boundary match (start/end of sentence)
    const regex = new RegExp(`\\b${pattern}\\b`);
    if (regex.test(normalized)) return true;
  }

  // Additional safety check: must not be part of longer words
  const words = normalized.split(/\s+/);
  for (const word of words) {
    if (exactPatterns.includes(word)) {
      return true;
    }
  }

  return false;
}

// Text normalization for activation detection
function normalizeForActivation(text) {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s]/g, '') // Remove punctuation
    .replace(/\s+/g, ' ') // Normalize whitespace
    .replace(/otto/g, 'oto') // Handle common mispronunciation
    .replace(/òto/g, 'oto')
    .replace(/óto/g, 'oto');
}

// Start voice recognition
function startVoiceRecognition() {
  if (!recognition || isListening) return;
  
  try {
    isListening = true;
    recognition.start();
    console.log('Voice recognition started - listening for "OtoBot"');
    status.textContent = "Dì 'OtoBot' per attivare l'assistente o premi il microfono";
  } catch (error) {
    console.error('Error starting voice recognition:', error);
    isListening = false;
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

// Activate OtoBot with professional greeting
async function activateOtoBot() {
  console.log('OtoBot activated!');
  
  // Stop listening temporarily to avoid feedback
  stopVoiceRecognition();
  
  // Visual feedback
  micBtn.classList.add('listening');
  status.textContent = "OtoBot attivato! Elaborazione in corso...";
  
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
      speakWithMaleVoice(data.reply);
    } else {
      console.error('Error communicating with backend');
      speakWithMaleVoice('Buongiorno, sono OtoBot, il suo assistente virtuale di Otofarma Spa. Sono qui per aiutarla in tutto ciò che riguarda i nostri servizi e prodotti. Come posso esserle utile oggi?');
    }
  } catch (error) {
    console.error('Network error:', error);
    speakWithMaleVoice('Buongiorno, sono OtoBot, il suo assistente virtuale di Otofarma Spa. Sono qui per aiutarla in tutto ciò che riguarda i nostri servizi e prodotti. Come posso esserle utile oggi?');
  }
  
  // Remove visual feedback
  micBtn.classList.remove('listening');
  
  // Restart listening after a delay
  setTimeout(() => {
    startVoiceRecognition();
  }, 3000);
}

// Enhanced professional Italian male voice - matching app.py style
function speakWithMaleVoice(text) {
  if (!window.speechSynthesis || !text) return;
  
  // Cancel any ongoing speech
  window.speechSynthesis.cancel();
  
  // Wait for voices to load if needed
  if (window.speechSynthesis.getVoices().length === 0) {
    window.speechSynthesis.addEventListener('voiceschanged', () => {
      speakWithMaleVoice(text);
    }, { once: true });
    return;
  }

  const utterance = new SpeechSynthesisUtterance(text);
  const selectedVoice = getBestItalianMaleVoice();
  
  if (selectedVoice) {
    utterance.voice = selectedVoice;
    console.log('Using professional voice:', selectedVoice.name);
  }
  
  // Professional announcement voice settings - matching app.py preferences
  utterance.lang = 'it-IT';
  utterance.pitch = 0.85;  // Lower pitch for more authoritative, professional sound
  utterance.rate = 0.85;   // Slower, more deliberate announcement-style speech
  utterance.volume = 0.95; // Clear, strong volume

  status.textContent = "OtoBot sta parlando...";

  utterance.onstart = () => {
    console.log('Speaking with professional male announcement voice');
    animateMicrophone();
  };

  utterance.onend = () => {
    console.log('Speech ended');
    status.textContent = "Dì 'OtoBot' per attivare l'assistente o premi il microfono";
    stopMicrophoneAnimation();
  };

  utterance.onerror = (event) => {
    console.error('Speech error:', event.error);
    status.textContent = "Errore durante la riproduzione vocale";
    stopMicrophoneAnimation();
  };

  window.speechSynthesis.speak(utterance);
}

// Microphone animation during speech
function animateMicrophone() {
  micBtn.classList.add('listening');
  
  // Add pulsing animation
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

micBtn.addEventListener('mousedown', startRecording);
micBtn.addEventListener('touchstart', startRecording);
micBtn.addEventListener('mouseup', stopRecording);
micBtn.addEventListener('mouseleave', stopRecording);
micBtn.addEventListener('touchend', stopRecording);

async function startRecording(e) {
  if (recording) return;
  recording = true;
  micBtn.classList.add('listening');
  status.textContent = "Sto ascoltando...";

  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

    mediaRecorder.onstop = async () => {
      status.textContent = "Elaborazione...";
      
      // Start recognition for user input
      await processVoiceInput();
      
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
      micBtn.classList.remove('listening');
      recording = false;
    };

    mediaRecorder.start();
  } catch (error) {
    console.error('Error accessing microphone:', error);
    status.textContent = "Errore nell'accesso al microfono";
    recording = false;
    micBtn.classList.remove('listening');
  }
}

function stopRecording(e) {
  if (recording && mediaRecorder && mediaRecorder.state === "recording") {
    status.textContent = "Sto elaborando la tua voce...";
    mediaRecorder.stop();
  }
}

// Process voice input with speech recognition
async function processVoiceInput() {
  try {
    status.textContent = "Dimmi la tua domanda...";
    
    // Create a new recognition instance for user input
    const userRecognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    userRecognition.lang = 'it-IT';
    userRecognition.continuous = false;
    userRecognition.interimResults = false;

    userRecognition.onresult = async function(event) {
      const transcript = event.results[0][0].transcript;
      console.log('User said:', transcript);
      
      // Send to backend for processing
      await sendMessageToBackend(transcript);
    };

    userRecognition.onerror = function(event) {
      console.error('Recognition error:', event.error);
      status.textContent = "Errore nel riconoscimento vocale. Riprova.";
    };

    userRecognition.start();

  } catch (error) {
    console.error('Error processing voice input:', error);
    status.textContent = "Errore nell'elaborazione vocale";
  }
}

// Send message to backend and get response - matching app.py JSON structure
async function sendMessageToBackend(message) {
  try {
    status.textContent = "Elaborazione della risposta...";
    
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
      // Check if male_voice flag is set in response (from app.py)
      if (data.male_voice || data.voice) {
        speakWithMaleVoice(data.reply);
      } else {
        status.textContent = data.reply;
      }
    } else {
      status.textContent = "Errore nella comunicazione con il server";
    }
  } catch (error) {
    console.error('Error sending message:', error);
    status.textContent = "Errore di rete";
  }
}

// Initialize everything when page loads
document.addEventListener('DOMContentLoaded', function() {
  console.log('OtoBot Voice Assistant initializing...');
  
  // Wait for voices to load
  if (window.speechSynthesis) {
    if (window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.addEventListener('voiceschanged', () => {
        console.log('Voices loaded:', window.speechSynthesis.getVoices().length);
        initializeVoiceRecognition();
        setTimeout(startVoiceRecognition, 1000);
      }, { once: true });
    } else {
      initializeVoiceRecognition();
      setTimeout(startVoiceRecognition, 1000);
    }
  }
  
  status.textContent = "Dì 'OtoBot' per attivare l'assistente o premi il microfono";
  console.log('OtoBot Voice Assistant ready - say "OtoBot" to activate or press microphone');
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopVoiceRecognition();
  } else {
    setTimeout(() => {
      if (!isListening) startVoiceRecognition();
    }, 1000);
  }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  stopVoiceRecognition();
  window.speechSynthesis.cancel();
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
  }
});

// Test voice function for debugging
window.testOtoBotVoice = function() {
  speakWithMaleVoice('Salve, sono OtoBot, il suo assistente virtuale di Otofarma Spa. Test della voce maschile italiana professionale.');
};

// Global function for external calls (if needed)
window.otoBotSpeak = function(text) {
  speakWithMaleVoice(text);
};

console.log('OtoBot Voice Assistant loaded successfully - Avatar removed, Voice-only mode active');
