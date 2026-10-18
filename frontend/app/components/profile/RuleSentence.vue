<script setup lang="ts" generic="T extends HouseholdRule">
import { addRules, failed, IDLE, LOADING, received, removeRule, type RuleDraft } from "~/lib/rule-draft";
import type { HouseholdRule, PresenceRule, RuleKind, RuleParseRequest } from "~/types/household";

// One sentence -> what we understood -> the household adds it. Added rules are stored when the profile is saved.
const props = defineProps<{
  kind: RuleKind;
  members: RuleParseRequest["members"];
}>();
const rules = defineModel<T[]>({ required: true });

const COPY = {
  presence: {
    label: "Who's home",
    placeholder: "e.g. \"The kids have lunch at school on weekdays\"",
    empty: "No rules yet. Everyone eats every meal at home.",
  },
  cooking_time: {
    label: "Cooking time on some days",
    placeholder: "e.g. \"Weekday dinners within 30 minutes\"",
    empty: "No time rules. Every meal uses the cooking time above.",
  },
} as const;

const { parseRule } = useHouseholdProfile();
const text = ref("");
const speaker = ref("");
const draft = ref<RuleDraft>(IDLE);
const copy = computed(() => COPY[props.kind]);
const names = computed(() => props.members.map(member => member.name.trim()).filter(Boolean));

async function read() {
  if (!text.value.trim() || !names.value.length) return;
  draft.value = LOADING;
  try {
    draft.value = received(await parseRule({
      kind: props.kind,
      text: text.value.trim(),
      members: props.members.filter(member => member.name.trim()).map(member => ({ ...member, name: member.name.trim() })),
      speaker: props.kind === "presence" && speaker.value ? speaker.value : null,
    }));
  }
  catch (error) {
    draft.value = failed((error as Error).message);
  }
}

function add() {
  if (draft.value.status !== "confirm") return;
  rules.value = addRules(rules.value, draft.value.rules as T[]);
  draft.value = IDLE;
  text.value = "";
}

/** A presence rule for someone no longer a member; the server refuses to save it. */
function orphaned(rule: HouseholdRule) {
  return "member_name" in rule && !names.value.includes((rule as PresenceRule).member_name);
}
</script>

<template>
  <div class="rule-sentence">
    <p class="rule-title">{{ copy.label }}</p>
    <ul v-if="rules.length" class="saved">
      <li v-for="(rule, index) in rules" :key="`${index}-${rule.restatement}`">
        <span>
          {{ rule.restatement }}
          <small>From "{{ rule.source_text }}"</small>
          <small v-if="orphaned(rule)" class="danger-text">Not a member any more. Remove this rule to save.</small>
        </span>
        <button type="button" class="text-button danger-text" @click="rules = removeRule(rules, index)">Remove</button>
      </li>
    </ul>
    <p v-else class="field-help">{{ copy.empty }}</p>

    <!-- Not a <form>: this sits inside the profile form, and Enter must read the sentence, not save. -->
    <div class="ask">
      <input
        v-model="text"
        type="text"
        maxlength="500"
        :aria-label="`${copy.label}: one sentence`"
        :placeholder="copy.placeholder"
        :disabled="draft.status === 'loading'"
        @keydown.enter.prevent="read"
        @input="draft.status === 'error' && (draft = IDLE)"
      >
      <select v-if="kind === 'presence'" v-model="speaker" aria-label="Who is writing?" title="Who is writing? This is who &quot;I&quot; and &quot;my&quot; mean.">
        <option value="">Who is writing?</option>
        <option v-for="name in names" :key="name" :value="name">{{ name }}</option>
      </select>
      <button class="secondary-button" type="button" :disabled="draft.status === 'loading' || !text.trim() || !names.length" @click="read">
        {{ draft.status === "loading" ? "Reading…" : "Read it" }}
      </button>
    </div>

    <section v-if="draft.status === 'confirm'" class="confirm" aria-live="polite">
      <p class="rule-title">We understood:</p>
      <ul>
        <li v-for="rule in draft.rules" :key="rule.restatement">{{ rule.restatement }}</li>
      </ul>
      <p v-if="draft.fellBack" class="field-help">Read with simple rules; check it carefully.</p>
      <div class="actions">
        <button class="secondary-button add" type="button" @click="add">Add {{ draft.rules.length === 1 ? "this rule" : "these rules" }}</button>
        <button class="text-button" type="button" @click="draft = IDLE">Change the sentence</button>
      </div>
    </section>
    <div v-else-if="draft.status === 'error'" class="issues" role="alert">
      <p v-for="issue in draft.issues" :key="issue">{{ issue }}</p>
    </div>
  </div>
</template>

<style scoped>
.rule-sentence { display: grid; gap: 10px; margin-top: 20px; }
.rule-title { margin: 0; color: var(--t2); font-size: 12px; font-weight: 650; }
.saved, .confirm ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.saved li { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 9px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--s2); font-size: 13px; }
.saved small { display: block; margin-top: 2px; color: var(--muted); font-size: 12px; }
.saved small.danger-text { color: var(--danger); }
.ask { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 9px; align-items: center; }
.ask select { width: auto; min-width: 150px; }
.confirm { display: grid; gap: 10px; padding: 14px 16px; border: 1px solid rgba(79, 184, 110, 0.4); border-radius: 14px; background: var(--c-ok-bg); }
.confirm li { font-size: 14px; font-weight: 650; color: var(--ivory); }
.actions { display: flex; align-items: center; gap: 14px; }
.add { border-color: var(--c-green); color: #fff; background: var(--c-green); }
.issues { padding: 10px 14px; border-radius: 10px; color: var(--danger); background: var(--c-allergy-bg); font-size: 12px; line-height: 1.55; }
.issues p { margin: 0; }
</style>
