<script setup lang="ts">
useHead({ title: "Sign in · MealCraft" });

const mode = ref<"login" | "register">("login");
const email = ref("");
const password = ref("");
const displayName = ref("");
const { actor, authenticate, errorMessage, isLoading } = useAuth();
const requested = useRoute().query.next;
// Only same-site paths, so a crafted link cannot bounce the user elsewhere.
const next = typeof requested === "string" && /^\/(?![/\\])/.test(requested) ? requested : "/profile";

watchEffect(() => {
  if (actor.value) navigateTo(next);
});

async function submit() {
  const payload: Record<string, string> = { email: email.value, password: password.value };
  if (mode.value === "register") payload.display_name = displayName.value;
  if (await authenticate(mode.value, payload)) await navigateTo(next);
}
</script>

<template>
  <main class="page-width main-content auth-page">
    <section class="auth-card">
      <p class="eyebrow">Private household workspace</p>
      <h1>{{ mode === "login" ? "Welcome back" : "Create your MealCraft account" }}</h1>
      <p>Your plans, household profile and Assistant history stay inside your household.</p>

      <div class="auth-tabs" role="tablist" aria-label="Authentication mode">
        <button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">Sign in</button>
        <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">Register</button>
      </div>

      <form @submit.prevent="submit">
        <label v-if="mode === 'register'">
          Display name
          <input v-model="displayName" autocomplete="name" maxlength="120" required>
        </label>
        <label>
          Email
          <input v-model="email" autocomplete="email" type="email" maxlength="320" required>
        </label>
        <label>
          Password
          <input v-model="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" type="password" minlength="12" required>
        </label>
        <p v-if="errorMessage" class="auth-error" role="alert">{{ errorMessage }}</p>
        <button class="auth-submit" type="submit" :disabled="isLoading">
          {{ isLoading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account" }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.auth-page { display: grid; place-items: start center; }
.auth-card { width: 520px; padding: 38px; border: 1px solid var(--border); border-radius: 12px; }
.auth-card h1 { margin: 6px 0 10px; font-size: 34px; }
.auth-card > p { color: var(--muted); line-height: 1.5; }
.eyebrow { margin: 0; color: var(--success) !important; font-weight: 700; }
.auth-tabs { display: grid; grid-template-columns: 1fr 1fr; margin: 28px 0 22px; border-bottom: 1px solid var(--border); }
.auth-tabs button { padding: 12px; border: 0; background: transparent; color: var(--muted); cursor: pointer; }
.auth-tabs button.active { border-bottom: 2px solid #17191c; color: #17191c; font-weight: 700; }
form { display: grid; gap: 18px; }
label { display: grid; gap: 8px; font-weight: 650; }
input { width: 100%; padding: 12px 14px; border: 1px solid var(--border); border-radius: 7px; font: inherit; }
.auth-submit { padding: 13px 18px; border: 0; border-radius: 7px; color: white; background: #17191c; font-weight: 700; cursor: pointer; }
.auth-submit:disabled { opacity: .6; cursor: wait; }
.auth-error { margin: 0; color: var(--danger) !important; }
</style>
