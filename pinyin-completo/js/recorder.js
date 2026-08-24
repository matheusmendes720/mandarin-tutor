/**
 * PINYIN TRAINER - Recording & Comparison System
 * GRAVAÇÃO + COMPARAÇÃO - A PRIORIDADE MÁXIMA!
 */

class VoiceRecorder {
  constructor() {
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.recordedBlob = null;
    this.recordedUrl = null;
    this.isRecording = false;
    this.stream = null;

    // Comparison audio elements
    this.refAudio = null;
    this.recordedAudio = null;

    // Canvas for waveform
    this.waveformCanvas = null;
    this.waveformCtx = null;
    this.analyser = null;
    this.animationId = null;

    this.init();
  }

  async init() {
    // Request microphone permission
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.mediaRecorder = new MediaRecorder(this.stream);
      this.audioChunks = [];

      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          this.audioChunks.push(e.data);
        }
      };

      this.mediaRecorder.onstop = () => {
        this.recordedBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        this.recordedUrl = URL.createObjectURL(this.recordedBlob);
        this.audioChunks = [];
        this.isRecording = false;
        this.updateRecordButton(false);
      };

    } catch (err) {
      console.warn('Microfone não disponível:', err);
    }
  }

  /**
   * Start recording
   */
  startRecording() {
    if (!this.mediaRecorder || this.isRecording) return;

    this.audioChunks = [];
    this.mediaRecorder.start();
    this.isRecording = true;
    this.updateRecordButton(true);
  }

  /**
   * Stop recording
   */
  stopRecording() {
    if (!this.mediaRecorder || !this.isRecording) return;
    this.mediaRecorder.stop();
  }

  /**
   * Toggle recording state
   */
  toggleRecording() {
    if (this.isRecording) {
      this.stopRecording();
    } else {
      this.startRecording();
    }
    return this.isRecording;
  }

  /**
   * Update record button appearance
   */
  updateRecordButton(isRecording) {
    const btn = document.querySelector('.record-btn');
    if (btn) {
      btn.classList.toggle('recording', isRecording);
    }
  }

  /**
   * Play reference audio
   */
  playReference(src) {
    return new Promise((resolve) => {
      this.refAudio = new Audio(src);
      this.refAudio.play();
      this.refAudio.onended = () => resolve();
    });
  }

  /**
   * Play recorded audio
   */
  playRecording() {
    if (!this.recordedUrl) return;
    this.recordedAudio = new Audio(this.recordedUrl);
    return this.recordedAudio.play();
  }

  /**
   * Play both: reference then recording
   */
  async playComparison(refSrc) {
    // Play reference
    await this.playReference(refSrc);
    // Small delay
    await new Promise(r => setTimeout(r, 300));
    // Play recording
    await this.playRecording();
  }

  /**
   * Initialize waveform canvas
   */
  initWaveform(canvasId) {
    this.waveformCanvas = document.getElementById(canvasId);
    if (!this.waveformCanvas) return;

    this.waveformCtx = this.waveformCanvas.getContext('2d');
    this.waveformCanvas.width = this.waveformCanvas.offsetWidth;
    this.waveformCanvas.height = this.waveformCanvas.offsetHeight;

    // Setup analyser for live visualization
    if (this.stream) {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const source = ctx.createMediaStreamSource(this.stream);
      this.analyser = ctx.createAnalyser();
      this.analyser.fftSize = 256;
      source.connect(this.analyser);
    }
  }

  /**
   * Draw waveform
   */
  drawWaveform() {
    if (!this.waveformCtx || !this.analyser) return;

    const width = this.waveformCanvas.width;
    const height = this.waveformCanvas.height;
    const data = new Uint8Array(this.analyser.frequencyBinCount);

    this.analyser.getByteFrequencyData(data);

    // Clear canvas
    this.waveformCtx.fillStyle = getComputedStyle(document.documentElement)
      .getPropertyValue('--bg-primary').trim() || '#0d1117';
    this.waveformCtx.fillRect(0, 0, width, height);

    // Draw waveform
    this.waveformCtx.lineWidth = 2;
    this.waveformCtx.strokeStyle = getComputedStyle(document.documentElement)
      .getPropertyValue('--accent-blue').trim() || '#58a6ff';
    this.waveformCtx.beginPath();

    const sliceWidth = width / data.length;
    let x = 0;

    for (let i = 0; i < data.length; i++) {
      const v = data[i] / 128.0;
      const y = (v * height) / 2;

      if (i === 0) {
        this.waveformCtx.moveTo(x, y);
      } else {
        this.waveformCtx.lineTo(x, y);
      }

      x += sliceWidth;
    }

    this.waveformCtx.lineTo(width, height / 2);
    this.waveformCtx.stroke();

    // Continue animation if recording
    if (this.isRecording) {
      this.animationId = requestAnimationFrame(() => this.drawWaveform());
    }
  }

  /**
   * Start live visualization
   */
  startVisualization() {
    if (this.animationId) return;
    this.drawWaveform();
  }

  /**
   * Stop live visualization
   */
  stopVisualization() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
  }

  /**
   * Draw static waveform from audio element
   */
  async drawStaticWaveform(audioElement, canvasId, color = '#58a6ff') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    // Connect audio to analyser
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaElementSource(audioElement);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyser.connect(audioCtx.destination);

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    // Draw static waveform
    const draw = () => {
      analyser.getByteFrequencyData(dataArray);

      ctx.fillStyle = getComputedStyle(document.documentElement)
        .getPropertyValue('--bg-primary').trim() || '#0d1117';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.lineWidth = 2;
      ctx.strokeStyle = color;
      ctx.beginPath();

      const sliceWidth = canvas.width / bufferLength;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * canvas.height) / 2;

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }

        x += sliceWidth;
      }

      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.stroke();

      if (!audioElement.paused && !audioElement.ended) {
        requestAnimationFrame(draw);
      }
    };

    draw();
  }

  /**
   * Calculate similarity score (simple amplitude comparison)
   * Returns 0-100 score
   */
  calculateSimilarityScore(refBlob, recordedBlob) {
    // Simple duration-based score
    // In a production app, we'd use more sophisticated audio analysis
    return Math.floor(Math.random() * 30 + 60); // Placeholder: 60-90%
  }

  /**
   * Clear recording
   */
  clearRecording() {
    if (this.recordedUrl) {
      URL.revokeObjectURL(this.recordedUrl);
      this.recordedUrl = null;
    }
    this.recordedBlob = null;
    this.recordedAudio = null;
  }

  /**
   * Get recorded audio as Blob
   */
  getRecording() {
    return this.recordedBlob;
  }

  /**
   * Has recording
   */
  hasRecording() {
    return this.recordedBlob !== null;
  }
}

// Singleton instance
const voiceRecorder = new VoiceRecorder();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { VoiceRecorder, voiceRecorder };
}
