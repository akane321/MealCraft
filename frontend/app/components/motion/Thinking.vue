<template>
  <!-- The MealCraft mark while a reply is on its way: the plate stays, the leaf circles it. -->
  <span class="think" aria-hidden="true">
    <svg viewBox="-1.5 0.5 35 35">
      <circle cx="16" cy="18" r="9.5" fill="none" stroke="#fff" stroke-width="2.6" />
      <path d="M15.2 9.2c1-4.6 5.4-6.6 9.4-5.6-.9 4.2-5 6.9-9.4 5.6z" fill="#e8775a">
        <animateTransform attributeName="transform" type="rotate" from="0 16 18" to="360 16 18" dur="1.8s" repeatCount="indefinite" />
      </path>
    </svg>
  </span>
</template>

<style scoped>
.think { width: 32px; height: 32px; flex: none; display: grid; place-items: center; border-radius: 9px; background: linear-gradient(135deg, #2a2a31, #0f0f12); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 1px 2px rgba(0, 0, 0, 0.2); }
.think svg { width: 26px; height: 26px; }
</style>
