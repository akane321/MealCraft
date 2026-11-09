<script lang="ts">
// Counts across the home page and the workspace, which each mount their own microphone.
let demoIndex = 0;
</script>

<script setup lang="ts">
import { DEMO_SENTENCES } from "~/lib/demo-script";
import { revealTokens } from "~/lib/reveal";

// The microphone beside a message box (ADR-0116). A tap records, a tap (or about 3 s of quiet) stops; the clip goes
// to POST /api/voice/transcriptions and the words come back into the box with `text`, never sent by themselves.
defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{ start: []; text: [value: string, final: boolean] }>();

const OK_KEY = "mealcraft-mic-ok";
const LOUD = 0.12;
const SILENCE_MS = 3000;
const MAX_MS = 60_000;

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const demo = Boolean(config.public.demoScript);
const supported = ref(false);
const phase = ref<"idle" | "ask" | "recording" | "transcribing">("idle");
const level = ref(0);
// The level bars while recording: five bands of the voice's frequencies, 0 to 1, the strongest drawn in the middle.
const bars = ref([0, 0, 0, 0, 0]);
const BANDS = [[18, 32], [5, 10], [2, 5], [10, 18], [32, 64]] as const;
const elapsed = ref(0);
const error = ref<string | null>(null);

let stream: MediaStream | null = null;
let audio: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
let recorder: MediaRecorder | null = null;
let chunks: Blob[] = [];
let frame = 0;
let startedAt = 0;
let lastLoud = 0;
let heard = false;
let cancelled = false;
let demoWords: string[] = [];
let demoShown = 0;
let demoNextAt = 0;
let errorTimer: ReturnType<typeof setTimeout> | undefined;

const time = computed(() => `${Math.floor(elapsed.value / 60)}:${String(elapsed.value % 60).padStart(2, "0")}`);

function fail(message: string) {
  error.value = message;
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => { error.value = null; }, 7000);
}

function press() {
  if (phase.value === "recording") return stop();
  if (phase.value !== "idle") return;
  let ok = false;
  try { ok = localStorage.getItem(OK_KEY) === "1"; }
  catch { /* storage blocked: ask each time */ }
  if (ok) void start();
  else phase.value = "ask";
}

function allow() {
  try { localStorage.setItem(OK_KEY, "1"); }
  catch { /* ignore */ }
  void start();
}

async function start() {
  error.value = null;
  emit("start");
  // Created and resumed inside the tap, or iPhone keeps the level ring still.
  audio = new AudioContext();
  void audio.resume();
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  }
  catch (reason) {
    cleanup();
    phase.value = "idle";
    fail((reason as DOMException).name === "NotAllowedError"
      ? "Microphone blocked. Allow it for this site (iPhone: Settings › Safari › Microphone; Android: Chrome › Site settings › Microphone), or type instead."
      : "Couldn't open the microphone. You can type instead.");
    return;
  }
  analyser = audio.createAnalyser();
  analyser.fftSize = 1024;
  audio.createMediaStreamSource(stream).connect(analyser);
  if (demo) {
    demoWords = revealTokens(DEMO_SENTENCES[demoIndex % DEMO_SENTENCES.length]!);
    demoShown = 0;
    demoNextAt = 0;
  }
  else {
    const mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find(type => MediaRecorder.isTypeSupported(type));
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunks = [];
    recorder.ondataavailable = event => chunks.push(event.data);
    recorder.onstop = upload;
    // The whole clip at once: iPhone's timesliced pieces often do not decode when joined.
    recorder.start();
  }
  cancelled = false;
  heard = false;
  startedAt = lastLoud = performance.now();
  phase.value = "recording";
  frame = requestAnimationFrame(tick);
}

function tick(now: number) {
  if (!analyser || phase.value !== "recording") return;
  const samples = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(samples);
  let sum = 0;
  for (const sample of samples) sum += ((sample - 128) / 128) ** 2;
  level.value = Math.min(1, Math.sqrt(sum / samples.length) * 5);
  const spectrum = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(spectrum);
  bars.value = BANDS.map(([from, to]) => {
    let total = 0;
    for (let bin = from; bin < to; bin++) total += spectrum[bin]!;
    return Math.min(1, (total / (to - from) / 255) * 1.5);
  });
  elapsed.value = Math.floor((now - startedAt) / 1000);
  const loud = level.value > LOUD;
  if (loud) {
    lastLoud = now;
    heard = true;
  }
  if (demo) {
    // One more word (a space counts with the word after it) every ~160 ms while there is sound.
    if (loud && now >= demoNextAt) {
      do demoShown++;
      while (demoShown < demoWords.length && !demoWords[demoShown - 1]!.trim());
      demoNextAt = now + 160;
      emit("text", demoWords.slice(0, demoShown).join(""), false);
      if (demoShown >= demoWords.length) return stop();
    }
  }
  else if (now - lastLoud > SILENCE_MS || now - startedAt > MAX_MS) {
    return stop();
  }
  frame = requestAnimationFrame(tick);
}

function stop() {
  if (phase.value !== "recording") return;
  if (demo) {
    emit("text", demoWords.join(""), true);
    demoIndex++;
    cleanup();
    phase.value = "idle";
    return;
  }
  phase.value = "transcribing";
  cancelAnimationFrame(frame);
  level.value = 0;
  // A short tail, so the last word is not cut.
  setTimeout(() => recorder?.state === "recording" && recorder.stop(), 300);
}

function cancel() {
  cancelled = true;
  if (demo && phase.value === "recording") emit("text", "", true);
  if (recorder?.state === "recording") recorder.stop();
  cleanup();
  phase.value = "idle";
}

async function upload() {
  const clip = new Blob(chunks, { type: recorder?.mimeType || "audio/webm" });
  cleanup();
  if (cancelled) return;
  if (!heard) {
    phase.value = "idle";
    return fail("Didn't hear anything. Try again, or type instead.");
  }
  try {
    const result = await apiFetch<{ text: string }>(`${config.public.apiBase}/api/voice/transcriptions`, {
      method: "POST",
      body: clip,
      headers: { "Content-Type": clip.type },
    });
    if (!cancelled && result.text.trim()) emit("text", result.text.trim(), true);
    else if (!cancelled) fail("Didn't catch any words. Try again, or type instead.");
  }
  catch (reason) {
    const detail = (reason as { data?: { detail?: string } }).data?.detail;
    if (!cancelled) fail(`${detail || "Couldn't turn that into text."} What you typed is kept.`);
  }
  finally {
    phase.value = "idle";
  }
}

function cleanup() {
  cancelAnimationFrame(frame);
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  void audio?.close().catch(() => {});
  audio = null;
  analyser = null;
  level.value = 0;
  bars.value = [0, 0, 0, 0, 0];
  elapsed.value = 0;
}

function onHidden() {
  if (document.hidden && phase.value === "recording") {
    cancel();
    fail("Recording stopped when you left the page.");
  }
}

onMounted(() => {
  supported.value = window.isSecureContext && Boolean(navigator.mediaDevices?.getUserMedia) && "MediaRecorder" in window;
  document.addEventListener("visibilitychange", onHidden);
});
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", onHidden);
  if (phase.value !== "idle") cancel();
});
</script>

<template>
  <div v-if="supported" class="voice">
    <button
      type="button"
      class="mic"
      :class="{ on: phase === 'recording' }"
      :style="{ '--lvl': level }"
      :aria-label="phase === 'recording' ? 'Stop recording' : 'Speak your request'"
      :aria-pressed="phase === 'recording'"
      :disabled="disabled || phase === 'transcribing'"
      @click="press"
    >
      <UIcon :name="phase === 'recording' ? 'i-lucide-square' : 'i-lucide-mic'" aria-hidden="true" />
    </button>

    <div v-if="phase === 'recording' || phase === 'transcribing'" class="float rec" role="status">
      <!-- Recording: level bars that follow the voice; turning it into text: the loader. -->
      <span class="ring" :style="{ '--lvl': level }" aria-hidden="true">
        <span v-if="phase === 'recording'" class="wave"><i v-for="(height, bar) in bars" :key="bar" :style="{ '--h': height }" /></span>
        <MotionLoader v-else class="ring-loader" />
      </span>
      <template v-if="phase === 'recording'">
        <b class="time">{{ time }}</b><span class="hint">Listening…</span>
        <button type="button" class="rec-btn stop" @click="stop">Done</button>
      </template>
      <span v-else class="hint">Turning your words into text…</span>
      <button type="button" class="rec-btn x" aria-label="Cancel recording" @click="cancel"><UIcon name="i-lucide-x" aria-hidden="true" /></button>
    </div>

    <div v-else-if="phase === 'ask'" class="float ask-card" role="dialog" aria-label="Use the microphone">
      <span class="ring"><UIcon name="i-lucide-mic" aria-hidden="true" /></span>
      <div>
        <b>Speak instead of typing</b>
        <p>MealCraft needs your microphone. Your clip is sent to OpenAI to turn it into text; MealCraft doesn't keep it. The words land in the box for you to check before sending.</p>
        <div class="ask-acts">
          <button type="button" class="rec-btn" @click="phase = 'idle'">Not now</button>
          <button type="button" class="rec-btn stop" @click="allow">Allow microphone</button>
        </div>
      </div>
    </div>

    <p v-else-if="error" class="float mic-error" role="alert">{{ error }}<button type="button" class="rec-btn x" aria-label="Dismiss" @click="error = null"><UIcon name="i-lucide-x" aria-hidden="true" /></button></p>
  </div>
</template>

<style scoped>
.voice { display: contents; }
.mic { width: 32px; height: 32px; flex: none; display: grid; place-items: center; padding: 0; border: 1px solid #e4e4e7; border-radius: 999px; background: #fff; color: #3f3f46; box-shadow: 0 0 0 calc(var(--lvl, 0) * 10px) rgba(124, 58, 237, 0.18); transition: box-shadow 80ms linear, background 150ms; }
.mic:hover:not(:disabled) { background: #f7f7f8; }
.mic.on { border-color: #7c3aed; background: #7c3aed; color: #fff; }
.mic .iconify { width: 16px; height: 16px; }
.float { position: absolute; z-index: 6; left: 0; right: 0; bottom: calc(100% + 10px); margin: 0 auto; width: fit-content; max-width: 100%; display: flex; align-items: center; gap: 10px; padding: 8px 8px 8px 10px; border: 1px solid #ececef; border-radius: 999px; background: rgba(255, 255, 255, 0.96); color: #27272a; font: 500 13px/18px var(--font-sans, Inter, system-ui, sans-serif); text-align: left; text-shadow: none; box-shadow: 0 1px 2px rgba(16, 16, 20, 0.05), 0 12px 32px -12px rgba(16, 16, 20, 0.22); backdrop-filter: blur(10px); animation: mc-rise 240ms cubic-bezier(0.22, 1, 0.36, 1) both; }
.ring { width: 32px; height: 32px; flex: none; display: grid; place-items: center; border-radius: 999px; background: #7c3aed; color: #fff; box-shadow: 0 0 0 calc(4px + var(--lvl, 0) * 14px) rgba(124, 58, 237, 0.18); transition: box-shadow 80ms linear; }
.ring .iconify { width: 16px; height: 16px; }
/* Five bars, one per band of the voice's frequencies (the strongest bands in the middle). */
.wave { display: flex; align-items: center; gap: 2.5px; height: 18px; }
.wave i { width: 3px; height: 18px; border-radius: 3px; background: #fff; transform: scaleY(calc(0.18 + var(--h, 0) * 0.82)); transition: transform 70ms linear; }
.ring-loader { --l1: #fff; --l2: #fff; --l3: #fff; --dot: 4px; }
@media (prefers-reduced-motion: reduce) { .wave i { transition: none; } }
.time { font-variant-numeric: tabular-nums; color: #18181b; font-weight: 600; }
.hint { color: #52525b; white-space: nowrap; }
.rec-btn { height: 32px; flex: none; display: inline-grid; place-items: center; padding: 0 12px; border: 1px solid #e4e4e7; border-radius: 999px; background: #fff; color: #27272a; font: 500 13px/1 var(--font-sans, Inter, system-ui, sans-serif); }
.rec-btn.stop { border-color: #18181b; background: #18181b; color: #fff; }
.rec-btn.x { width: 32px; padding: 0; border-color: transparent; background: transparent; color: #71717a; }
.rec-btn .iconify { width: 16px; height: 16px; }
.ask-card { align-items: flex-start; width: min(420px, 100%); padding: 14px; border-radius: 16px; }
.ask-card b { display: block; color: #18181b; font-weight: 600; }
.ask-card p { margin: 4px 0 10px; color: #52525b; font-size: 13px; line-height: 19px; font-weight: 400; }
.ask-acts { display: flex; justify-content: flex-end; gap: 8px; }
.mic-error { max-width: min(520px, 100%); border-color: #fecdca; border-radius: 14px; background: #fef3f2; color: #b42318; padding-left: 14px; }
@media (max-width: 767px) {
  .mic, .rec-btn, .ring { width: 44px; height: 44px; }
  .rec-btn:not(.x) { width: auto; }
  .hint { white-space: normal; }
}
</style>
