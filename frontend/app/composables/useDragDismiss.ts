// Drag a phone sheet or drawer toward its edge to close it. `edge` is the direction that closes ("down" for a
// bottom sheet, "left" for a left drawer). While dragging, `offset` is how far it has followed the finger (px, in
// the closing direction; a pull the other way gives a little and stops) and `progress` runs 0..1 with it for the
// scrim. Let go past a third of its size, or with a flick, and `close` runs; otherwise it springs back (CSS).
// A gesture that starts across the drag axis is left to the page (scrolling), and a drag never ends in a click.
export function useDragDismiss(edge: "down" | "left", close: () => void) {
  const offset = ref(0);
  const dragging = ref(false);
  let size = 1;
  const progress = computed(() => Math.min(1, Math.max(0, offset.value / size)));
  let pointer: number | null = null;
  let startMain = 0;
  let startCross = 0;
  let lastMain = 0;
  let lastTime = 0;
  let speed = 0;

  const main = (event: PointerEvent) => (edge === "down" ? event.clientY : -event.clientX);
  const cross = (event: PointerEvent) => (edge === "down" ? event.clientX : event.clientY);

  function onPointerdown(event: PointerEvent) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    // The size that counts is the whole sheet's (marked data-dismiss), even when only its head takes the drag.
    const target = event.currentTarget as HTMLElement;
    const box = (target.closest("[data-dismiss]") ?? target).getBoundingClientRect();
    pointer = event.pointerId;
    startMain = lastMain = main(event);
    startCross = cross(event);
    lastTime = event.timeStamp;
    speed = 0;
    size = Math.max(1, edge === "down" ? box.height : box.width);
  }
  function onPointermove(event: PointerEvent) {
    if (event.pointerId !== pointer) return;
    const moved = main(event) - startMain;
    if (!dragging.value) {
      const across = Math.abs(cross(event) - startCross);
      if (Math.abs(moved) < 8 && across < 8) return;
      // Across the axis, or toward opening: not a dismiss.
      if (across > Math.abs(moved) || moved < 0) {
        pointer = null;
        return;
      }
      dragging.value = true;
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    }
    const now = event.timeStamp;
    if (now > lastTime) speed = (main(event) - lastMain) / (now - lastTime);
    lastMain = main(event);
    lastTime = now;
    offset.value = moved > 0 ? moved : moved / 4;
  }
  function onPointerup(event: PointerEvent) {
    if (event.pointerId !== pointer) return;
    pointer = null;
    if (!dragging.value) return;
    dragging.value = false;
    // The click that follows a drag would press whatever is under the finger.
    window.addEventListener("click", swallow, { capture: true, once: true });
    setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 80);
    if (offset.value > size / 3 || (speed > 0.5 && offset.value > 24)) close();
    else offset.value = 0;
  }
  function swallow(event: Event) {
    event.preventDefault();
    event.stopPropagation();
  }
  // A sheet opened again starts where it belongs.
  const reset = () => { offset.value = 0; };

  return { offset, dragging, progress, reset,
    // Keyed for v-on's object form.
    handlers: { pointerdown: onPointerdown, pointermove: onPointermove, pointerup: onPointerup, pointercancel: onPointerup } };
}
