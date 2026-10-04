<script setup lang="ts">
import { formatWhen, humanKey } from "~/lib/ops";
import { qualityBytes, qualityDistribution, qualityPageLabel, qualityPercent, shortQualityDigest } from "~/lib/ops-quality";
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
      <p class="mc-eyebrow">Data quality</p>
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
        <span class="ops-badge" :style="{ '--dot': summary.status === 'available' ? 'var(--sage)' : 'var(--warn)' }">
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
          <p v-if="!summary.coverage" class="ops-muted">Coverage is unavailable from this release.</p>
        </div>
        <div v-if="summary.coverage" class="metric-grid">
          <article class="ops-card metric"><span>Recipes</span><strong class="mc-num">{{ summary.coverage.released_recipes.toLocaleString() }}</strong></article>
          <article class="ops-card metric"><span>Ingredients</span><strong class="mc-num">{{ summary.coverage.released_ingredients.toLocaleString() }}</strong></article>
          <article class="ops-card metric"><span>Every release field</span><strong class="mc-num">{{ summary.coverage.recipes_with_every_field.toLocaleString() }}</strong><small>of {{ summary.coverage.released_recipes.toLocaleString() }} recipes</small></article>
          <article class="ops-card metric"><span>Enrichment set</span><strong class="mc-num">{{ summary.coverage.enrichment_set.toLocaleString() }}</strong></article>
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
          <p class="review-number mc-num">{{ summary.allergen_rules_pending_human === null ? "—" : summary.allergen_rules_pending_human.toLocaleString() }}</p>
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
            <p class="ops-muted">Candidates that did not enter the release, with the recorded reason.</p>
          </div>
          <label>Reason
            <select v-model="reason" @change="selectReason">
              <option value="">All reasons</option>
              <option v-for="option in reasonOptions" :key="option" :value="option">{{ humanKey(option) }}</option>
            </select>
          </label>
        </header>

        <div v-if="summary.dropped_by_reason" class="reason-counts" aria-label="Dropped counts by reason">
          <span v-for="(count, key) in summary.dropped_by_reason" :key="key"><b class="mc-num">{{ count.toLocaleString() }}</b> {{ humanKey(key) }}</span>
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
                  <td class="mc-num">{{ item.candidate_id }}</td>
                  <td>{{ item.title }}</td>
                  <td><span class="reason-pill">{{ humanKey(item.reason) }}</span></td>
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
            <thead><tr><th>Artifact</th><th>SHA-256</th><th>Size</th><th>Updated</th></tr></thead>
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
.issues { border-color: rgba(217, 165, 90, 0.4); background: rgba(217, 165, 90, 0.07); }
.issues p { margin: -6px 0 12px; font-size: 13px; }
.issues ul { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.issues li { display: grid; gap: 2px; padding: 9px 12px; border-radius: 10px; background: var(--s2); font-size: 13px; }
.issues li span { color: var(--t3); }
.section-heading { margin-bottom: 10px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.metric { display: grid; gap: 5px; padding: 16px; }
.metric span, .metric small { color: var(--t3); font-size: 12px; }
.metric strong { font-family: var(--serif); font-size: 30px; font-weight: 300; }
.evidence-grid { align-items: stretch; }
.evidence-grid > .ops-card { min-height: 205px; }
.intro { margin: -5px 0 16px; font-size: 12.5px; line-height: 1.5; }
.share-list, .nutrition-stats { display: grid; gap: 13px; margin: 0; }
.share-list div { display: grid; gap: 6px; }
.share-list dt { display: flex; justify-content: space-between; gap: 12px; color: var(--t2); font-size: 13px; }
.share-list dd { height: 7px; margin: 0; overflow: hidden; border-radius: 999px; background: var(--s3); }
.share-list dd span { display: block; height: 100%; border-radius: inherit; background: #d9a55a; }
.nutrition-stats { grid-template-columns: repeat(3, 1fr); }
.nutrition-stats div { padding: 11px; border-radius: 10px; background: var(--s2); }
.nutrition-stats dt { color: var(--t3); font-size: 12px; }
.nutrition-stats dd { margin: 4px 0 0; font-family: var(--serif); font-size: 22px; }
.review-number { margin: 24px 0 5px; font-family: var(--serif); font-size: 42px; }
.distribution-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; }
.distribution-grid h3 { margin: 0 0 12px; color: var(--t2); font-size: 13px; }
.distribution-grid ol { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.distribution-grid li { display: grid; grid-template-columns: minmax(90px, 1fr) minmax(70px, 1fr) auto; align-items: center; gap: 9px; font-size: 12.5px; }
.distribution-grid .bar { height: 5px; overflow: hidden; border-radius: 999px; background: var(--s3); }
.distribution-grid .bar i { display: block; height: 100%; border-radius: inherit; background: var(--sage); }
.dropped-card { padding: 0; overflow: hidden; }
.dropped-card > header { padding: 20px; }
.dropped-card > header h2 { margin-bottom: 5px; }
.dropped-card label { display: grid; min-width: 220px; gap: 5px; color: var(--t3); font-size: 12px; }
select { padding: 8px 10px; border: 1px solid var(--line-2); border-radius: 9px; background: var(--s2); color: var(--ivory); font: inherit; }
.reason-counts { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 20px 16px; }
.reason-counts span, .reason-pill { padding: 3px 9px; border: 1px solid var(--line-2); border-radius: 999px; color: var(--t2); font-size: 11.5px; }
.inline-error, .empty { margin: 0; padding: 18px 20px; border-top: 1px solid var(--line); }
.inline-error p { margin: 0 0 10px; }
.dropped-warning { display: grid; gap: 3px; padding: 12px 20px; border-top: 1px solid rgba(217, 165, 90, 0.3); background: rgba(217, 165, 90, 0.08); color: var(--t2); font-size: 12.5px; }
.table-wrap { overflow-x: auto; border-top: 1px solid var(--line); }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th { padding: 10px 14px; border-bottom: 1px solid var(--line-2); color: var(--t3); font-weight: 500; text-align: left; white-space: nowrap; }
td { padding: 10px 14px; border-bottom: 1px solid var(--line); vertical-align: top; }
td:first-child { white-space: nowrap; }
.pager { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 12px 16px; }
.pager span { margin-right: auto; font-size: 12px; }
.artifacts > p { margin: -6px 0 14px; font-size: 12.5px; }
.artifacts .table-wrap { margin: 0 -20px -20px; }
.artifacts code { color: var(--t2); }
button:disabled { cursor: not-allowed; opacity: 0.45; }

@media (max-width: 1080px) {
  .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .distribution-grid { grid-template-columns: 1fr; }
}
</style>
