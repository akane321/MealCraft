<script setup lang="ts">
// The one loading mark in the product: three dots that swell in turn, violet to terracotta. `lg` waits for a reply,
// `sm` sits inline (buttons, loading lines, notes); inside a button the dots take the button's text colour.
// Adapted from SpinKit's "Flow" — https://github.com/tobiasahlin/SpinKit — MIT License, Copyright (c) 2015 Tobias Ahlin.
withDefaults(defineProps<{ size?: "sm" | "lg" }>(), { size: "sm" });
</script>

<template>
  <span class="mc-loader" :class="size" aria-hidden="true"><i /><i /><i /></span>
</template>

<style>
.mc-loader { --l1: #7c3aed; --l2: #a78bfa; --l3: #e8775a; --dot: 5px; flex: none; display: inline-flex; align-items: center; justify-content: center; gap: calc(var(--dot) * 0.55); width: calc(var(--dot) * 4.4); height: calc(var(--dot) * 2.8); }
.mc-loader.lg { --dot: 10px; width: 40px; height: 40px; gap: 4px; }
.mc-loader i { width: var(--dot); height: var(--dot); flex: none; border-radius: 50%; background: var(--l1); animation: mc-flow 1.4s cubic-bezier(0.455, 0.03, 0.515, 0.955) infinite both; }
.mc-loader i:nth-child(1) { animation-delay: -0.3s; }
.mc-loader i:nth-child(2) { background: var(--l2); animation-delay: -0.15s; }
.mc-loader i:nth-child(3) { background: var(--l3); }
/* Inside a button (an ink, violet or red pill) the dots are the label's colour. */
:is(button, .mc-btn) .mc-loader { --l1: currentColor; --l2: currentColor; --l3: currentColor; }
@keyframes mc-flow { 0%, 80%, 100% { transform: scale(0.4); opacity: 0.55; } 40% { transform: scale(1); opacity: 1; } }
@keyframes mc-flow-still { 0%, 80%, 100% { opacity: 0.35; } 40% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .mc-loader i { animation-name: mc-flow-still; } }
</style>
