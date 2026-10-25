/* Accessibilité : bouton « Contraste lisible » présent sur toutes les pages.
 *
 * Activé, il parcourt la page et, pour chaque texte :
 *   - relève la couleur réelle du texte et celle de son fond (dégradés compris) ;
 *   - si le contraste est inférieur à 4,5:1 (3:1 pour un grand texte), assombrit ou éclaircit la couleur du
 *     texte juste ce qu'il faut, en gardant sa teinte ;
 *   - agrandit à 14 px les textes plus petits.
 * Désactivé, il restaure exactement les styles d'origine : la page redevient identique à celle du site.
 * Le choix est mémorisé dans le navigateur (localStorage).
 */
(function () {
  'use strict';
  if (window.__cargolinkAccessibilite) { return; }
  window.__cargolinkAccessibilite = true;

  var CLE = 'cargolink-contraste';           // même clé que accessibilite/middleware.py
  var CLASSE = 'a11y-contraste';
  var RACINE = document.documentElement;
  var TAILLE_MIN = 14;                       // px
  var CONTRASTE_MIN = 4.55;                  // 4,5:1 exigé, avec une marge d'arrondi
  var CONTRASTE_GRAND = 3.05;                // texte d'au moins 24 px, ou 18,66 px en gras : 3:1
  var BALISES_IGNOREES = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEMPLATE: 1, HEAD: 1, META: 1, LINK: 1, TITLE: 1, OPTION: 1, OPTGROUP: 1 };
  var CHAMPS = { INPUT: 1, TEXTAREA: 1, SELECT: 1 };

  var modifications = new Map();             // élément -> { propriété: valeur d'origine }
  var actif = false;
  var observateur = null;
  var minuterie = null;
  var enAttente = new Set();
  window.__a11yImpossibles = [];

  /* ---------- Couleurs ---------- */

  function lireCouleur(texte) {
    if (!texte) { return null; }
    var m = texte.match(/^rgba?\(([^)]+)\)$/);
    var p;
    if (m) {
      p = m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat);
      if (p.length < 3 || p.some(isNaN)) { return null; }
      return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? (p[3] > 1 ? p[3] / 100 : p[3]) : 1 };
    }
    m = texte.match(/^color\(srgb ([^)]+)\)$/);
    if (m) {
      p = m[1].split(/[\s\/]+/).filter(Boolean).map(parseFloat);
      if (p.length < 3 || p.some(isNaN)) { return null; }
      return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1 };
    }
    return null;
  }

  function lineaire(v) { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
  function luminance(c) { return 0.2126 * lineaire(c.r) + 0.7152 * lineaire(c.g) + 0.0722 * lineaire(c.b); }
  function rapport(a, b) {
    var x = luminance(a), y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }
  function composer(devant, derriere) {
    return {
      r: devant.r * devant.a + derriere.r * (1 - devant.a),
      g: devant.g * devant.a + derriere.g * (1 - devant.a),
      b: devant.b * devant.a + derriere.b * (1 - devant.a),
      a: 1
    };
  }
  function melanger(c, cible, t) {
    return { r: c.r + (cible.r - c.r) * t, g: c.g + (cible.g - c.g) * t, b: c.b + (cible.b - c.b) * t, a: 1 };
  }
  function css(c) { return 'rgb(' + Math.round(c.r) + ', ' + Math.round(c.g) + ', ' + Math.round(c.b) + ')'; }

  /* ---------- Fond et opacité réels d'un élément ---------- */

  function couleursDuDegrade(image) {
    var trouvees = image.match(/rgba?\([^)]*\)|color\(srgb[^)]*\)/g) || [];
    return trouvees.map(lireCouleur).filter(Boolean);
  }

  function dedoublonner(liste) {
    var vus = {}, resultat = [];
    liste.forEach(function (c) {
      var cle = Math.round(c.r) + ',' + Math.round(c.g) + ',' + Math.round(c.b);
      if (!vus[cle] && resultat.length < 16) { vus[cle] = 1; resultat.push(c); }
    });
    return resultat;
  }

  // Renvoie { liste: couleurs possibles du fond, incertain: fond impossible à connaître (image) }.
  function fond(el, memo) {
    if (memo.has(el)) { return memo.get(el); }
    var s = getComputedStyle(el);
    var parent = el.parentElement;
    var base = parent ? fond(parent, memo) : { liste: [{ r: 255, g: 255, b: 255, a: 1 }], incertain: false };
    var couleur = lireCouleur(s.backgroundColor);
    var dessous;
    if (couleur && couleur.a >= 1) { dessous = [couleur]; }
    else if (couleur && couleur.a > 0) { dessous = base.liste.map(function (b) { return composer(couleur, b); }); }
    else { dessous = base.liste; }
    var resultat;
    var image = s.backgroundImage;
    if (image && image !== 'none') {
      var stops = /gradient\(/.test(image) ? couleursDuDegrade(image) : [];
      if (!stops.length) {
        resultat = { liste: dessous, incertain: true };           // image : fond inconnu
      } else {
        var liste = [];
        stops.forEach(function (c) { dessous.forEach(function (b) { liste.push(composer(c, b)); }); });
        resultat = { liste: dedoublonner(liste), incertain: base.incertain };
      }
    } else {
      resultat = { liste: dessous, incertain: couleur && couleur.a >= 1 ? false : base.incertain };
    }
    memo.set(el, resultat);
    return resultat;
  }

  function opacite(el, memo) {
    if (memo.has(el)) { return memo.get(el); }
    var o = parseFloat(getComputedStyle(el).opacity);
    if (isNaN(o)) { o = 1; }
    var total = o * (el.parentElement ? opacite(el.parentElement, memo) : 1);
    memo.set(el, total);
    return total;
  }

  /* ---------- Choix de la couleur corrigée ---------- */

  function pireContraste(c, liste, op) {
    var pire = Infinity;
    liste.forEach(function (b) {
      var devant = composer({ r: c.r, g: c.g, b: c.b, a: (c.a === undefined ? 1 : c.a) * op }, b);
      pire = Math.min(pire, rapport(devant, b));
    });
    return pire;
  }

  // Couleur de même teinte, assombrie ou éclaircie au minimum pour atteindre le contraste exigé.
  function corriger(fg, liste, exige, op) {
    var noir = { r: 0, g: 0, b: 0, a: 1 }, blanc = { r: 255, g: 255, b: 255, a: 1 };
    var pn = pireContraste(noir, liste, op), pb = pireContraste(blanc, liste, op);
    if (Math.max(pn, pb) < exige) { return null; }
    var cible = pn >= pb ? noir : blanc;
    if (pn >= exige && pb >= exige) {
      var lumFond = liste.reduce(function (s, b) { return s + luminance(b); }, 0) / liste.length;
      cible = luminance(fg) <= lumFond ? noir : blanc;               // rester du même côté que la couleur d'origine
    }
    var bas = 0, haut = 1;
    for (var i = 0; i < 14; i++) {
      var milieu = (bas + haut) / 2;
      if (pireContraste(melanger(fg, cible, milieu), liste, op) >= exige) { haut = milieu; } else { bas = milieu; }
    }
    return melanger(fg, cible, haut);
  }

  /* ---------- Modification et restauration des styles ---------- */

  function poser(el, propriete, valeur) {
    var info = modifications.get(el);
    if (!info) { info = {}; modifications.set(el, info); }
    if (!(propriete in info)) {
      info[propriete] = { valeur: el.style.getPropertyValue(propriete), priorite: el.style.getPropertyPriority(propriete) };
    }
    el.style.setProperty(propriete, valeur, 'important');
  }

  function restaurer(el) {
    var info = modifications.get(el);
    if (!info) { return; }
    Object.keys(info).forEach(function (propriete) {
      var origine = info[propriete];
      if (origine.valeur) { el.style.setProperty(propriete, origine.valeur, origine.priorite); }
      else { el.style.removeProperty(propriete); }
    });
    if (el.getAttribute('style') === '') { el.removeAttribute('style'); }
    modifications.delete(el);
  }

  /* ---------- Parcours de la page ---------- */

  function aUnTexte(el) {
    if (CHAMPS[el.tagName]) { return el.type !== 'hidden' && el.type !== 'checkbox' && el.type !== 'radio' && el.type !== 'range' && el.type !== 'file'; }
    for (var n = el.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3 && n.nodeValue.trim()) { return true; }
    }
    return false;
  }

  function collecter(racine, ensemble) {
    if (racine.nodeType !== 1 || racine.closest('[data-a11y-ignore]')) { return; }
    var tous = [racine].concat(Array.prototype.slice.call(racine.querySelectorAll('*')));
    tous.forEach(function (el) {
      if (BALISES_IGNOREES[el.tagName] || (typeof SVGElement !== 'undefined' && el instanceof SVGElement)) { return; }
      if (el.closest('[data-a11y-ignore]') || !aUnTexte(el)) { return; }
      if (!el.getClientRects().length || getComputedStyle(el).visibility === 'hidden') { return; }
      var boite = el.getBoundingClientRect();
      if (boite.width < 2 || boite.height < 2 || parseFloat(getComputedStyle(el).fontSize) <= 1) { return; }
      ensemble.add(el);
    });
  }

  function traiter(racines) {
    var elements = new Set();
    racines.forEach(function (r) { collecter(r, elements); });
    elements.forEach(restaurer);              // on repart des styles d'origine pour décider

    // 1. Lecture seule (aucune écriture : pas de recalcul de mise en page entre deux éléments)
    var memoFond = new Map(), memoOpacite = new Map(), plan = [];
    elements.forEach(function (el) {
      var s = getComputedStyle(el);
      var decision = { el: el };
      var taille = parseFloat(s.fontSize), poids = parseInt(s.fontWeight, 10) || 400;
      if (taille < TAILLE_MIN) { decision.taille = true; }

      var fg = lireCouleur(s.color), f = fond(el, memoFond);
      if (fg && f.liste.length && !f.incertain) {
        var exige = (taille >= 24 || (taille >= 18.66 && poids >= 700)) ? CONTRASTE_GRAND : CONTRASTE_MIN;
        var op = opacite(el, memoOpacite);
        if (pireContraste(fg, f.liste, op) < exige) {
          if (op < 1) {                       // texte estompé par une opacité : on la neutralise
            decision.opacite = [];
            for (var e = el; e; e = e.parentElement) {
              if (parseFloat(getComputedStyle(e).opacity) < 1) { decision.opacite.push(e); }
            }
            op = 1;
          }
          if (pireContraste(fg, f.liste, op) < exige) {
            var corrigee = corriger(fg, f.liste, exige, op);
            if (corrigee) { decision.couleur = css(corrigee); }
            else { window.__a11yImpossibles.push(el.tagName.toLowerCase() + '.' + (el.className || '') + ' : fonds trop différents'); }
          }
        }
      } else if (f.incertain) {
        window.__a11yImpossibles.push(el.tagName.toLowerCase() + '.' + (el.className || '') + ' : fond en image');
      }
      if (decision.taille || decision.couleur || decision.opacite) { plan.push(decision); }
    });

    // 2. Écriture
    plan.forEach(function (d) {
      if (d.couleur) { poser(d.el, 'color', d.couleur); }
      if (d.taille) { poser(d.el, 'font-size', TAILLE_MIN + 'px'); }
      if (d.opacite) { d.opacite.forEach(function (e) { poser(e, 'opacity', '1'); }); }
    });
  }

  /* ---------- Contenu ajouté après le chargement (popups, fenêtres…) ---------- */

  function observer() {
    if (observateur || !document.body) { return; }
    observateur = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        if (m.type === 'childList') {
          Array.prototype.forEach.call(m.addedNodes, function (n) {
            if (n.nodeType === 1) { enAttente.add(n); }
            else if (n.nodeType === 3 && m.target.nodeType === 1) { enAttente.add(m.target); }   // texte ajouté dans un élément existant
          });
        } else if (m.type === 'characterData') {
          if (m.target.parentElement) { enAttente.add(m.target.parentElement); }                 // texte modifié
        } else if (m.target.nodeType === 1) { enAttente.add(m.target); }
      });
      if (enAttente.size && !minuterie) { minuterie = setTimeout(traiterAjouts, 120); }
    });
    observateur.observe(document.body, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden', 'open'] });
  }

  function traiterAjouts() {
    minuterie = null;
    if (!actif) { enAttente.clear(); return; }
    var racines = Array.from(enAttente);
    enAttente.clear();
    if (observateur) { observateur.disconnect(); }
    try { traiter(racines); } finally {
      observateur = null;
      observer();
    }
  }

  /* ---------- Activation / désactivation ---------- */

  function memoriser(valeur) {
    try { if (valeur) { localStorage.setItem(CLE, '1'); } else { localStorage.removeItem(CLE); } } catch (e) { /* stockage indisponible */ }
  }

  function activer() {
    actif = true;
    RACINE.classList.add(CLASSE);
    if (observateur) { observateur.disconnect(); observateur = null; }
    window.__a11yImpossibles = [];
    try { traiter([document.body]); } catch (erreur) { if (window.console) { console.warn('Accessibilité :', erreur); } }
    observer();
    RACINE.setAttribute('data-a11y-pret', '1');
    majBouton();
  }

  function desactiver() {
    actif = false;
    if (observateur) { observateur.disconnect(); observateur = null; }
    if (minuterie) { clearTimeout(minuterie); minuterie = null; }
    enAttente.clear();
    Array.from(modifications.keys()).forEach(restaurer);
    RACINE.classList.remove(CLASSE);
    RACINE.removeAttribute('data-a11y-pret');
    majBouton();
  }

  /* ---------- Bouton ---------- */

  var bouton = null, annonce = null;

  function majBouton() {
    if (!bouton) { return; }
    bouton.setAttribute('aria-pressed', actif ? 'true' : 'false');
    bouton.querySelector('.a11y-etat').textContent = actif ? 'Activé' : 'Désactivé';
  }

  function annoncer(texte) {
    annonce.textContent = '';
    setTimeout(function () { annonce.textContent = texte; }, 50);
  }

  function creerBouton() {
    bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.id = 'a11y-bouton';
    bouton.setAttribute('data-a11y-ignore', '');
    bouton.setAttribute('aria-pressed', 'false');
    bouton.setAttribute('aria-describedby', 'a11y-aide');
    bouton.innerHTML =
      '<svg aria-hidden="true" focusable="false" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="7.5" r="1.4" fill="currentColor"></circle>' +
      '<path d="M7 10.5l5 1 5-1M12 11.5V16m0 0l-2.5 3.5M12 16l2.5 3.5"></path></svg>' +
      '<span class="a11y-libelle">Accessibilité</span><span class="a11y-etat" aria-hidden="true">Désactivé</span>';

    var aide = document.createElement('span');
    aide.id = 'a11y-aide';
    aide.className = 'a11y-sr';
    aide.setAttribute('data-a11y-ignore', '');
    aide.textContent = 'Contraste lisible : applique des couleurs et des tailles de texte plus lisibles sur toutes les pages.';

    annonce = document.createElement('div');
    annonce.className = 'a11y-sr';
    annonce.setAttribute('role', 'status');
    annonce.setAttribute('aria-live', 'polite');
    annonce.setAttribute('data-a11y-ignore', '');

    document.body.appendChild(bouton);
    document.body.appendChild(aide);
    document.body.appendChild(annonce);

    bouton.addEventListener('click', function () {
      if (actif) { desactiver(); memoriser(false); annoncer('Contraste lisible désactivé'); }
      else { activer(); memoriser(true); annoncer('Contraste lisible activé'); }
    });
  }

  function demarrer() {
    creerBouton();
    var memorise = false;
    try { memorise = localStorage.getItem(CLE) === '1'; } catch (e) { /* stockage indisponible */ }
    if (memorise) { activer(); } else { majBouton(); }
    // Les autres onglets restent synchronisés avec ce choix.
    window.addEventListener('storage', function (evenement) {
      if (evenement.key !== CLE) { return; }
      if (evenement.newValue === '1' && !actif) { activer(); }
      if (evenement.newValue !== '1' && actif) { desactiver(); }
    });
  }

  var AIDES = {
    depart_ville: 'Indiquez la ville où les marchandises seront enlevées.',
    depart_adresse: 'Saisissez l’adresse précise du lieu d’enlèvement.',
    date_depart: 'Choisissez la date souhaitée pour l’enlèvement.',
    arrivee_ville: 'Indiquez la ville de livraison.',
    arrivee_adresse: 'Saisissez l’adresse précise de livraison.',
    date_limite: 'Choisissez la date au plus tard à laquelle la livraison doit être reçue.',
    destinataire_nom: 'Indiquez le nom de l’entreprise ou de la personne qui recevra les marchandises.',
    destinataire_contact: 'Indiquez le nom du responsable à contacter pour la réception.',
    destinataire_tel: 'Saisissez un numéro de téléphone composé uniquement de chiffres.',
    description: 'Décrivez la marchandise et son conditionnement sans ajouter d’informations confidentielles.',
    type: 'Choisissez le type de conditionnement ou de marchandise.',
    poids: 'Saisissez le poids total correspondant, en kilogrammes.',
    volume: 'Saisissez le volume total correspondant, en mètres cubes.',
    fragile: 'Cochez cette case si la marchandise doit être manipulée avec précaution.',
    budget: 'Indiquez le budget maximal souhaité en dinars tunisiens. Ce champ peut rester vide.',
    modalite_paiement: 'Choisissez le moment auquel vous souhaitez régler le transport.',
    validite_offres: 'Choisissez la durée pendant laquelle les transporteurs pourront répondre.',
    immatriculation: 'Saisissez l’immatriculation du véhicule, sans erreur.',
    marque: 'Indiquez la marque du véhicule.',
    modele: 'Indiquez le modèle du véhicule.',
    annee: 'Indiquez l’année de mise en circulation du véhicule.',
    type_vehicule: 'Choisissez le type de véhicule correspondant à ses caractéristiques.',
    capacite_poids_kg: 'Indiquez la charge maximale autorisée du véhicule, en kilogrammes.',
    capacite_volume_m3: 'Indiquez le volume maximal du véhicule, en mètres cubes.',
    capacite_kg: 'Cette valeur est reprise de la capacité du véhicule sélectionné.',
    volume_m3: 'Cette valeur est reprise du volume disponible du véhicule sélectionné.',
    kilometrage: 'Indiquez le kilométrage actuellement affiché au compteur, si vous le connaissez.',
    kilometrage_releve: 'Indiquez le kilométrage relevé au compteur lors de cette opération.',
    date_releve_km: 'Indiquez la date à laquelle le kilométrage a été relevé.',
    photo: 'Ajoutez une photo nette du véhicule, au format JPG, PNG ou WebP.',
    date_debut: 'Choisissez la date et l’heure de début de la période.',
    date_fin: 'Choisissez la date et l’heure de fin de la période.',
    zone_depart: 'Indiquez la zone où le véhicule sera disponible au départ.',
    zone_arrivee: 'Indiquez la zone où le véhicule sera disponible à l’arrivée.',
    motif: 'Choisissez le motif qui décrit le mieux la situation.',
    motif_moderation: 'Expliquez brièvement la raison de la décision de modération.',
    trajet: 'Choisissez l’un de vos trajets publiés qui correspond à cette demande.',
    prix: 'Saisissez le prix proposé en dinars tunisiens.',
    message: 'Ajoutez un message utile au sujet de votre proposition.',
    statut: 'Choisissez le statut correspondant à la situation actuelle.',
    titre: 'Résumez cette étape du transport en quelques mots.',
    lieu: 'Indiquez la ville ou le lieu où se trouve actuellement le transport.',
    note: 'Choisissez une note de 1 à 5 selon votre expérience.',
    commentaire: 'Décrivez les faits de façon claire, précise et respectueuse.',
    montant_prejudice: 'Indiquez le montant estimé du préjudice en dinars tunisiens, si vous le connaissez.',
    reponse: 'Rédigez une réponse claire à destination de l’auteur du dossier.',
    email: 'Saisissez une adresse e-mail valide.',
    username: 'Saisissez l’adresse e-mail associée à votre compte.',
    full_name: 'Saisissez le nom complet de la personne ou de l’entreprise.',
    role: 'Choisissez le rôle qui correspond à cet utilisateur.',
    code: 'Saisissez le code à six chiffres reçu par e-mail.',
    password: 'Saisissez le mot de passe de votre compte.',
    password1: 'Choisissez un mot de passe conforme aux règles affichées.',
    password2: 'Saisissez à nouveau le même mot de passe.',
    consignes: 'Ajoutez toute consigne utile à la préparation, à l’enlèvement ou à la livraison.'
  };

  function aidePour(champ, label) {
    var aides = champ.getAttribute('data-help') || champ.getAttribute('title') ||
      (label && label.getAttribute('data-help'));
    var references = (champ.getAttribute('aria-describedby') || '').split(/\s+/);
    if (!aides) {
      references.some(function (reference) {
        var element = document.getElementById(reference);
        if (element && !element.closest('[role="alert"], .field-error, .form-error, .errorlist') &&
            element.textContent.trim()) {
          aides = element.textContent.trim();
          return true;
        }
        return false;
      });
    }
    if (!aides && champ.parentElement) {
      var aideVisible = champ.parentElement.querySelector('.portal-input-hint, .field-help, .helptext, .help-text, [data-field-help]');
      if (aideVisible) { aides = aideVisible.textContent.trim(); }
    }
    var identifiant = (champ.name || champ.id || '').split('-').pop();
    if (aides) { return aides; }
    if (identifiant === 'description' &&
        !/marchandise/i.test(label ? label.textContent : '') &&
        !/marchandises/i.test(champ.name || '')) {
      return 'Décrivez les faits et les informations utiles de façon claire, précise et respectueuse.';
    }
    if (identifiant === 'type' && !/conditionnement/i.test(label ? label.textContent : '')) {
      return 'Choisissez l’option qui correspond à votre situation.';
    }
    if (AIDES[identifiant]) { return AIDES[identifiant]; }
    if (champ.placeholder) { return 'Exemple : ' + champ.placeholder; }
    if (champ.type === 'email') { return 'Saisissez une adresse e-mail valide.'; }
    if (champ.type === 'password') { return 'Saisissez le mot de passe demandé.'; }
    if (champ.type === 'date' || champ.type === 'datetime-local') { return 'Choisissez la date demandée.'; }
    if (champ.type === 'number') { return 'Saisissez une valeur numérique dans l’unité indiquée.'; }
    if (champ.type === 'checkbox') { return 'Cochez cette case si cette option s’applique.'; }
    if (champ.tagName === 'SELECT') { return 'Choisissez l’option qui correspond à votre situation.'; }
    if (champ.tagName === 'TEXTAREA') { return 'Ajoutez les informations utiles de façon claire et précise.'; }
    var libelle = label ? label.textContent.replace(/\*/g, '').trim() : '';
    return libelle ? 'Saisissez les informations demandées pour « ' + libelle + ' ».' : '';
  }

  function preparerAidesFormulaires(racine) {
    var libelles = (racine || document).querySelectorAll('form label');
    Array.prototype.forEach.call(libelles, function (label) {
      if (label.querySelector('.a11y-help-button')) { return; }
      var champ = label.control || (label.htmlFor && document.getElementById(label.htmlFor)) ||
        label.querySelector('input, select, textarea');
      if (!champ || champ.type === 'hidden' || champ.type === 'radio' ||
          champ.type === 'submit' || champ.type === 'button' || champ.type === 'reset') { return; }
      var description = aidePour(champ, label);
      if (!description) { return; }

      var conteneur = label.parentElement;
      var nombre = document.querySelectorAll('.a11y-help-tooltip').length + 1;
      var tooltipId = 'a11y-aide-champ-' + nombre;
      var boutonAide = document.createElement('button');
      boutonAide.type = 'button';
      boutonAide.className = 'a11y-help-button';
      boutonAide.textContent = '?';
      boutonAide.setAttribute('aria-label', 'Aide pour ' + label.textContent.replace(/\*/g, '').trim());
      boutonAide.setAttribute('aria-expanded', 'false');
      boutonAide.setAttribute('aria-controls', tooltipId);

      var tooltip = document.createElement('span');
      tooltip.className = 'a11y-help-tooltip';
      tooltip.id = tooltipId;
      tooltip.setAttribute('role', 'tooltip');
      tooltip.textContent = description;

      var libelle = label.querySelector('.portal-label') || label;
      libelle.classList.add('a11y-help-label');
      libelle.insertAdjacentElement('afterend', boutonAide);
      boutonAide.insertAdjacentElement('afterend', tooltip);
      if (conteneur) { conteneur.classList.add('a11y-help-container'); }

      var describedBy = (champ.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
      if (describedBy.indexOf(tooltipId) === -1) { describedBy.push(tooltipId); }
      champ.setAttribute('aria-describedby', describedBy.join(' '));
    });
  }

  function initialiserAidesFormulaires() {
    preparerAidesFormulaires(document);
    var observateurAides = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        Array.prototype.forEach.call(mutation.addedNodes, function (node) {
          if (node.nodeType === 1) { preparerAidesFormulaires(node); }
        });
      });
    });
    observateurAides.observe(document.body, { childList: true, subtree: true });

    document.addEventListener('click', function (evenement) {
      var boutonAide = evenement.target.closest('.a11y-help-button');
      if (boutonAide) {
        if (boutonAide.closest('label')) {
          evenement.preventDefault();
          evenement.stopPropagation();
        }
        var ouvrir = boutonAide.getAttribute('aria-expanded') !== 'true';
        boutonAide.setAttribute('aria-expanded', ouvrir ? 'true' : 'false');
        return;
      }
      Array.prototype.forEach.call(document.querySelectorAll('.a11y-help-button[aria-expanded="true"]'), function (bouton) {
        bouton.setAttribute('aria-expanded', 'false');
      });
    });
    document.addEventListener('keydown', function (evenement) {
      if (evenement.key === 'Escape') {
        Array.prototype.forEach.call(document.querySelectorAll('.a11y-help-button[aria-expanded="true"]'), function (bouton) {
          bouton.setAttribute('aria-expanded', 'false');
        });
      }
    });
  }

  function demarrerAccessibilite() {
    demarrer();
    initialiserAidesFormulaires();
  }

  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', demarrerAccessibilite); } else { demarrerAccessibilite(); }
})();
