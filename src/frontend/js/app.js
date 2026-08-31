/**
 * ITOM Portal Launcher Controller
 * 
 * Features:
 * 1. Global module search with '/' focus and 'Escape' dismissal
 * 2. Profile and Notification dropdown state management
 * 3. Deep-link launcher module bridge routing directly into ops_analytics.html tabs
 *    (#overview, #intune, #solarwinds, #network, #dex)
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const searchInput = document.getElementById('searchBar');
  const moduleCards = document.querySelectorAll('.module-card');
  const noResultsState = document.getElementById('noResults');
  const searchBarShortcut = document.querySelector('.search-shortcut');
  
  const profileBtn = document.getElementById('profileBtn');
  const profileDropdown = document.getElementById('profileDropdown');
  
  const notificationsBtn = document.getElementById('notificationsBtn');
  const notificationsDropdown = document.getElementById('notificationsDropdown');
  const notificationDot = document.querySelector('.notification-dot');
  const markReadBtn = document.getElementById('markReadBtn');
  const notificationItems = document.querySelectorAll('.notification-item');
  
  const launcherOverlay = document.getElementById('launcherOverlay');
  const launcherModuleName = document.getElementById('launcherModuleName');
  const launcherStatus = document.getElementById('launcherStatus');
  const launcherCancelBtn = document.getElementById('launcherCancel');

  let launcherTimeout = null;

  // --- DROPDOWNS LOGIC ---
  
  function closeAllDropdowns() {
    if (profileDropdown) profileDropdown.classList.remove('active');
    if (notificationsDropdown) notificationsDropdown.classList.remove('active');
  }

  if (profileBtn && profileDropdown) {
    profileBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (notificationsDropdown) notificationsDropdown.classList.remove('active');
      profileDropdown.classList.toggle('active');
    });
  }

  if (notificationsBtn && notificationsDropdown) {
    notificationsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (profileDropdown) profileDropdown.classList.remove('active');
      notificationsDropdown.classList.toggle('active');
    });
  }

  // Close dropdowns on clicking outside
  document.addEventListener('click', () => {
    closeAllDropdowns();
  });

  if (profileDropdown) {
    profileDropdown.addEventListener('click', (e) => e.stopPropagation());
  }
  if (notificationsDropdown) {
    notificationsDropdown.addEventListener('click', (e) => e.stopPropagation());
  }

  // Mark all notifications as read
  if (markReadBtn) {
    markReadBtn.addEventListener('click', () => {
      notificationItems.forEach(item => {
        item.classList.remove('unread');
      });
      if (notificationDot) {
        notificationDot.style.display = 'none';
      }
    });
  }

  // --- SEARCH LOGIC ---
  
  function filterModules() {
    if (!searchInput) return;
    const query = searchInput.value.toLowerCase().trim();
    let visibleCount = 0;

    moduleCards.forEach(card => {
      const nameElem = card.querySelector('.module-name');
      const descElem = card.querySelector('.module-desc');
      const name = nameElem ? nameElem.textContent.toLowerCase() : '';
      const desc = descElem ? descElem.textContent.toLowerCase() : '';
      
      if (name.includes(query) || desc.includes(query)) {
        card.classList.remove('hidden');
        visibleCount++;
      } else {
        card.classList.add('hidden');
      }
    });

    if (noResultsState) {
      noResultsState.style.display = (visibleCount === 0) ? 'flex' : 'none';
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', filterModules);
  }

  // --- KEYBOARD SHORTCUTS ---
  
  document.addEventListener('keydown', (e) => {
    // Focus search on '/' key press (if not in an input already)
    if (e.key === '/' && searchInput && document.activeElement !== searchInput) {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
    
    // Clear search and blur on Escape
    if (e.key === 'Escape') {
      if (searchInput && document.activeElement === searchInput) {
        searchInput.value = '';
        filterModules();
        searchInput.blur();
      }
      closeAllDropdowns();
      closeLauncher();
    }
  });

  // Focus and placeholder hints
  if (searchInput && searchBarShortcut) {
    searchInput.addEventListener('focus', () => {
      searchBarShortcut.textContent = 'Esc';
    });

    searchInput.addEventListener('blur', () => {
      searchBarShortcut.textContent = '/';
    });
  }

  // --- LAUNCHER & DEEP-LINK BRIDGE LOGIC ---

  /**
   * Resolve destination URL with appropriate hash routing for ops_analytics tabs.
   * @param {string} moduleName
   * @param {string} targetUrl
   * @returns {string}
   */
  function resolveModuleDestination(moduleName, targetUrl) {
    const rawTarget = (targetUrl || '').trim();
    const rawMod = (moduleName || '').toLowerCase().trim();

    // Explicit hash mapping
    if (rawTarget.includes('#network') || rawMod.includes('cmdb') || rawTarget === '#cmdb') {
      return 'ops_analytics.html#network';
    }
    if (rawTarget.includes('#solarwinds') || rawMod.includes('capacity') || rawMod.includes('tools') || rawTarget === '#capacity' || rawTarget === '#tools-center') {
      return 'ops_analytics.html#solarwinds';
    }
    if (rawTarget.includes('#dex') || rawMod.includes('dex') || rawTarget === '#dex') {
      return 'ops_analytics.html#dex';
    }
    if (rawTarget.includes('#intune') || rawMod.includes('compliance') || rawTarget === '#compliance') {
      return 'ops_analytics.html#intune';
    }
    if (rawTarget.includes('#overview') || rawMod.includes('analytics') || rawTarget === 'ops_analytics.html') {
      return 'ops_analytics.html#overview';
    }

    if (rawTarget && rawTarget !== '#' && !rawTarget.startsWith('#')) {
      return rawTarget;
    }

    return 'ops_analytics.html#overview';
  }
  
  function launchModule(moduleName, targetUrl) {
    closeAllDropdowns();
    if (launcherModuleName) launcherModuleName.textContent = moduleName;
    if (launcherOverlay) launcherOverlay.classList.add('active');
    
    if (launcherStatus) launcherStatus.textContent = isComingSoon ? 'Coming soon...' : 'Launching module console...';
    
    if (isComingSoon) return;

    // Quick 200ms visual feedback before direct navigation
    launcherTimeout = setTimeout(() => {
      closeLauncher();
      window.location.href = resolveModuleDestination(moduleName, targetUrl);
    }, 200);
  }

  function closeLauncher() {
    if (launcherOverlay) launcherOverlay.classList.remove('active');
    if (launcherTimeout) {
      clearTimeout(launcherTimeout);
      launcherTimeout = null;
    }
  }

  moduleCards.forEach(card => {
    card.addEventListener('click', (e) => {
      e.preventDefault();
      const nameElem = card.querySelector('.module-name');
      const moduleName = nameElem ? nameElem.textContent : 'Module';
      const status = card.getAttribute('data-status');
      const isComingSoon = status === 'coming-soon';
      const targetUrl = card.getAttribute('href');
      launchModule(moduleName, targetUrl, isComingSoon);
    });
  });

  if (launcherCancelBtn) {
    launcherCancelBtn.addEventListener('click', closeLauncher);
  }

  if (launcherOverlay) {
    launcherOverlay.addEventListener('click', (e) => {
      if (e.target === launcherOverlay) {
        closeLauncher();
      }
    });
  }

  // Export functions globally
  window.launchModule = launchModule;
  window.closeLauncher = closeLauncher;
  window.resolveModuleDestination = resolveModuleDestination;
});
