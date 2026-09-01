<script setup lang="ts">
import { activeAgentPhase, formatOptionalNumber, formatPantryQuantity } from "~/lib/agent-format";

useHead({ title: "Planning assistant · MealCraft" });

const starterMessage = ref("");
const replyMessage = ref("");
const {
  confirm,
  create,
  errorMessage,
  generatedPlan,
  isLoading,
  reply,
  reset,
  restoreLatest,
  session,
} = useMealCraftAgent();

const activePhase = computed(() => activeAgentPhase(session.value?.status || null));
const preferences = computed(() => {
  if (!session.value) return [];
  return [
    ...session.value.constraints.dietary_preferences,
    ...session.value.constraints.health_preferences,
  ];
});
const nutritionTargets = computed(() => {
  if (!session.value) return [];
  const targets = session.value.constraints.nutrition_targets;
  return [
    targets.calories_kcal === null ? null : `${targets.calories_kcal} kcal`,
    targets.protein_g === null ? null : `${targets.protein_g} g protein`,
    targets.carbohydrate_g === null ? null : `${targets.carbohydrate_g} g carbohydrate`,
    targets.fat_g === null ? null : `${targets.fat_g} g fat`,
  ].filter((value): value is string => value !== null);
});

async function startSession() {
  const message = starterMessage.value.trim();
  if (!message) return;
  await create(message);
  if (session.value) starterMessage.value = "";
}

async function sendReply() {
  const message = replyMessage.value.trim();
  if (!message) return;
  await reply(message);
  if (!errorMessage.value) replyMessage.value = "";
}

onMounted(restoreLatest);
</script>

<template>
  <main class="page-width assistant-page">
    <section class="assistant-hero">
      <div>
        <p class="eyebrow">Persistent constraint-aware agent</p>
        <h1>Plan with MealCraft.</h1>
      </div>
      <p>
        Describe the week in ordinary language. The assistant extracts explicit constraints, asks only for missing information, and generates a plan after your confirmation.
      </p>
    </section>

    <ol class="assistant-progress" aria-label="Planning progress">
      <li v-for="(label, index) in ['Understanding request', 'Clarifying details', 'Ready to plan']" :key="label" :class="{ active: activePhase === index + 1, complete: activePhase > index + 1 }">
        <span>{{ index + 1 }}</span><strong>{{ label }}</strong>
      </li>
    </ol>

    <div v-if="errorMessage" class="notice-panel error-notice assistant-error">{{ errorMessage }}</div>

    <div class="assistant-workspace">
      <section class="assistant-conversation" aria-label="Assistant conversation">
        <header>
          <div>
            <p>Planning conversation</p>
            <span v-if="session">Session #{{ session.id }} · {{ session.parser_provider }} parser</span>
            <span v-else>Start with the constraints that matter to you</span>
          </div>
          <button v-if="session" class="assistant-text-button" type="button" @click="reset">New conversation</button>
        </header>

        <div v-if="!session" class="assistant-start">
          <div class="assistant-mark" aria-hidden="true">M</div>
          <h2>What should this week look like?</h2>
          <p>Include the household size, budget, restrictions and any ingredients you already have. You can add missing details in later messages.</p>
          <form @submit.prevent="startSession">
            <textarea v-model="starterMessage" rows="5" required placeholder="Example: Plan for 2 people, S$15 per meal, low sodium and no peanuts. I already have chicken breast." />
            <div>
              <span>Medical treatment advice is outside the project boundary.</span>
              <button class="assistant-primary" type="submit" :disabled="isLoading || !starterMessage.trim()">
                {{ isLoading ? "Understanding…" : "Start planning" }}
              </button>
            </div>
          </form>
        </div>

        <template v-else>
          <div class="assistant-thread" aria-live="polite">
            <article v-for="message in session.messages" :key="message.id" class="assistant-message" :class="message.role">
              <span>{{ message.role === 'user' ? 'You' : 'MealCraft' }}</span>
              <p>{{ message.content }}</p>
            </article>
          </div>

          <form v-if="session.status !== 'planned'" class="assistant-composer" @submit.prevent="sendReply">
            <textarea v-model="replyMessage" rows="3" required :placeholder="session.clarification_questions[0] || 'Add or revise a constraint…'" />
            <div>
              <span>{{ session.status === 'ready' ? 'You can still revise a constraint before confirming.' : 'Answer the clarification or add another constraint.' }}</span>
              <button class="assistant-primary" type="submit" :disabled="isLoading || !replyMessage.trim()">
                {{ isLoading ? "Updating…" : "Send" }}
              </button>
            </div>
          </form>
        </template>
      </section>

      <aside class="constraint-inspector" aria-label="Structured planning constraints">
        <header>
          <div><p>Structured constraints</p><span>What the planner will execute</span></div>
          <span class="agent-status" :class="session?.status || 'empty'">{{ session?.status || 'waiting' }}</span>
        </header>

        <div v-if="!session" class="constraint-empty">
          <p>Constraints will appear here as soon as the assistant has parsed your first message.</p>
        </div>
        <template v-else>
          <dl class="constraint-list">
            <div><dt>Household</dt><dd>{{ formatOptionalNumber(session.constraints.household_size, ' people') }}</dd></div>
            <div><dt>Meal budget</dt><dd>{{ session.constraints.budget_per_meal_sgd === null ? 'Not specified' : `S$${session.constraints.budget_per_meal_sgd}` }}</dd></div>
            <div><dt>Weekly budget</dt><dd>{{ session.constraints.weekly_budget_sgd === null ? 'Not specified' : `S$${session.constraints.weekly_budget_sgd}` }}</dd></div>
            <div><dt>Cooking time</dt><dd>{{ session.constraints.max_cooking_time_minutes }} min</dd></div>
            <div><dt>Pricing</dt><dd>{{ session.constraints.pricing_mode === 'live' ? 'Live FairPrice' : 'Fixture · reproducible' }}</dd></div>
          </dl>

          <section class="constraint-section">
            <h2>Restrictions</h2>
            <div v-if="session.constraints.allergens.length" class="constraint-chips danger">
              <span v-for="item in session.constraints.allergens" :key="item">{{ item }} allergen</span>
            </div>
            <div v-if="session.constraints.excluded_ingredients.length" class="constraint-chips exclusion-chips">
              <span v-for="item in session.constraints.excluded_ingredients" :key="item">exclude {{ item.replaceAll('_', ' ') }}</span>
            </div>
            <p v-if="!session.constraints.allergens.length && !session.constraints.excluded_ingredients.length" class="constraint-muted">No allergens or excluded ingredients stated.</p>
          </section>

          <section class="constraint-section">
            <h2>Preferences and targets</h2>
            <div v-if="preferences.length || nutritionTargets.length" class="constraint-chips">
              <span v-for="item in preferences" :key="item">{{ item.replaceAll('-', ' ') }}</span>
              <span v-for="item in nutritionTargets" :key="item">{{ item }}</span>
            </div>
            <p v-else class="constraint-muted">No optional nutrition targets stated.</p>
          </section>

          <section class="constraint-section">
            <h2>Available ingredients</h2>
            <div v-if="session.constraints.available_ingredients.length" class="pantry-inspector">
              <div v-for="item in session.constraints.available_ingredients" :key="item.normalized_name">
                <strong>{{ item.normalized_name.replaceAll('_', ' ') }}</strong>
                <span :class="{ pending: item.quantity === null }">{{ formatPantryQuantity(item) }}</span>
              </div>
            </div>
            <p v-else class="constraint-muted">No existing ingredients stated.</p>
          </section>

          <div v-if="session.clarification_questions.length" class="clarification-card">
            <span>Clarification needed</span>
            <p>{{ session.clarification_questions[0] }}</p>
          </div>

          <div v-if="session.status === 'planned'" class="plan-created-card">
            <span>Plan created</span>
            <strong>#{{ session.plan_id }}</strong>
            <NuxtLink :to="{ path: '/dashboard', query: { plan: session.plan_id } }">Open nutrition dashboard →</NuxtLink>
          </div>

          <button v-else class="assistant-confirm" type="button" :disabled="!session.can_confirm || isLoading" @click="confirm">
            {{ isLoading ? 'Generating seven days…' : 'Confirm and generate plan' }}
          </button>
          <p v-if="!session.can_confirm && session.status !== 'planned'" class="confirm-hint">Resolve the highlighted clarification before confirming.</p>
          <p v-else-if="generatedPlan" class="confirm-hint">The plan contains {{ generatedPlan.days.length }} main meals.</p>
        </template>
      </aside>
    </div>
  </main>
</template>
