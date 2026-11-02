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
      <div class="audience" role="radiogroup" aria-label="Sign in as">
        <button type="button" role="radio" :aria-checked="audience === 'household'" :class="{ active: audience === 'household' }" @click="choose('household')">Household</button>
        <button type="button" role="radio" :aria-checked="audience === 'admin'" :class="{ active: audience === 'admin' }" @click="choose('admin')">Administrator</button>
      </div>

      <template v-if="audience === 'household'">
        <h1>{{ mode === "login" ? "Welcome back" : "Create your MealCraft account" }}</h1>
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

      <p v-if="notAdmin" class="auth-error" role="alert">
        {{ actor?.user.display_name }} is signed in, but this account is not an administrator. Switch to Household to open your week, or sign out and use an administrator account.
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
        <p v-if="errorMessage" class="auth-error" role="alert">{{ errorMessage }}</p>
        <button class="auth-submit" type="submit" :disabled="isLoading">
          {{ isLoading ? "Please wait…" : mode === "register" ? "Create account" : audience === "admin" ? "Sign in to the console" : "Sign in" }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
/* One white card on the tinted page: a segmented audience switch, plain fields, a dark pill to sign in. */
.auth-page { display: grid; place-items: start center; padding-block: 56px 0; }
.auth-card { width: min(440px, 100%); padding: 28px 32px 32px; border: 1px solid #ececef; border-radius: 16px; background: #fff; box-shadow: var(--mc-shadow-md); }
.auth-card h1 { margin: 0 0 6px; color: var(--mc-strong); font-size: 24px; line-height: 30px; font-weight: 600; letter-spacing: -0.02em; }
.auth-card > p { margin: 0; color: #71717a; font-size: 14px; line-height: 20px; }
.audience { display: grid; grid-template-columns: 1fr 1fr; gap: 2px; margin-bottom: 24px; padding: 3px; border-radius: 10px; background: #f4f4f5; }
.audience button { height: 30px; padding: 0 12px; border: 0; border-radius: 8px; background: transparent; color: #71717a; font-size: 13px; font-weight: 500; cursor: pointer; }
.audience button.active { background: #fff; color: var(--mc-strong); box-shadow: var(--mc-shadow-xs); }
.auth-tabs { display: grid; grid-template-columns: 1fr 1fr; margin: 20px 0; border-bottom: 1px solid #f0f0f2; }
.auth-tabs button { height: 40px; border: 0; background: transparent; color: #71717a; font-size: 14px; font-weight: 500; cursor: pointer; }
.auth-tabs button.active { box-shadow: inset 0 -2px 0 #18181b; color: var(--mc-strong); }
.auth-spacer { height: 20px; }
form { display: grid; gap: 16px; }
label, .field { display: grid; gap: 6px; color: #3f3f46; font-size: 13px; font-weight: 500; }
.field-head { display: flex; justify-content: space-between; align-items: baseline; }
.switch { padding: 0; border: 0; background: none; color: #6d28d9; font: inherit; font-weight: 500; cursor: pointer; }
.switch:hover { text-decoration: underline; }
input { width: 100%; height: 40px; padding: 0 12px; border: 1px solid #e4e4e7; border-radius: 10px; background: #fff; color: #18181b; font: inherit; font-size: 14px; font-weight: 400; box-shadow: var(--mc-shadow-xs); transition: border-color 150ms, box-shadow 150ms; }
input:focus { outline: none; border-color: #8b5cf6; box-shadow: 0 0 0 3px #ede9fe; }
.auth-submit { height: 40px; margin-top: 4px; border: 0; border-radius: 999px; background: #18181b; color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.08); }
.auth-submit:hover:not(:disabled) { background: #27272a; }
.auth-submit:disabled { opacity: 0.6; cursor: wait; }
.auth-error { margin: 16px 0 0; color: #b42318 !important; font-size: 13px; line-height: 1.5; }
form .auth-error { margin: 0; }
</style>
