(() => {
  const panel = document.querySelector('[data-lecture-vocale]');
  if (!panel) return;
  const buttons = document.querySelectorAll('[data-lecture-cible]');
  const pause = panel.querySelector('[data-lecture-pause]');
  const stop = panel.querySelector('[data-lecture-stop]');
  const speed = panel.querySelector('#lecture-vitesse');
  const status = panel.querySelector('[data-lecture-status]');
  let current = null;
  let activeButton = null;
  let paused = false;
  let frenchVoice = null;

  function reset(message) {
    current = null;
    paused = false;
    activeButton?.setAttribute('aria-pressed', 'false');
    activeButton = null;
    pause.disabled = true;
    stop.disabled = true;
    pause.textContent = 'Mettre en pause';
    status.textContent = message;
  }

  if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
    buttons.forEach(button => { button.disabled = true; });
    speed.disabled = true;
    reset('La lecture vocale est indisponible dans ce navigateur. Les détails restent consultables dans le tableau.');
    return;
  }

  const synthesis = window.speechSynthesis;

  function updateVoice() {
    const voices = synthesis.getVoices().filter(voice => /^fr(?:-|$)/i.test(voice.lang));
    frenchVoice = voices.find(voice => voice.localService) || voices[0] || null;
  }

  function read(button) {
    const target = document.getElementById(button.dataset.lectureCible);
    const text = target?.textContent.replace(/\s+/g, ' ').trim();
    if (!text) return;
    // Invalider l'ancienne lecture avant cancel : ses événements sont ignorés.
    reset('Préparation de la lecture…');
    synthesis.cancel();
    synthesis.resume();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'fr-FR';
    utterance.rate = Number(speed.value);
    updateVoice();
    utterance.voice = frenchVoice;
    activeButton = button;
    current = utterance;
    button.setAttribute('aria-pressed', 'true');
    pause.disabled = false;
    stop.disabled = false;
    status.textContent = `Lecture de ${button.dataset.lectureNom} en cours.`;
    utterance.onend = () => {
      if (current === utterance) reset('Lecture terminée.');
    };
    utterance.onerror = () => {
      if (current === utterance) reset('La lecture a échoué. Vérifiez les voix françaises disponibles sur votre appareil puis réessayez.');
    };
    try {
      synthesis.speak(utterance);
    } catch {
      reset('Impossible de démarrer la lecture vocale sur cet appareil.');
    }
  }

  buttons.forEach(button => {
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => read(button));
  });

  pause.addEventListener('click', () => {
    if (!current) return;
    paused = !paused;
    if (paused) synthesis.pause();
    else synthesis.resume();
    pause.textContent = paused ? 'Reprendre la lecture' : 'Mettre en pause';
    status.textContent = paused ? 'Lecture en pause.' : `Lecture de ${activeButton.dataset.lectureNom} en cours.`;
  });

  stop.addEventListener('click', () => {
    const button = activeButton;
    reset('Lecture arrêtée.');
    synthesis.cancel();
    button?.focus();
  });

  speed.addEventListener('change', () => {
    if (activeButton) read(activeButton);
  });

  // Les voix peuvent être chargées après le script, selon le navigateur.
  synthesis.addEventListener('voiceschanged', updateVoice);
  updateVoice();
  window.addEventListener('pagehide', () => {
    reset('Choisissez un élément à écouter.');
    synthesis.cancel();
  });
  reset('Choisissez un élément à écouter.');
})();
