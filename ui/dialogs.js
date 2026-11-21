/**
 * Accessible dialog and modal manager.
 * Features:
 * - Focus trapping (Tab / Shift+Tab)
 * - Escape key to close
 * - Restores focus to the triggering element on close
 */

let activeModal = null;
let lastFocusedElement = null;

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])'
].join(',');

export function openModal(modalId, triggerElement = null) {
  const modal = document.getElementById(modalId);
  if (!modal) return;

  if (activeModal && activeModal !== modal) {
    closeModal(activeModal.id);
  }

  lastFocusedElement = triggerElement || document.activeElement;
  activeModal = modal;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");

  // Focus first focusable element inside modal
  const focusables = modal.querySelectorAll(FOCUSABLE_SELECTORS);
  if (focusables.length > 0) {
    setTimeout(() => focusables[0].focus(), 50);
  }
}

export function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;

  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");

  if (activeModal === modal) {
    activeModal = null;
  }

  if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
    lastFocusedElement.focus();
    lastFocusedElement = null;
  }
}

export function closeAllModals() {
  if (activeModal) {
    closeModal(activeModal.id);
  }
}

// Global keyboard trap & Escape handling
window.addEventListener("keydown", (e) => {
  if (!activeModal) return;

  if (e.key === "Escape") {
    e.preventDefault();
    closeModal(activeModal.id);
    return;
  }

  if (e.key === "Tab") {
    const focusables = Array.from(activeModal.querySelectorAll(FOCUSABLE_SELECTORS));
    if (focusables.length === 0) {
      e.preventDefault();
      return;
    }

    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }
});
