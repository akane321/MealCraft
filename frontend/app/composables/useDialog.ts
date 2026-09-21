const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/**
 * Modal behaviour for an overlay: Escape closes it from anywhere, focus moves
 * into it and returns to whatever opened it, Tab stays inside, and the surface
 * behind it does not scroll.
 *
 * `open` may be a plain `true` for an overlay that only exists while it is open,
 * or a ref for one that stays mounted (the shopping preview does, so printing
 * has something to print).
 */
export function useDialog(
  element: Ref<HTMLElement | null>,
  onClose: () => void,
  open: Ref<boolean> | boolean = true,
) {
  const isOpen = computed(() => (typeof open === "boolean" ? open : open.value));
  let restoreTo: HTMLElement | null = null;

  function focusable(): HTMLElement[] {
    const root = element.value;
    if (!root) return [];
    return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(node => node.offsetParent !== null);
  }

  function onKeydown(event: KeyboardEvent) {
    if (!isOpen.value) return;
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const nodes = focusable();
    if (!nodes.length) return;
    const first = nodes[0]!;
    const last = nodes[nodes.length - 1]!;
    const active = document.activeElement as HTMLElement | null;
    // Wrap at both ends, and pull focus back in if it has escaped the overlay.
    if (event.shiftKey && (active === first || !element.value?.contains(active))) {
      event.preventDefault();
      last.focus();
    }
    else if (!event.shiftKey && (active === last || !element.value?.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }

  async function activate() {
    restoreTo = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    await nextTick();
    (focusable()[0] ?? element.value)?.focus();
  }

  function deactivate() {
    document.body.style.overflow = "";
    // The opener can be gone by now (a closed panel, a replaced list).
    if (restoreTo?.isConnected) restoreTo.focus();
    restoreTo = null;
  }

  onMounted(() => {
    document.addEventListener("keydown", onKeydown);
    if (isOpen.value) void activate();
  });

  onUnmounted(() => {
    document.removeEventListener("keydown", onKeydown);
    if (isOpen.value) deactivate();
  });

  if (typeof open !== "boolean") {
    watch(open, (value) => {
      if (value) void activate();
      else deactivate();
    });
  }
}
