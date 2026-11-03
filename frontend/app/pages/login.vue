<script setup lang="ts">
import { isConsoleAccount } from "~/lib/ops";

useHead({ title: "Sign in · MealCraft" });

const route = useRoute();
// ADR-0047: one form for both; administrators are fixed accounts, so they only ever sign in.
const audience = ref<"household" | "admin">(route.query.as === "admin" ? "admin" : "household");
const mode = ref<"login" | "register">("login");
const email = ref("");
const username = ref("");
// Sign in with a username by default; email is the other way in (2026-10-12, owner).
const signInWith = ref<"username" | "email">("username");
const password = ref("");
const displayName = ref("");
const { actor, authenticate, errorMessage, isLoading, logout } = useAuth();
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
  const payload: Record<string, string> = { password: password.value };
  if (mode.value === "register") Object.assign(payload, { display_name: displayName.value, username: username.value, email: email.value });
  else if (signInWith.value === "username") payload.username = username.value;
  else payload.email = email.value;
  await authenticate(mode.value, payload);
}
</script>

<template>
  <main class="page-width main-content auth-page">
    <section class="auth-card">
      <NuxtLink to="/" class="auth-brand"><ShellMark />MealCraft</NuxtLink>
      <div class="audience" role="radiogroup" aria-label="Sign in as">
        <button type="button" role="radio" :aria-checked="audience === 'household'" :class="{ active: audience === 'household' }" @click="choose('household')">Household</button>
        <button type="button" role="radio" :aria-checked="audience === 'admin'" :class="{ active: audience === 'admin' }" @click="choose('admin')">Administrator</button>
      </div>

      <template v-if="audience === 'household'">
        <h1 :class="{ long: mode === 'register' }">{{ mode === "login" ? "Welcome back" : "Create your MealCraft account" }}</h1>
        <p>Your plans, household profile and Assistant history stay inside your household.</p>

        <div class="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">Sign in</button>
          <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">Register</button>
        </div>
      </template>
      <template v-else>
        <h1>Administrator sign in</h1>
        <p>Administrator accounts are set up by the team. Sign in to watch runs, check services and debug plans.</p>
        <div class="auth-spacer" />
      </template>

      <p v-if="notAdmin" class="auth-error mc-alert" role="alert">
        <UIcon name="i-lucide-circle-alert" aria-hidden="true" />
        <span>
          {{ actor?.user.display_name }} is signed in, but this account is not an administrator. Switch to Household to open your week, or sign out and use an administrator account.
          <button type="button" class="sign-out" @click="logout">Sign out</button>
        </span>
      </p>

      <form @submit.prevent="submit">
        <label v-if="mode === 'register'">
          Display name
          <input v-model="displayName" autocomplete="name" maxlength="120" required>
        </label>
        <div v-if="mode === 'register' || signInWith === 'username'" class="field">
          <span class="field-head">
            <label for="sign-in-username">Username</label>
            <button v-if="mode === 'login'" type="button" class="switch" @click="signInWith = 'email'">Use email instead</button>
          </span>
          <input id="sign-in-username" v-model="username" autocomplete="username" maxlength="32" required>
        </div>
        <div v-if="mode === 'register' || signInWith === 'email'" class="field">
          <span class="field-head">
            <label for="sign-in-email">Email</label>
            <button v-if="mode === 'login'" type="button" class="switch" @click="signInWith = 'username'">Use username instead</button>
          </span>
          <input id="sign-in-email" v-model="email" :autocomplete="mode === 'login' ? 'username' : 'email'" type="email" maxlength="320" required>
        </div>
        <label>
          Password
          <input v-model="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" type="password" required>
        </label>
        <p v-if="errorMessage" class="auth-error mc-alert" role="alert"><UIcon name="i-lucide-circle-alert" aria-hidden="true" />{{ errorMessage }}</p>
        <button class="auth-submit" type="submit" :disabled="isLoading" :aria-busy="isLoading || undefined">
          <UIcon v-if="isLoading" name="i-lucide-loader-circle" class="mc-spin" aria-hidden="true" />
          {{ isLoading ? "Please wait…" : mode === "register" ? "Create account" : audience === "admin" ? "Sign in to the console" : "Sign in" }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
/* One white card, centred on the tinted page: a quiet audience switch, plain fields, a dark pill to sign in. */
.auth-page { min-height: calc(100vh - 24px); display: grid; place-items: center; padding-block: 16px; }
.auth-card { width: min(420px, 100%); padding: 28px 32px; border: 1px solid #ececef; border-radius: 20px; background: #fff; box-shadow: var(--mc-shadow-md); }
/* The brand tile and wordmark head the card. */
.auth-brand { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 16px; color: var(--mc-strong); font-size: 17px; line-height: 24px; font-weight: 600; letter-spacing: -0.01em; text-decoration: none; }
.auth-brand .sb-mark { width: 40px; height: 40px; border-radius: 11px; }
.auth-brand .sb-mark :deep(svg) { width: 24px; height: 27px; }
.auth-card h1 { margin: 0 0 6px; text-align: center; color: var(--mc-strong); font-size: 24px; line-height: 30px; font-weight: 600; letter-spacing: -0.02em; }
.auth-card h1.long { font-size: 20px; }
.auth-card > p { margin: 0; text-align: center; color: #71717a; font-size: 14px; line-height: 20px; }
/* The audience is a quiet text switch (an underline marks the choice); Sign in / Register is the one segmented control. */
.audience { display: flex; justify-content: center; gap: 20px; margin: 0 0 18px; }
.audience button { height: 28px; padding: 0 2px; border: 0; background: transparent; color: #71717a; font-size: 13px; font-weight: 500; cursor: pointer; }
.audience button:hover { color: #27272a; }
.audience button.active { color: var(--mc-strong); box-shadow: inset 0 -2px 0 #18181b; }
.auth-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 2px; margin: 18px 0; padding: 3px; border-radius: 10px; background: #f4f4f5; }
.auth-tabs button { height: 32px; padding: 0 12px; border: 0; border-radius: 8px; background: transparent; color: #52525b; font-size: 13px; font-weight: 500; cursor: pointer; }
.auth-tabs button.active { background: #fff; color: var(--mc-strong); box-shadow: var(--mc-shadow-xs); }
.auth-spacer { height: 18px; }
form { display: grid; gap: 14px; }
label, .field { display: grid; gap: 6px; color: #3f3f46; font-size: 13px; font-weight: 500; }
.field-head { display: flex; justify-content: space-between; align-items: baseline; }
.switch { padding: 0; border: 0; background: none; color: #6d28d9; font: inherit; font-weight: 500; cursor: pointer; }
.switch:hover { text-decoration: underline; }
input { width: 100%; height: 40px; padding: 0 12px; border: 1px solid #e4e4e7; border-radius: 10px; background: #fff; color: #18181b; font: inherit; font-size: 14px; font-weight: 400; box-shadow: var(--mc-shadow-xs); transition: border-color 150ms, box-shadow 150ms; }
input:focus { outline: none; border-color: #8b5cf6; box-shadow: 0 0 0 3px #ede9fe; }
.auth-submit { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 40px; margin-top: 4px; border: 0; border-radius: 999px; background: #18181b; color: #fff; font-size: 14px; font-weight: 500; cursor: pointer; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.08); }
.auth-submit:hover:not(:disabled) { background: #27272a; }
/* In flight: the same ink pill with a spinner, never the disabled grey. */
.auth-submit:disabled { cursor: progress; }
.auth-error { margin: 4px 0 16px; color: #b42318 !important; }
/* Above the form: left-aligned beside its icon (the card centres its other lines), with room before the fields. */
.auth-card > .auth-error { margin: 16px 0 18px; text-align: left; }
form .auth-error { margin: 0; }
.sign-out { display: block; margin-top: 8px; padding: 0; border: 0; background: none; color: #b42318; font: inherit; font-weight: 600; text-decoration: underline; cursor: pointer; }
</style>
