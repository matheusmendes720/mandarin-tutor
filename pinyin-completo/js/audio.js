/**
 * PINYIN TRAINER - Audio Player with Visualization
 * Sincroniza reprodução com feedback visual
 */

class PinyinAudio {
  constructor() {
    this.audioContext = null;
    this.analyser = null;
    this.currentAudio = null;
    this.isPlaying = false;
    this.activeCell = null;
    this.progressInterval = null;

    this.init();
  }

  init() {
    // Initialize AudioContext on first user interaction
    document.addEventListener('click', () => this.initAudioContext(), { once: true });
  }

  initAudioContext() {
    if (this.audioContext) return;
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    this.analyser = this.audioContext.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.connect(this.audioContext.destination);
  }

  /**
   * Play audio file with visualization
   */
  async play(src, cell = null) {
    if (!this.audioContext) {
      this.initAudioContext();
    }

    // Stop current audio
    this.stop();

    // Resume audio context if suspended
    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume();
    }

    // Load and play audio
    this.currentAudio = new Audio(src);
    this.currentAudio.preload = 'auto';

    // Connect to analyser for visualization
    const source = this.audioContext.createMediaElementSource(this.currentAudio);
    source.connect(this.analyser);

    // Update cell state
    if (cell) {
      this.activeCell = cell;
      cell.classList.add('playing');
      this.startProgressBar(cell);
    }

    this.isPlaying = true;

    return new Promise((resolve, reject) => {
      this.currentAudio.onended = () => {
        this.isPlaying = false;
        if (cell) {
          cell.classList.remove('playing');
          this.stopProgressBar(cell);
        }
        resolve();
      };

      this.currentAudio.onerror = (e) => {
        this.isPlaying = false;
        reject(e);
      };

      this.currentAudio.play().catch(reject);
    });
  }

  stop() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }

    if (this.activeCell) {
      this.activeCell.classList.remove('playing');
      this.stopProgressBar(this.activeCell);
      this.activeCell = null;
    }

    this.isPlaying = false;
  }

  /**
   * Progress bar animation
   */
  startProgressBar(cell) {
    const progressBar = cell.querySelector('.progress-bar');
    if (!progressBar) return;

    const audio = this.currentAudio;
    if (!audio) return;

    const updateProgress = () => {
      if (!audio.duration) return;
      const percent = (audio.currentTime / audio.duration) * 100;
      progressBar.style.width = `${percent}%`;

      if (this.isPlaying) {
        this.progressInterval = requestAnimationFrame(updateProgress);
      }
    };

    this.progressInterval = requestAnimationFrame(updateProgress);
  }

  stopProgressBar(cell) {
    if (this.progressInterval) {
      cancelAnimationFrame(this.progressInterval);
      this.progressInterval = null;
    }

    const progressBar = cell.querySelector('.progress-bar');
    if (progressBar) {
      progressBar.style.width = '0%';
    }
  }

  /**
   * Get frequency data for visualization
   */
  getFrequencyData() {
    if (!this.analyser) return new Uint8Array(128);
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(data);
    return data;
  }

  /**
   * Set playback speed
   */
  setSpeed(rate) {
    if (this.currentAudio) {
      this.currentAudio.playbackRate = rate;
    }
  }
}

// Singleton instance
const pinyinAudio = new PinyinAudio();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PinyinAudio, pinyinAudio };
}
