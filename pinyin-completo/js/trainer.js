/**
 * PINYIN TRAINER - Quiz & Spaced Repetition System
 * Gamificação com revisão espaçada
 */

class PinyinTrainer {
  constructor() {
    this.cards = [];
    this.currentIndex = 0;
    this.score = 0;
    this.totalQuestions = 0;
    this.streak = 0;
    this.maxStreak = 0;
    this.errors = []; // Cards that were answered incorrectly
    this.history = []; // Answer history
    this.quizMode = false;
    this.mode = 'browse'; // 'browse' | 'quiz' | 'record'

    // Storage
    this.storageKey = 'pinyin-trainer-stats';
    this.loadStats();
  }

  /**
   * Initialize trainer with cards
   */
  init(cards) {
    this.cards = cards;
    this.currentIndex = 0;
  }

  /**
   * Start quiz mode
   */
  startQuiz(shuffle = true) {
    this.quizMode = true;
    this.mode = 'quiz';
    this.currentIndex = 0;
    this.score = 0;
    this.totalQuestions = 0;
    this.errors = [];
    this.history = [];

    if (shuffle) {
      this.shuffleCards();
    }

    // Prioritize error cards
    if (this.errors.length > 0) {
      this.prioritizeErrors();
    }

    return this.getCurrentQuestion();
  }

  /**
   * Shuffle cards for quiz
   */
  shuffleCards() {
    for (let i = this.cards.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [this.cards[i], this.cards[j]] = [this.cards[j], this.cards[i]];
    }
  }

  /**
   * Prioritize error cards (spaced repetition)
   */
  prioritizeErrors() {
    const errorCards = this.cards.filter(c => c.isError);
    const goodCards = this.cards.filter(c => !c.isError);

    // Interleave error cards with good cards
    this.cards = [];
    let ei = 0, gi = 0;
    while (ei < errorCards.length || gi < goodCards.length) {
      if (ei < errorCards.length && ei < 3) {
        this.cards.push(errorCards[ei++]);
      }
      if (gi < goodCards.length) {
        this.cards.push(goodCards[gi++]);
      }
    }
  }

  /**
   * Get current question
   */
  getCurrentQuestion() {
    if (this.currentIndex >= this.cards.length) {
      return null; // Quiz complete
    }

    const card = this.cards[this.currentIndex];
    return {
      card,
      options: this.generateOptions(card),
      progress: {
        current: this.currentIndex + 1,
        total: this.cards.length,
        score: this.score,
        streak: this.streak
      }
    };
  }

  /**
   * Generate answer options
   */
  generateOptions(card) {
    const allLabels = this.cards.map(c => c.label);
    const options = [card.label];

    // Get 3 random different options
    const otherLabels = allLabels.filter(l => l !== card.label);
    while (options.length < 4 && otherLabels.length > 0) {
      const idx = Math.floor(Math.random() * otherLabels.length);
      const label = otherLabels.splice(idx, 1)[0];
      if (!options.includes(label)) {
        options.push(label);
      }
    }

    // Shuffle options
    return this.shuffleArray(options);
  }

  /**
   * Submit answer
   */
  submitAnswer(selectedLabel) {
    const card = this.cards[this.currentIndex];
    const isCorrect = selectedLabel === card.label;

    // Record history
    this.history.push({
      card,
      selected: selectedLabel,
      correct: isCorrect,
      timestamp: Date.now()
    });

    if (isCorrect) {
      this.score++;
      this.streak++;
      this.maxStreak = Math.max(this.maxStreak, this.streak);
      card.isError = false;
    } else {
      this.streak = 0;
      card.isError = true;
      this.errors.push(card);
    }

    this.totalQuestions++;

    // Move to next
    this.currentIndex++;

    return {
      isCorrect,
      correct: card.label,
      selected: selectedLabel,
      nextQuestion: this.getCurrentQuestion(),
      stats: this.getStats()
    };
  }

  /**
   * Get current stats
   */
  getStats() {
    return {
      score: this.score,
      total: this.totalQuestions,
      streak: this.streak,
      maxStreak: this.maxStreak,
      accuracy: this.totalQuestions > 0
        ? Math.round((this.score / this.totalQuestions) * 100)
        : 0
    };
  }

  /**
   * End quiz
   */
  endQuiz() {
    this.quizMode = false;
    this.mode = 'browse';
    this.saveStats();

    return {
      ...this.getStats(),
      totalQuestions: this.totalQuestions,
      history: this.history
    };
  }

  /**
   * Set training mode
   */
  setMode(mode) {
    this.mode = mode;
    this.quizMode = mode === 'quiz';
  }

  /**
   * Save stats to localStorage
   */
  saveStats() {
    const stats = {
      totalQuizzes: 0,
      totalQuestions: 0,
      totalCorrect: 0,
      maxStreak: this.maxStreak,
      errorCards: this.errors.map(c => c.label),
      lastPlayed: Date.now()
    };

    try {
      const existing = JSON.parse(localStorage.getItem(this.storageKey)) || {};
      stats.totalQuizzes = (existing.totalQuizzes || 0) + 1;
      stats.totalQuestions = (existing.totalQuestions || 0) + this.totalQuestions;
      stats.totalCorrect = (existing.totalCorrect || 0) + this.score;
      stats.maxStreak = Math.max(stats.maxStreak, existing.maxStreak || 0);

      localStorage.setItem(this.storageKey, JSON.stringify(stats));
    } catch (e) {
      console.warn('Could not save stats:', e);
    }
  }

  /**
   * Load stats from localStorage
   */
  loadStats() {
    try {
      const stats = JSON.parse(localStorage.getItem(this.storageKey));
      if (stats) {
        this.maxStreak = stats.maxStreak || 0;
      }
    } catch (e) {
      // Ignore
    }
  }

  /**
   * Get saved stats
   */
  getSavedStats() {
    try {
      return JSON.parse(localStorage.getItem(this.storageKey)) || null;
    } catch (e) {
      return null;
    }
  }

  /**
   * Reset stats
   */
  resetStats() {
    try {
      localStorage.removeItem(this.storageKey);
    } catch (e) {
      // Ignore
    }
  }

  /**
   * Shuffle array (Fisher-Yates)
   */
  shuffleArray(array) {
    const arr = [...array];
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }
}

// Singleton instance
const pinyinTrainer = new PinyinTrainer();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PinyinTrainer, pinyinTrainer };
}
