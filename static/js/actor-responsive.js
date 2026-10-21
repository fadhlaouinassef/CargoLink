document.addEventListener('DOMContentLoaded', () => {
  const menu = document.querySelector('.mobile-menu-btn');
  const sidebar = document.querySelector('.portal-sidebar');
  if (menu && sidebar) {
    const syncMenu = () => {
      const open = sidebar.classList.contains('open');
      menu.setAttribute('aria-expanded', String(open));
      menu.setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu');
      sidebar.inert = window.matchMedia('(max-width: 992px)').matches && !open;
    };
    new MutationObserver(syncMenu).observe(sidebar, { attributes: true, attributeFilter: ['class'] });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && sidebar.classList.contains('open')) {
        sidebar.classList.remove('open');
        menu.focus();
      }
    });
    window.matchMedia('(max-width: 992px)').addEventListener('change', () => {
      sidebar.classList.remove('open');
      syncMenu();
    });
    syncMenu();
  }
  document.querySelectorAll('.portal-table-wrap').forEach(wrapper => {
    wrapper.tabIndex = 0;
    wrapper.setAttribute('role', 'region');
    wrapper.setAttribute('aria-label', 'Tableau défilant horizontalement');
  });
  document.querySelectorAll('.otp-digit').forEach(input => {
    input.inputMode = 'numeric';
  });
  // The signature tab starts hidden. Size its bitmap when it becomes visible,
  // and retain the drawing when the screen changes size or orientation.
  const canvas = document.querySelector('.signature-canvas');
  if (canvas) {
    new ResizeObserver(() => {
      const { width, height } = canvas.getBoundingClientRect();
      if (!width || !height) return;
      const scale = window.devicePixelRatio || 1;
      const bitmapWidth = Math.round(width * scale);
      const bitmapHeight = Math.round(height * scale);
      if (canvas.width === bitmapWidth && canvas.height === bitmapHeight) return;
      const previous = document.createElement('canvas');
      previous.width = canvas.width;
      previous.height = canvas.height;
      if (previous.width && previous.height) {
        previous.getContext('2d').drawImage(canvas, 0, 0);
      }
      canvas.width = bitmapWidth;
      canvas.height = bitmapHeight;
      const context = canvas.getContext('2d');
      if (previous.width && previous.height) {
        context.drawImage(previous, 0, 0, bitmapWidth, bitmapHeight);
      }
      context.setTransform(scale, 0, 0, scale, 0, 0);
      context.lineWidth = 2.5;
      context.lineCap = 'round';
      context.strokeStyle = '#191c1b';
    }).observe(canvas);
  }
});
