<script setup lang="ts">
import { animate } from "motion-v";

// The success moment of a confirm (about 1.5 s; a click skips it): the pressed button grows on a spring into a card
// over the chat; its ring closes into the plate, the plate fills, a check draws, the leaf grows, with a soft burst,
// sparks and brand confetti; the words rise; then the card folds back onto the chat's stamp. Reduced motion: a fade.
const props = defineProps<{ title: string; detail: string; from: DOMRect | null }>();
const emit = defineEmits<{ collapse: []; done: [] }>();

type Box = { l: number; t: number; w: number; h: number; r: number };
const root = ref<HTMLElement | null>(null);
const morph = ref<HTMLElement | null>(null);
const open = ref(false);
const out = ref(false);
const skipped = ref(false);
const still = ref(false);
const card = ref<Box>({ l: 0, t: 0, w: 320, h: 236, r: 28 });
const SPARKS = Array.from({ length: 10 }, (_, i) => i * 36);

let size = { w: 0, h: 0 };
let now: Box = card.value;
let running: { stop: () => void } | null = null;
let wake: (() => void) | null = null;

function clip(box: Box) {
  now = box;
  if (morph.value) morph.value.style.clipPath = `inset(${box.t}px ${size.w - box.l - box.w}px ${size.h - box.t - box.h}px ${box.l}px round ${Math.max(0, box.r)}px)`;
}
/** Springs the card's outline from where it is to `to`. */
function morphTo(to: Box, spring: { stiffness: number; damping: number }) {
  running?.stop();
  const from = now;
  const mix = (a: number, b: number, p: number) => a + (b - a) * p;
  const controls = animate(0, 1, {
    type: "spring", ...spring, restDelta: 0.001,
    onUpdate: p => clip({ l: mix(from.l, to.l, p), t: mix(from.t, to.t, p), w: mix(from.w, to.w, p), h: mix(from.h, to.h, p), r: mix(from.r, to.r, p) }),
  });
  running = controls;
  return controls;
}
/** Waits `ms`, or less when the household clicks to skip. */
function hold(ms: number) {
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    wake = () => { clearTimeout(timer); resolve(); };
  });
}
function skip() {
  if (skipped.value || out.value) return;
  skipped.value = true;
  wake?.();
}

async function burst() {
  if (skipped.value || !root.value) return;
  const confetti = (await import("canvas-confetti")).default;
  const box = root.value.getBoundingClientRect();
  confetti({
    particleCount: 90, spread: 360, startVelocity: 26, decay: 0.9, gravity: 0.75, ticks: 150, scalar: 0.8,
    origin: { x: (box.left + card.value.l + card.value.w / 2) / window.innerWidth, y: (box.top + card.value.t + 70) / window.innerHeight },
    colors: ["#6d28d9", "#8b5cf6", "#c4b5fd", "#e8775a", "#f4a582", "#fcd9c5"],
    shapes: ["circle", "square"], zIndex: 40, disableForReducedMotion: true,
  });
}

onMounted(async () => {
  const el = root.value!;
  const box = el.getBoundingClientRect();
  size = { w: box.width, h: box.height };
  const w = Math.min(320, size.w - 32);
  const h = 236;
  card.value = { l: (size.w - w) / 2, t: Math.max(16, (size.h - h) / 2 - 24), w, h, r: 28 };
  still.value = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const f = props.from;
  const start: Box = f && !still.value
    ? { l: f.left - box.left, t: f.top - box.top, w: f.width, h: f.height, r: f.height / 2 }
    : { ...card.value };
  clip(start);
  requestAnimationFrame(() => { open.value = true; });
  if (!still.value) {
    morphTo(card.value, { stiffness: 210, damping: 21 });
    setTimeout(() => void burst(), 560);
  }
  await hold(still.value ? 1100 : 1300);

  // Fold onto the stamp, which the page lays out (still hidden) when told.
  out.value = true;
  emit("collapse");
  await nextTick();
  const stamp = el.parentElement?.querySelector<HTMLElement>("[data-stamp]")?.getBoundingClientRect();
  if (stamp && !still.value) {
    await morphTo({ l: stamp.left - box.left, t: stamp.top - box.top, w: stamp.width, h: stamp.height, r: stamp.height / 2 }, { stiffness: 380, damping: 34 });
  }
  else await new Promise(resolve => setTimeout(resolve, 260));
  emit("done");
});
onBeforeUnmount(() => running?.stop());
</script>

<template>
  <div ref="root" class="success" :class="{ open, out, skipped, still }" role="presentation" @click="skip">
    <div class="veil" />
    <div class="lift">
      <div ref="morph" class="morph" />
    </div>
    <div class="content" :style="{ left: `${card.l}px`, top: `${card.t}px`, width: `${card.w}px`, height: `${card.h}px` }">
      <span class="wash" aria-hidden="true" />
      <div class="stage" aria-hidden="true">
        <span class="halo" />
        <span class="wave" />
        <span class="sparks"><i v-for="angle in SPARKS" :key="angle" :style="{ '--a': `${angle}deg` }" /></span>
        <MotionOrb class="plate" :size="58" :speed="1.4" />
        <svg viewBox="0 0 36 36">
          <circle class="rim" cx="18" cy="18" r="12.5" pathLength="100" transform="rotate(-90 18 18)" />
          <path class="check" d="M12.4 18.5l3.7 3.7 7-7.4" pathLength="100" />
          <path class="sprout" d="M17.2 5.6c1-4.6 5.4-6.6 9.4-5.6-.9 4.2-5 6.9-9.4 5.6z" />
        </svg>
      </div>
      <p class="title">{{ title }}</p>
      <p v-if="detail" class="detail">{{ detail }}</p>
    </div>
  </div>
</template>

<style scoped>
.success { position: absolute; inset: 0; z-index: 25; cursor: pointer; overflow: hidden; }
.veil { position: absolute; inset: 0; background: radial-gradient(60% 50% at 50% 42%, rgba(237, 233, 254, 0.75), rgba(255, 255, 255, 0.62)); backdrop-filter: blur(6px) saturate(1.3); opacity: 0; transition: opacity 280ms ease-out; }
.open .veil { opacity: 1; }
.out .veil { opacity: 0; transition-duration: 320ms; }
.lift { position: absolute; inset: 0; filter: drop-shadow(0 24px 40px rgba(24, 24, 27, 0.16)) drop-shadow(0 2px 6px rgba(24, 24, 27, 0.08)); }
.morph { position: absolute; inset: 0; background: #18181b; transition: background-color 260ms ease-out; }
.open .morph { background: #fff; }
.content { position: absolute; display: flex; flex-direction: column; align-items: center; padding-top: 22px; text-align: center; opacity: 0; transition: opacity 200ms ease-out 140ms, transform 200ms ease-out; }
.open .content { opacity: 1; }
.out .content { opacity: 0; transform: scale(0.92); transition: opacity 140ms ease-in, transform 160ms ease-in; }

/* A soft brand-coloured light at the top of the card. */
.wash { position: absolute; inset: 0; border-radius: 28px; background: radial-gradient(120% 70% at 50% 0%, rgba(196, 181, 253, 0.38), rgba(251, 211, 189, 0.18) 45%, transparent 75%); opacity: 0; transition: opacity 500ms ease-out 300ms; pointer-events: none; }
.open .wash { opacity: 1; }
.stage { position: relative; width: 96px; height: 96px; display: grid; place-items: center; }
.stage > * { grid-area: 1 / 1; }
.stage svg { width: 96px; height: 96px; overflow: visible; }
.halo { width: 120px; height: 120px; border-radius: 50%; background: radial-gradient(circle, rgba(139, 92, 246, 0.32), rgba(232, 119, 90, 0.16) 45%, transparent 70%); opacity: 0; transform: scale(0.5); }
.wave { width: 68px; height: 68px; border-radius: 50%; border: 2px solid rgba(139, 92, 246, 0.55); opacity: 0; }
.sparks { position: relative; width: 0; height: 0; }
.sparks i { position: absolute; left: -1.5px; top: -9px; width: 3px; height: 14px; border-radius: 3px; background: linear-gradient(#8b5cf6, #e8775a); opacity: 0; transform: rotate(var(--a)) translateY(-42px); }
.plate { opacity: 0; transform: scale(0.2); }
.rim { fill: none; stroke: #18181b; stroke-width: 2.6; stroke-linecap: round; stroke-dasharray: 100 100; stroke-dashoffset: 100; }
.check { fill: none; stroke: #fff; stroke-width: 2.8; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: 100 100; stroke-dashoffset: 100; filter: drop-shadow(0 0.4px 0.6px rgba(24, 24, 27, 0.35)); }
.sprout { fill: #e8775a; transform-origin: 17.2px 5.6px; transform: scale(0) rotate(-30deg); }
.title { margin: 14px 0 0; color: #18181b; font-size: 20px; line-height: 26px; font-weight: 600; letter-spacing: -0.01em; opacity: 0; }
.detail { margin: 4px 0 0; color: #71717a; font-size: 14px; line-height: 20px; font-weight: 500; opacity: 0; }

.open .rim { animation: draw 440ms cubic-bezier(0.65, 0, 0.35, 1) 180ms forwards; }
.open .plate { animation: pop 560ms var(--spring-pop) 520ms forwards; }
.open .halo { animation: halo 900ms ease-out 520ms forwards; }
.open .wave { animation: wave 760ms cubic-bezier(0.2, 0.7, 0.3, 1) 560ms forwards; }
.open .sparks i { animation: spark 560ms cubic-bezier(0.2, 0.7, 0.3, 1) 560ms forwards; }
.open .check { animation: draw 300ms ease-out 660ms forwards; }
.open .sprout { animation: sprout 640ms var(--spring-pop) 760ms forwards; }
.open .title { animation: rise 700ms var(--spring) 560ms forwards; }
.open .detail { animation: rise 700ms var(--spring) 660ms forwards; }
/* A click jumps to the end state before folding. */
.skipped :is(.rim, .plate, .halo, .check, .sprout, .title, .detail) { animation-delay: 0ms !important; animation-duration: 1ms !important; }
.skipped :is(.wave, .sparks i) { animation: none !important; }
.still :is(.rim, .plate, .halo, .check, .sprout, .title, .detail) { animation: none !important; opacity: 1; transform: none; stroke-dashoffset: 0; }
.still .halo { opacity: 0.6; }

@keyframes draw { to { stroke-dashoffset: 0; } }
@keyframes pop { to { opacity: 1; transform: none; } }
@keyframes halo { 40% { opacity: 1; transform: scale(1.15); } to { opacity: 0.55; transform: scale(1); } }
@keyframes wave { from { opacity: 0.9; transform: scale(1); } to { opacity: 0; transform: scale(2.3); } }
@keyframes spark { 0% { opacity: 1; transform: rotate(var(--a)) translateY(-40px) scaleY(1); } 100% { opacity: 0; transform: rotate(var(--a)) translateY(-70px) scaleY(0.2); } }
@keyframes sprout { to { transform: none; } }
@keyframes rise { from { opacity: 0; transform: translateY(10px); filter: blur(6px); } to { opacity: 1; transform: none; filter: none; } }
</style>
