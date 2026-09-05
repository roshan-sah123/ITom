/**
 * ITOM Portal Launcher Controller
 * 
 * Features:
 * 1. Global module search with '/' focus and 'Escape' dismissal
 * 2. Category Filter Pills with instant filtering
 * 3. Module launch bridge with hash-routing deep links to ops_analytics.html
 * 4. User profile and Notification dropdown management
 * 5. Keyboard accessibility (Enter to launch first result, Escape to close)
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const searchInput = document.getElementById('searchBar');
  const moduleCards = document.querySelectorAll('.module-card');
  const noResultsState = document.getElementById('noResults');
  const searchBarShortcut = document.querySelector('.search-shortcut');
  const clearSearchBtn = document.getElementById('clearSearchBtn');
  const filterPills = document.querySelectorAll('.filter-pill');
  const moduleCountBadge = document.getElementById('moduleCountBadge');
  
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

  // --- SEARCH & FILTER LOGIC ---
  
  function filterModules() {
    if (!searchInput) return;
    const query = searchInput.value.toLowerCase().trim();
    let visibleCount = 0;

    moduleCards.forEach(card => {
      const nameElem = card.querySelector('.module-name');
      const descElem = card.querySelector('.module-desc');
      const name = nameElem ? nameElem.textContent.toLowerCase() : '';
      const desc = descElem ? descElem.textContent.toLowerCase() : '';
      const cardId = (card.id || '').toLowerCase();
      
      if (name.includes(query) || desc.includes(query) || cardId.includes(query)) {
        card.classList.remove('hidden');
        visibleCount++;
      } else {
        card.classList.add('hidden');
      }
    });

    if (noResultsState) {
      noResultsState.style.display = (visibleCount === 0) ? 'flex' : 'none';
    }

    if (moduleCountBadge) {
      if (query) {
        moduleCountBadge.textContent = `${visibleCount} of ${moduleCards.length} Modules`;
      } else {
        moduleCountBadge.textContent = `${moduleCards.length} Applications`;
      }
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      // Sync active pill state
      const val = searchInput.value.toLowerCase().trim();
      let matchedPill = false;
      filterPills.forEach(pill => {
        const filterVal = (pill.getAttribute('data-filter') || '').toLowerCase();
        if (val === filterVal) {
          pill.classList.add('active');
          matchedPill = true;
        } else {
          pill.classList.remove('active');
        }
      });
      if (!matchedPill && !val) {
        const allPill = document.querySelector('.filter-pill[data-filter=""]');
        if (allPill) allPill.classList.add('active');
      }
      filterModules();
    });
  }

  // Quick Filter Pills Click Handlers
  filterPills.forEach(pill => {
    pill.addEventListener('click', () => {
      filterPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const filterVal = pill.getAttribute('data-filter') || '';
      if (searchInput) {
        searchInput.value = filterVal;
        filterModules();
        if (filterVal) {
          searchInput.focus();
        }
      }
    });
  });

  // Clear Search Button
  if (clearSearchBtn) {
    clearSearchBtn.addEventListener('click', () => {
      if (searchInput) {
        searchInput.value = '';
        searchInput.focus();
        filterPills.forEach(p => p.classList.remove('active'));
        const allPill = document.querySelector('.filter-pill[data-filter=""]');
        if (allPill) allPill.classList.add('active');
        filterModules();
      }
    });
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
        if (searchInput.value) {
          searchInput.value = '';
          filterPills.forEach(p => p.classList.remove('active'));
          const allPill = document.querySelector('.filter-pill[data-filter=""]');
          if (allPill) allPill.classList.add('active');
          filterModules();
        }
        searchInput.blur();
      }
      closeAllDropdowns();
      closeLauncher();
    }
  });

  // Press Enter to launch the first visible module card
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const visibleCards = Array.from(moduleCards).filter(c => !c.classList.contains('hidden'));
        if (visibleCards.length > 0) {
          e.preventDefault();
          visibleCards[0].click();
        }
      }
    });

    searchInput.addEventListener('focus', () => {
      if (searchBarShortcut) searchBarShortcut.textContent = 'Esc';
    });

    searchInput.addEventListener('blur', () => {
      if (searchBarShortcut) searchBarShortcut.textContent = '/';
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
    if (rawTarget.includes('#solarwinds') || rawMod.includes('capacity') || rawMod.includes('tools') || rawMod.includes('server') || rawTarget === '#capacity' || rawTarget === '#tools-center') {
      return 'ops_analytics.html#solarwinds';
    }
    if (rawTarget.includes('#cmdb') || rawMod.includes('cmdb')) {
      return 'ops_analytics.html#cmdb';
    }
    if (rawTarget.includes('#intune') || rawMod.includes('compliance') || rawMod.includes('dex') || rawTarget === '#compliance') {
      return 'ops_analytics.html#intune';
    }

    if (rawTarget && rawTarget !== '#' && !rawTarget.startsWith('#')) {
      return rawTarget;
    }

    return 'ops_analytics.html';
  }
  
  // --- OPS ANALYTICS DOMAIN DRILLDOWN MODAL (AUXILIARY ACCESS) ---
  const opsDomainModal = document.getElementById('opsDomainModal');
  const closeDomainModalBtn = document.getElementById('closeDomainModalBtn');

  function openDomainModal() {
    closeAllDropdowns();
    if (opsDomainModal) {
      opsDomainModal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  }

  function closeDomainModal() {
    if (opsDomainModal) {
      opsDomainModal.classList.remove('active');
      document.body.style.overflow = '';
    }
  }

  if (closeDomainModalBtn) {
    closeDomainModalBtn.addEventListener('click', closeDomainModal);
  }

  if (opsDomainModal) {
    opsDomainModal.addEventListener('click', (e) => {
      if (e.target === opsDomainModal) {
        closeDomainModal();
      }
    });
  }

  function launchModule(moduleName, targetUrl, isComingSoon) {
    closeAllDropdowns();
    if (launcherModuleName) launcherModuleName.textContent = moduleName;

    if (isComingSoon) {
      if (launcherStatus) {
        launcherStatus.innerHTML = `<span class="text-warning font-semibold">Phase 2 Module — In Development Pipeline</span><br><span class="text-xs text-muted">Integration with enterprise backend scheduled for upcoming release.</span>`;
      }
      if (launcherOverlay) launcherOverlay.classList.add('active');
      return;
    }

    if (launcherStatus) launcherStatus.textContent = `Launching ${moduleName}...`;
    if (launcherOverlay) launcherOverlay.classList.add('active');

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
  window.openDomainModal = openDomainModal;
  window.closeDomainModal = closeDomainModal;
  window.resolveModuleDestination = resolveModuleDestination;
});
