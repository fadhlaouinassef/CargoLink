/**
 * CargoLink Actor Portals Interactive Utilities
 * (PME & Destinataire)
 */

document.addEventListener('DOMContentLoaded', () => {
  // Mobile Sidebar Toggle
  const menuBtn = document.querySelector('.mobile-menu-btn');
  const sidebar = document.querySelector('.portal-sidebar');
  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
    // Close when clicking outside
    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && !menuBtn.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  // Interactive OTP Digits Handler
  const otpInputs = document.querySelectorAll('.otp-digit');
  if (otpInputs.length > 0) {
    otpInputs.forEach((input, index) => {
      input.addEventListener('input', (e) => {
        const val = e.target.value;
        if (val.length === 1 && index < otpInputs.length - 1) {
          otpInputs[index + 1].focus();
        }
      });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !input.value && index > 0) {
          otpInputs[index - 1].focus();
        }
      });
    });
  }

  // Interactive Signature Pad (Canvas)
  const canvas = document.querySelector('.signature-canvas');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    let isDrawing = false;
    let hasSigned = false;

    // Scale canvas for sharp rendering
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * 2;
    canvas.height = rect.height * 2;
    ctx.scale(2, 2);
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#191c1b';

    const getPos = (e) => {
      const r = canvas.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      return {
        x: clientX - r.left,
        y: clientY - r.top
      };
    };

    const startDraw = (e) => {
      isDrawing = true;
      hasSigned = true;
      const pos = getPos(e);
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y);
      e.preventDefault();
    };

    const draw = (e) => {
      if (!isDrawing) return;
      const pos = getPos(e);
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
      e.preventDefault();
    };

    const stopDraw = () => {
      isDrawing = false;
    };

    canvas.addEventListener('mousedown', startDraw);
    canvas.addEventListener('mousemove', draw);
    window.addEventListener('mouseup', stopDraw);

    canvas.addEventListener('touchstart', startDraw, { passive: false });
    canvas.addEventListener('touchmove', draw, { passive: false });
    window.addEventListener('touchend', stopDraw);

    const clearBtn = document.querySelector('#btn-clear-sig');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        hasSigned = false;
      });
    }
  }

  // Dynamic Add / Remove Goods (Marchandise) in DemandeTransport Form
  const addGoodBtn = document.querySelector('#btn-add-goods');
  const goodsTbody = document.querySelector('#goods-table-body');
  if (addGoodBtn && goodsTbody) {
    addGoodBtn.addEventListener('click', () => {
      const rowCount = goodsTbody.children.length + 1;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><input type="text" name="marchandise_desc[]" placeholder="Ex: Cartons huiles d'olive" class="portal-input" required></td>
        <td>
          <select name="marchandise_type[]" class="portal-select">
            <option value="palettes">Palettes Euro</option>
            <option value="cartons">Cartons / Colis</option>
            <option value="vrac">Vrac</option>
            <option value="frais">Produits réfrigérés</option>
            <option value="machines">Matériel / Machines</option>
          </select>
        </td>
        <td><input type="number" step="0.1" name="marchandise_poids[]" placeholder="Poids (kg)" class="portal-input" required></td>
        <td><input type="number" step="0.01" name="marchandise_volume[]" placeholder="Vol (m³)" class="portal-input"></td>
        <td><input type="checkbox" name="marchandise_fragile[]"> Fragile</td>
        <td style="text-align: center;">
          <button type="button" class="btn-remove-row" title="Supprimer la ligne">✕</button>
        </td>
      `;
      goodsTbody.appendChild(tr);

      // Bind remove
      tr.querySelector('.btn-remove-row').addEventListener('click', () => {
        tr.remove();
      });
    });

    // Bind existing remove buttons
    document.querySelectorAll('.btn-remove-row').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.target.closest('tr').remove();
      });
    });
  }

  // Interactive Offer Acceptance Modal or Notification
  const acceptButtons = document.querySelectorAll('.btn-accept-offer');
  acceptButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const carrier = btn.getAttribute('data-carrier') || 'ce transporteur';
      const price = btn.getAttribute('data-price') || '';
      if (confirm(`Confirmez-vous la sélection de ${carrier} pour un montant de ${price} TND ?\nCette action créera le transport et notifiera le destinataire.`)) {
        alert('Offre acceptée avec succès ! Le transport #TR-2026-09 a été généré.');
        window.location.href = btn.getAttribute('data-redirect') || '#';
      }
    });
  });
});
