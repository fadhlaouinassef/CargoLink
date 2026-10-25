(() => {
  const buttons = document.querySelectorAll('[data-lecture-cible]');
  const status = document.querySelector('[data-lecture-status]');
  if (!buttons.length || !status) return;
  let current = null;
  let activeButton = null;

  function reset(message, error = false) {
    current = null;
    if (activeButton) {
      activeButton.textContent = 'Écouter les détails';
      activeButton.setAttribute('aria-pressed', 'false');
      activeButton.setAttribute('aria-label', activeButton.dataset.lectureLibelle);
      activeButton = null;
    }
    status.textContent = message;
    status.classList.toggle('lecture-status', !error);
  }

  if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
    buttons.forEach(button => { button.disabled = true; });
    reset('La lecture vocale est indisponible dans ce navigateur.', true);
    return;
  }

  const synthesis = window.speechSynthesis;
  synthesis.getVoices();

  buttons.forEach(button => {
    button.dataset.lectureLibelle = button.getAttribute('aria-label');
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => {
      const alreadyReading = activeButton === button;
      // Ignorer les événements de la lecture annulée.
      reset('Lecture arrêtée.');
      synthesis.cancel();
      if (alreadyReading) return;

      const target = document.getElementById(button.dataset.lectureCible);
      const text = target?.textContent.replace(/\s+/g, ' ').trim();
      if (!text) return;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'fr-FR';
      const voices = synthesis.getVoices().filter(voice => /^fr(?:-|$)/i.test(voice.lang));
      utterance.voice = voices.find(voice => voice.localService) || voices[0] || null;
      current = utterance;
      activeButton = button;
      button.textContent = 'Arrêter la lecture';
      button.setAttribute('aria-label', `Arrêter la lecture de ${button.dataset.lectureNom}`);
      button.setAttribute('aria-pressed', 'true');
      status.textContent = `Lecture de ${button.dataset.lectureNom} en cours.`;
      utterance.onend = () => {
        if (current === utterance) reset('Lecture terminée.');
      };
      utterance.onerror = () => {
        if (current === utterance) reset('La lecture a échoué. Vérifiez les voix françaises disponibles sur votre appareil puis réessayez.', true);
      };
      try {
        synthesis.resume();
        synthesis.speak(utterance);
      } catch {
        reset('Impossible de démarrer la lecture vocale sur cet appareil.', true);
      }
    });
  });

  window.addEventListener('pagehide', () => {
    reset('');
    synthesis.cancel();
  });
})();
