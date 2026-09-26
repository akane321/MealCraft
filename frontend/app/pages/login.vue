<script setup lang="ts">
import { isConsoleAccount } from "~/lib/ops";

useHead({ title: "Sign in · MealCraft" });

const route = useRoute();
// ADR-0047: one form for both; administrators are fixed accounts, so they only ever sign in.
const audience = ref<"household" | "admin">(route.query.as === "admin" ? "admin" : "household");
const mode = ref<"login" | "register">("login");
const email = ref("");
const password = ref("");
const displayName = ref("");
const { actor, authenticate, errorMessage, isLoading } = useAuth();
const requested = route.query.next;
// Only same-site paths, so a crafted link cannot bounce the user elsewhere.
const next = typeof requested === "string" && /^\/(?![/\\])/.test(requested) ? requested : "/";

const notAdmin = computed(() => audience.value === "admin" && actor.value !== null && !isConsoleAccount(actor.value));

watchEffect(() => {
  if (!actor.value) return;
  if (audience.value === "household") navigateTo(next);
  else if (isConsoleAccount(actor.value)) navigateTo("/ops");
});

function choose(value: "household" | "admin") {
  audience.value = value;
  mode.value = "login";
  errorMessage.value = null;
}

async function submit() {
  const payload: Record<string, string> = { email: email.value, password: password.value };
  if (mode.value === "register") payload.display_name = displayName.value;
  await authenticate(mode.value, payload);
}
</script>

<template>
  <main class="page-width main-content auth-page">
    <section class="auth-card">
      <div class="audience" role="radiogroup" aria-label="Sign in as">
        <button type="button" role="radio" :aria-checked="audience === 'household'" :class="{ active: audience === 'household' }" @click="choose('household')">Household</button>
        <button type="button" role="radio" :aria-checked="audience === 'admin'" :class="{ active: audience === 'admin' }" @click="choose('admin')">Administrator</button>
      </div>

      <template v-if="audience === 'household'">
        <p class="eyebrow">Private household workspace</p>
        <h1>{{ mode === "login" ? "Welcome back" : "Create your MealCraft account" }}</h1>
        <p>Your plans, household profile and Assistant history stay inside your household.</p>

        <div class="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">Sign in</button>
          <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">Register</button>
        </div>
      </template>
      <template v-else>
        <p class="eyebrow">Operations console</p>
        <h1>Administrator sign in</h1>
        <p>Administrator accounts are set up by the team. Sign in to watch runs, check services and debug plans.</p>
        <div class="auth-spacer" />
      </template>

      <p v-if="notAdmin" class="auth-error" role="alert">
        {{ actor?.user.display_name }} is signed in, but this account is not an administrator. Switch to Household to open your week, or sign out and use an administrator account.
      </p>

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
          <input v-model="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" type="password" :minlength="mode === 'register' ? 12 : undefined" required>
        </label>
        <p v-if="errorMessage" class="auth-error" role="alert">{{ errorMessage }}</p>
        <button class="auth-submit" type="submit" :disabled="isLoading">
          {{ isLoading ? "Please wait…" : mode === "register" ? "Create account" : audience === "admin" ? "Sign in to the console" : "Sign in" }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.auth-page { display: grid; place-items: start center; }
.auth-card { width: min(520px, 100%); padding: clamp(24px, 5vw, 38px); border: 1px solid var(--border); border-radius: 20px; background: var(--s1); }
.auth-card h1 { margin: 6px 0 10px; font-size: 34px; }
.auth-card > p { color: var(--muted); line-height: 1.5; }
.audience { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-bottom: 26px; padding: 4px; border: 1px solid var(--border); border-radius: 999px; background: var(--ink); }
.audience button { padding: 9px 12px; border: 0; border-radius: 999px; background: transparent; color: var(--muted); font-size: 13px; cursor: pointer; }
.audience button.active { background: var(--s3); color: var(--ivory); font-weight: 600; }
.eyebrow { margin: 0; color: var(--accent) !important; font-size: 10.5px; font-weight: 600; letter-spacing: 0.16em; }
.auth-tabs { display: grid; grid-template-columns: 1fr 1fr; margin: 28px 0 22px; border-bottom: 1px solid var(--border); }
.auth-tabs button { padding: 12px; border: 0; background: transparent; color: var(--muted); cursor: pointer; }
.auth-tabs button.active { box-shadow: inset 0 -2px 0 var(--accent); color: var(--ivory); font-weight: 600; }
.auth-spacer { height: 12px; }
form { display: grid; gap: 18px; }
label { display: grid; gap: 8px; color: var(--t2); font-size: 13px; font-weight: 500; }
input { width: 100%; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--s2); color: var(--ivory); font: inherit; }
input:focus { outline: none; border-color: var(--accent); }
.auth-submit { padding: 13px 18px; border: 0; border-radius: 999px; color: var(--ink); background: var(--ivory); font-weight: 600; cursor: pointer; }
.auth-submit:disabled { opacity: .6; cursor: wait; }
.auth-error { margin: 0 0 18px; color: var(--danger) !important; line-height: 1.5; }
form .auth-error { margin: 0; }
</style>
