<script setup lang="ts">
// A small living orb in the brand colours: Paper Shaders' mesh gradient (WebGL), loaded on the client only after
// mounting. Until it is up, or where WebGL is missing, a CSS gradient shows; reduced motion keeps it still.
// The shader pauses itself while the orb is off screen or the tab hidden.
const props = withDefaults(defineProps<{ size?: number; speed?: number }>(), { size: 28, speed: 0.7 });
const COLORS = ["#7c3aed", "#f0a183", "#c4b5fd", "#fff1e8", "#e8775a", "#6d28d9"];

const host = ref<HTMLElement | null>(null);
const live = ref(false);
let mount: { dispose: () => void } | null = null;
let gone = false;

onMounted(async () => {
  try {
    const shaders = await import("@paper-design/shaders");
    if (gone || !host.value) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const colors = COLORS.map(color => shaders.getShaderColorFromString(color));
    const sizing = shaders.defaultObjectSizing;
    mount = new shaders.ShaderMount(host.value, shaders.meshGradientFragmentShader, {
      u_colors: colors,
      u_colorsCount: colors.length,
      u_distortion: 1,
      u_swirl: 0.8,
      u_grainMixer: 0,
      u_grainOverlay: 0,
      u_fit: shaders.ShaderFitOptions.cover,
      u_scale: 0.75,
      u_rotation: sizing.rotation,
      u_originX: sizing.originX,
      u_originY: sizing.originY,
      u_offsetX: sizing.offsetX,
      u_offsetY: sizing.offsetY,
      u_worldWidth: sizing.worldWidth,
      u_worldHeight: sizing.worldHeight,
    }, undefined, still ? 0 : props.speed, 2400);
    live.value = true;
  }
  catch { /* no WebGL: the CSS gradient stays */ }
});
onBeforeUnmount(() => {
  gone = true;
  mount?.dispose();
});
</script>

<template>
  <span ref="host" class="orb" :class="{ live }" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true" />
</template>

<style scoped>
.orb { position: relative; display: block; flex: none; overflow: hidden; border-radius: 50%; isolation: isolate;
  background: radial-gradient(circle at 30% 28%, #fbd3bd 0, transparent 46%), radial-gradient(circle at 72% 70%, #e8775a 0, transparent 52%), conic-gradient(from 200deg, #6d28d9, #a78bfa, #8b5cf6, #6d28d9);
  animation: orb-turn 4s linear infinite; }
.orb.live { animation: none; }
.orb :deep(canvas) { position: absolute; inset: 0; width: 100% !important; height: 100% !important; opacity: 0; animation: orb-in 500ms ease-out forwards; }
@keyframes orb-turn { to { filter: hue-rotate(-18deg); transform: rotate(360deg); } }
@keyframes orb-in { to { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .orb { animation: none; } }
</style>
