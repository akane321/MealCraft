<script setup lang="ts">
import { formatWhen, humanKey } from "~/lib/ops";
import { qualityBytes, qualityDistribution, qualityPageLabel, qualityPercent, qualityReasonLabel, shortQualityDigest } from "~/lib/ops-quality";
import type { OpsDataQualitySummary, OpsDroppedCandidateCollection } from "~/types/ops-quality";

const PAGE_SIZE = 25;
const config = useRuntimeConfig();
const apiFetch = useApiFetch();

const summary = ref<OpsDataQualitySummary | null>(null);
const summaryFailed = ref(false);
const dropped = ref<OpsDroppedCandidateCollection | null>(null);
const droppedFailed = ref(false);
const droppedLoading = ref(false);
const reason = ref("");
const offset = ref(0);
let droppedRequest = 0;

const reasonOptions = computed(() => Object.keys(summary.value?.dropped_by_reason ?? {}).sort());
const distributions = computed(() => [
  { key: "cuisine", label: "Cuisine", rows: qualityDistribution(summary.value?.by_cuisine) },
  { key: "course", label: "Course", rows: qualityDistribution(summary.value?.by_course) },
  { key: "source", label: "Source", rows: qualityDistribution(summary.value?.by_source) },
]);
const estimatedShares = computed(() => {
  const shares = summary.value?.estimated_share;
  return shares
    ? [
        { label: "Servings", value: shares.servings },
        { label: "Times", value: shares.times },
        { label: "Ingredient amounts", value: shares.ingredient_amounts },
      ]
    : [];
});

// Every candidate from enrichment to release: build failures carry a recorded reason below; the quota pick has only a count.
const funnel = computed(() => {
  const coverage = summary.value?.coverage;
  if (!coverage) return [];
  const built = coverage.built_before_quota ?? null;
  const unbucketed = coverage.unbucketed_cuisine ?? null;
  return [
    { label: "entered enrichment", count: coverage.enrichment_set, note: "" },
    { label: "dropped by the build", count: built === null ? null : coverage.enrichment_set - built, note: "" },
    { label: "built", count: built, note: "" },
    {
      // Data release v3 (ADR-0111) also drops built recipes for a repeated title, implausible energy or a new
      // ingredient id after the build, so this step is no longer the quota pick alone.
      label: "not picked by the cuisine and course quota or dropped by the release checks",
      count: coverage.not_picked_by_quota ?? null,
      note: unbucketed ? `${unbucketed.toLocaleString()} with a cuisine no quota bucket claims` : "",
    },
    { label: "released", count: coverage.released_recipes, note: "" },
  ];
});

function estimatedWidth(value: number) {
  return `${Math.min(100, Math.max(0, value * 100))}%`;
}

async function loadSummary() {
  summaryFailed.value = false;
  summary.value = null;
  try {
    summary.value = await apiFetch<OpsDataQualitySummary>(`${config.public.apiBase}/api/ops/data-quality`);
  }
  catch {
    summaryFailed.value = true;
  }
}

async function loadDropped() {
  const request = ++droppedRequest;
  droppedFailed.value = false;
  droppedLoading.value = true;
  try {
    const result = await apiFetch<OpsDroppedCandidateCollection>(`${config.public.apiBase}/api/ops/data-quality/dropped`, {
      query: {
        offset: offset.value,
        limit: PAGE_SIZE,
        ...(reason.value ? { reason: reason.value } : {}),
      },
    });
    if (request === droppedRequest) dropped.value = result;
  }
  catch {
    if (request === droppedRequest) {
      dropped.value = null;
      droppedFailed.value = true;
    }
  }
  finally {
    if (request === droppedRequest) droppedLoading.value = false;
  }
}

function selectReason() {
  offset.value = 0;
  void loadDropped();
}

function previousPage() {
  offset.value = Math.max(0, offset.value - PAGE_SIZE);
  void loadDropped();
}

function nextPage() {
  if (dropped.value?.next_offset === null || dropped.value?.next_offset === undefined) return;
  offset.value = dropped.value.next_offset;
  void loadDropped();
}

function retryAll() {
  void Promise.all([loadSummary(), loadDropped()]);
}

onMounted(retryAll);
</script>

<template>
  <div class="ops-page quality-page">
    <header>
      <h1 class="mc-serif">What is in this release—and how it got there</h1>
      <p>Coverage, inferred values and dropped candidates come from the registered release build. This page never reads an operator-supplied path.</p>
    </header>

    <div v-if="summaryFailed" class="ops-card" role="alert">
      <p class="ops-error">Release quality couldn't be loaded.</p>
      <button type="button" class="mc-pill" @click="retryAll">Try again</button>
    </div>
    <p v-else-if="!summary" class="ops-muted" aria-busy="true">Loading release quality…</p>

    <template v-else>
      <section class="ops-card release-head" aria-labelledby="release-title">
        <div>
          <p class="mc-eyebrow">Registered release</p>
          <h2 id="release-title">{{ summary.release_version }}</h2>
          <p class="ops-muted">Schema {{ summary.schema_version ?? "unavailable" }} · generated {{ formatWhen(summary.generated_at) }}</p>
        </div>
        <span class="ops-badge" :class="summary.status === 'available' ? 'success' : 'warning'">
          {{ summary.status === "available" ? "Available" : "Degraded" }}
        </span>
      </section>

      <section v-if="summary.issues.length" class="ops-card issues" aria-labelledby="summary-issues-title">
        <h2 id="summary-issues-title">Release issues</h2>
        <p class="ops-muted">Unavailable or invalid evidence stays unavailable; the console does not replace it with zero.</p>
        <ul>
          <li v-for="issue in summary.issues" :key="`${issue.artifact}-${issue.code}-${issue.detail}`">
            <b>{{ issue.artifact }}</b><span>{{ humanKey(issue.code) }} · {{ issue.detail }}</span>
          </li>
        </ul>
      </section>

      <section aria-labelledby="coverage-title">
        <div class="section-heading">
          <div>
            <p class="mc-eyebrow">Coverage</p>
            <h2 id="coverage-title" class="mc-serif">Released records</h2>
          </div>
        </div>
        <!-- Where the cards would be: a dashed box with the reason. -->
        <p v-if="!summary.coverage" class="unavailable">Coverage is unavailable from this release.</p>
        <div v-if="summary.coverage" class="metric-grid">
          <!-- The overview's stat cards: a tile, then the label and the value on one baseline. -->
          <article class="metric mc-stat" data-tone="violet"><span class="mc-tile" aria-hidden="true"><UIcon name="i-lucide-book-open" /></span><span class="mc-stat-row"><span class="mc-stat-label">Recipes</span><strong class="mc-stat-value">{{ summary.coverage.released_recipes.toLocaleString() }}</strong></span></article>
          <article class="metric mc-stat" data-tone="green"><span class="mc-tile" aria-hidden="true"><UIcon name="i-lucide-carrot" /></span><span class="mc-stat-row"><span class="mc-stat-label">Ingredients</span><strong class="mc-stat-value">{{ summary.coverage.released_ingredients.toLocaleString() }}</strong></span></article>
          <article class="metric mc-stat" data-tone="sky"><span class="mc-tile" aria-hidden="true"><UIcon name="i-lucide-list-checks" /></span><span class="mc-stat-row"><span class="mc-stat-label">Every release field</span><strong class="mc-stat-value">{{ summary.coverage.recipes_with_every_field.toLocaleString() }}</strong></span><small class="mc-stat-note">of {{ summary.coverage.released_recipes.toLocaleString() }} recipes</small></article>
        </div>
      </section>

      <div class="ops-grid evidence-grid">
        <section class="ops-card" aria-labelledby="estimated-title">
          <h2 id="estimated-title">Estimated rather than stated</h2>
          <p class="ops-muted intro">These are inference shares, not missing-field rates. Lower means more values came directly from source records.</p>
          <p v-if="!summary.estimated_share" class="ops-muted">Inference shares are unavailable from this release.</p>
          <dl v-else class="share-list">
            <div v-for="item in estimatedShares" :key="item.label">
              <dt>{{ item.label }} <b class="mc-num">{{ qualityPercent(item.value) }}</b></dt>
              <dd><span :style="{ width: estimatedWidth(item.value) }" /></dd>
            </div>
          </dl>
        </section>

        <section class="ops-card" aria-labelledby="nutrition-title">
          <h2 id="nutrition-title">Nutrition</h2>
          <p v-if="!summary.nutrition" class="ops-muted">Nutrition completeness is unavailable from this release.</p>
          <dl v-else class="nutrition-stats">
            <div><dt>Complete recipes</dt><dd class="mc-num">{{ summary.nutrition.complete_recipes.toLocaleString() }} / {{ summary.nutrition.total_recipes.toLocaleString() }}</dd></div>
            <div><dt>Completeness</dt><dd class="mc-num">{{ qualityPercent(summary.nutrition.total_recipes ? summary.nutrition.complete_recipes / summary.nutrition.total_recipes : 0) }}</dd></div>
            <div><dt>Median energy</dt><dd class="mc-num">{{ summary.nutrition.median_energy_kcal === null ? "—" : `${summary.nutrition.median_energy_kcal.toLocaleString()} kcal` }}</dd></div>
          </dl>
        </section>

        <section class="ops-card" aria-labelledby="review-title">
          <h2 id="review-title">Human review</h2>
          <p class="review-number mc-num" :class="{ missing: summary.allergen_rules_pending_human === null }">{{ summary.allergen_rules_pending_human === null ? "—" : summary.allergen_rules_pending_human.toLocaleString() }}</p>
          <p class="ops-muted">Allergen rules still awaiting human confirmation.</p>
        </section>
      </div>

      <section class="ops-card" aria-labelledby="distribution-title">
        <h2 id="distribution-title">Release distribution</h2>
        <div class="distribution-grid">
          <article v-for="distribution in distributions" :key="distribution.key">
            <h3>{{ distribution.label }}</h3>
            <p v-if="!distribution.rows.length" class="ops-muted">Unavailable.</p>
            <ol v-else>
              <li v-for="row in distribution.rows" :key="row.label">
                <span>{{ humanKey(row.label) }}</span>
                <span class="bar"><i :style="{ width: estimatedWidth(row.share) }" /></span>
                <b class="mc-num">{{ row.count.toLocaleString() }}</b>
              </li>
            </ol>
          </article>
        </div>
      </section>

      <section class="ops-card dropped-card" aria-labelledby="dropped-title">
        <header>
          <div>
            <h2 id="dropped-title">Dropped candidates</h2>
            <p class="ops-muted">Candidates that failed the build, with the recorded reason. From data release v3 the record also lists built recipes the release did not take; before v3 those have a count, not a record.</p>
          </div>
          <label>Reason
            <select v-model="reason" @change="selectReason">
              <option value="">All reasons</option>
              <option v-for="option in reasonOptions" :key="option" :value="option">{{ qualityReasonLabel(option) }}</option>
            </select>
          </label>
        </header>

        <ol v-if="funnel.length" class="funnel" aria-label="Release funnel">
          <li v-for="step in funnel" :key="step.label">
            <b class="mc-num">{{ step.count === null ? "—" : step.count.toLocaleString() }}</b> {{ step.label }}
            <small v-if="step.note">{{ step.note }}</small>
          </li>
        </ol>

        <div v-if="summary.dropped_by_reason" class="reason-counts" aria-label="Dropped counts by reason">
          <span v-for="(count, key) in summary.dropped_by_reason" :key="key"><b class="mc-num">{{ count.toLocaleString() }}</b> {{ qualityReasonLabel(key) }}</span>
        </div>

        <div v-if="droppedFailed" class="inline-error" role="alert">
          <p class="ops-error">Dropped candidates couldn't be loaded.</p>
          <button type="button" class="mc-pill" @click="loadDropped">Try again</button>
        </div>
        <p v-else-if="droppedLoading && !dropped" class="ops-muted" aria-busy="true">Loading dropped candidates…</p>
        <template v-else-if="dropped">
          <div v-if="dropped.status === 'degraded' || dropped.issues.length" class="dropped-warning" role="status">
            <b>Dropped-candidate evidence is degraded.</b>
            <span v-if="dropped.skipped_records">{{ dropped.skipped_records }} invalid {{ dropped.skipped_records === 1 ? "record was" : "records were" }} skipped.</span>
            <span v-for="issue in dropped.issues" :key="`${issue.code}-${issue.detail}`">{{ issue.detail }}</span>
          </div>
          <p v-if="dropped.total === null" class="empty ops-muted">The dropped artifact is unavailable; no total has been invented.</p>
          <p v-else-if="!dropped.items.length" class="empty ops-muted">No dropped candidate matches this reason.</p>
          <div v-else class="table-wrap" :aria-busy="droppedLoading">
            <table>
              <thead><tr><th>Candidate</th><th>Title</th><th>Reason</th></tr></thead>
              <tbody>
                <tr v-for="item in dropped.items" :key="item.candidate_id">
                  <td class="cand">{{ item.candidate_id }}</td>
                  <td>{{ item.title }}</td>
                  <td><span class="reason-pill">{{ qualityReasonLabel(item.reason) }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <footer class="pager">
            <span class="ops-muted">{{ qualityPageLabel(dropped.offset, dropped.items.length, dropped.total) }}</span>
            <button type="button" class="mc-pill" :disabled="droppedLoading || dropped.offset === 0" @click="previousPage">Previous</button>
            <button type="button" class="mc-pill" :disabled="droppedLoading || dropped.next_offset === null" @click="nextPage">Next</button>
          </footer>
        </template>
      </section>

      <section class="ops-card artifacts" aria-labelledby="artifacts-title">
        <h2 id="artifacts-title">Release evidence</h2>
        <p class="ops-muted">Only registered filenames and digests are shown. Server paths are never returned.</p>
        <p v-if="!summary.artifacts.length" class="ops-muted">No readable release artifacts were recorded.</p>
        <div v-else class="table-wrap">
          <table>
            <thead><tr><th>Artifact</th><th>SHA-256</th><th class="mc-num">Size</th><th>Updated</th></tr></thead>
            <tbody>
              <tr v-for="artifact in summary.artifacts" :key="artifact.name">
                <td>{{ artifact.name }}</td>
                <td><code :title="artifact.sha256">{{ shortQualityDigest(artifact.sha256) }}</code></td>
                <td class="mc-num">{{ qualityBytes(artifact.size_bytes) }}</td>
                <td class="ops-muted">{{ formatWhen(artifact.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.quality-page { padding-bottom: 32px; }
.release-head, .section-heading, .dropped-card > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.release-head h2, .section-heading h2 { margin: 2px 0 4px; }
.release-head p, .section-heading p, .dropped-card header p { margin: 0; }
.release-head .ops-badge { margin-top: 3px; }
/* Release issues: the amber warning pair. */
.issues { border-color: #fedf89; background: #fffaeb; box-shadow: none; }
.issues p { margin: -6px 0 12px; font-size: 13px; }
.issues ul { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.issues li { display: grid; gap: 2px; padding: 9px 12px; border: 1px solid #fef0c7; border-radius: 10px; background: #fff; font-size: 13px; }
.issues li span { color: #71717a; }
.section-heading { margin-bottom: 10px; }
/* Coverage numbers as stat cards; a card without a caption keeps an empty caption row, so the values share one baseline. */
.metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.metric-grid .mc-stat:not(:has(.mc-stat-note))::after { content: ""; height: 16px; margin-top: -10px; }
.unavailable { display: grid; place-items: center; min-height: 104px; margin: 0; border: 1px dashed #e4e4e7; border-radius: 12px; color: #71717a; font-size: 14px; }
/* Three cards in one row, each as tall as its own content. */
.evidence-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: start; }
.mc-stat .mc-stat-note { margin-top: -10px; }
.intro { margin: -5px 0 16px; font-size: 12.5px; line-height: 1.5; }
.share-list, .nutrition-stats { display: grid; gap: 13px; margin: 0; }
.share-list div { display: grid; gap: 6px; }
.share-list dt { display: flex; justify-content: space-between; gap: 12px; color: #52525b; font-size: 13px; }
.share-list dt b { color: #27272a; font-weight: 500; }
.share-list dd { height: 6px; margin: 0; overflow: hidden; border-radius: 999px; background: #f0f0f2; }
.share-list dd span { display: block; height: 100%; border-radius: inherit; background: #8b5cf6; }
/* Nutrition: label and value rows. */
.nutrition-stats { gap: 0; }
.nutrition-stats div { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f2f2f4; }
.nutrition-stats div:last-child { border-bottom: 0; }
.nutrition-stats dt { color: #52525b; font-size: 13px; line-height: 18px; }
.nutrition-stats dd { margin: 0; color: var(--mc-strong); font-size: 15px; line-height: 20px; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.review-number { margin: 0 0 4px; color: var(--mc-strong); font-size: 22px; line-height: 28px; font-weight: 600; }
.review-number.missing { color: #71717a; font-size: 14px; line-height: 20px; font-weight: 400; }
.distribution-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; }
.distribution-grid h3 { margin: 0 0 12px; color: #71717a; font-size: 12px; line-height: 16px; font-weight: 500; }
.distribution-grid ol { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.distribution-grid li { display: grid; grid-template-columns: minmax(90px, 1fr) minmax(70px, 1fr) auto; align-items: center; gap: 10px; color: #27272a; font-size: 13px; }
.distribution-grid li b { font-weight: 500; }
.distribution-grid .bar { height: 6px; overflow: hidden; border-radius: 999px; background: #f0f0f2; }
.distribution-grid .bar i { display: block; height: 100%; border-radius: inherit; background: #8b5cf6; }
.dropped-card { padding: 0; overflow: hidden; }
.dropped-card > header { padding: 20px; }
.dropped-card > header h2 { margin-bottom: 5px; }
.dropped-card label { display: grid; flex: 0 0 220px; grid-template-columns: minmax(0, 1fr); gap: 6px; color: #71717a; font-size: 12px; font-weight: 500; }
.dropped-card select { width: 100%; min-width: 0; }
/* One column a step, so a step never wraps away from the arrow before it: the arrow sits in the gap, not in the text. */
.funnel { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 6px 30px; margin: 0; padding: 0 20px 14px; list-style: none; color: #71717a; font-size: 12.5px; line-height: 18px; }
.funnel li { position: relative; }
/* A Lucide arrow in the gap, centred on the number line. */
.funnel li + li::before { position: absolute; top: 5px; left: -22px; width: 14px; height: 14px; background: #d4d4d8; content: ""; -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12h14M12 5l7 7-7 7'/%3E%3C/svg%3E") no-repeat center / 14px; mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12h14M12 5l7 7-7 7'/%3E%3C/svg%3E") no-repeat center / 14px; }
.funnel b { display: block; color: var(--mc-strong); font-size: 16px; line-height: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.funnel small { display: block; margin-top: 2px; color: #71717a; font-size: 12px; line-height: 16px; }
.reason-counts { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 20px 16px; }
.reason-counts span, .reason-pill { display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 8px; border-radius: 999px; background: #f4f4f5; color: #52525b; font-size: 12px; font-weight: 500; white-space: nowrap; }
.reason-counts b { color: #27272a; font-weight: 600; }
.inline-error, .empty { margin: 0; padding: 18px 20px; border-top: 1px solid #f0f0f2; }
.inline-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; background: #fef3f2; }
.inline-error p { margin: 0; color: #b42318; }
.empty { color: #71717a; text-align: center; }
.dropped-warning { display: grid; gap: 3px; padding: 12px 20px; border-top: 1px solid #fedf89; background: #fffaeb; color: #b54708; font-size: 12.5px; }
.table-wrap { overflow-x: auto; border-top: 1px solid #f0f0f2; }
td:first-child { white-space: nowrap; }
.cand { color: #52525b; font: 12.5px/20px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; text-align: left; }
.artifacts > p { margin: -6px 0 14px; font-size: 12.5px; }
.artifacts .table-wrap { margin: 0 -20px -20px; }
.artifacts code { color: #52525b; font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; }
</style>
