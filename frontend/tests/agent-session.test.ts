import { ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMealCraftAgent } from "../app/composables/useMealCraftAgent";

vi.mock("~/lib/home-surface", () => ({ conversationForPlan: () => null }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function setup() {
  const fetch = vi.fn();
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("useRuntimeConfig", () => ({ public: { apiBase: "" } }));
  vi.stubGlobal("useApiFetch", () => fetch);
  return { fetch, agent: useMealCraftAgent() };
}

afterEach(() => vi.unstubAllGlobals());

describe("switching agent conversations", () => {
  it.each(["success", "failure"])("ignores an old %s and its finalizer while the fresh request is running", async (outcome) => {
    const { fetch, agent } = setup();
    const old = deferred<unknown>();
    const fresh = deferred<unknown>();
    fetch.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
    const previous = agent.create("Old request");
    agent.reset();
    expect(agent.isLoading.value).toBe(false);
    const current = agent.create("Fresh request");
    if (outcome === "success") old.resolve({ id: 51 });
    else old.reject({ data: { detail: "Old request failed" } });
    expect(await previous).toBeNull();
    expect(agent.session.value).toBeNull();
    expect(agent.errorMessage.value).toBeNull();
    expect(agent.isLoading.value).toBe(true);
    fresh.resolve({ id: 52 });
    await current;
    expect(agent.session.value?.id).toBe(52);
    expect(agent.isLoading.value).toBe(false);
  });

  it("does not recover a failed confirmation into a conversation opened afterwards", async () => {
    const { fetch, agent } = setup();
    fetch.mockResolvedValueOnce({ id: 51, messages: [] });
    await agent.create("Old request");
    const explained = deferred<unknown>();
    fetch.mockRejectedValueOnce({ data: { detail: "No week fits" } }).mockReturnValueOnce(explained.promise);
    const confirmation = agent.confirm();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    agent.reset();
    explained.resolve({ id: 51, messages: [{ id: 1, content: "Old explanation" }] });
    await confirmation;
    expect(agent.session.value).toBeNull();
    expect(agent.generatedPlan.value).toBeNull();
    expect(agent.errorMessage.value).toBeNull();
  });

  it.each(["confirm", "confirmReplan"] as const)("ignores a stale %s's saved plan", async (method) => {
    const { fetch, agent } = setup();
    fetch.mockResolvedValueOnce({ id: 51, messages: [] });
    await agent.create("Old request");
    const delayed = deferred<unknown>();
    fetch.mockReturnValueOnce(delayed.promise);
    const confirmation = agent[method]();
    agent.reset();
    fetch.mockResolvedValueOnce({ id: 52, messages: [] });
    await agent.create("Fresh request");
    delayed.resolve({ session: { id: 51 }, plan: { id: 9001 } });
    await confirmation;
    expect(agent.session.value?.id).toBe(52);
    expect(agent.generatedPlan.value).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("clears a stale preview's card on a 409 and keeps the message to ask again", async () => {
    const { fetch, agent } = setup();
    fetch.mockResolvedValueOnce({ id: 51, messages: [], pending_replan: { id: 7 } });
    await agent.create("Swap Monday's dinner");
    const stale = "This preview is stale because the meal plan has changed. Generate a new preview.";
    fetch.mockRejectedValueOnce({ statusCode: 409, data: { detail: stale } })
      .mockResolvedValueOnce({ id: 51, messages: [], pending_replan: null });
    expect(await agent.confirmReplan()).toBeNull();
    expect(fetch).toHaveBeenLastCalledWith("/api/agent/sessions/51/replan/discard", { method: "POST" });
    expect(agent.session.value?.pending_replan).toBeNull();
    expect(agent.errorMessage.value).toBe(stale);
  });
});

describe("a confirmation typed in the chat (ADR-0098)", () => {
  it.each(["PLAN_SAVED", "REPLAN_APPLIED"])("hands the plan panel the week it saved (%s)", async (ended) => {
    const { fetch, agent } = setup();
    fetch.mockResolvedValueOnce({ id: 51, messages: [], plan_id: null });
    await agent.create("Dinners for two");
    fetch.mockResolvedValueOnce({ id: 51, messages: [], plan_id: 9001, latest_run: { status: "committed", termination_reason_code: ended } })
      .mockResolvedValueOnce({ id: 9001, revision: 2 });
    await agent.reply("I confirm. Please proceed.");
    expect(fetch).toHaveBeenLastCalledWith("/api/plans/9001");
    expect(agent.session.value?.plan_id).toBe(9001);
    expect(agent.generatedPlan.value).toEqual({ id: 9001, revision: 2 });
  });

  it("leaves the plan panel alone after a turn that saved nothing", async () => {
    const { fetch, agent } = setup();
    fetch.mockResolvedValueOnce({ id: 51, messages: [], plan_id: 9001 });
    await agent.create("Swap Monday's dinner");
    fetch.mockResolvedValueOnce({ id: 51, messages: [], plan_id: 9001, latest_run: { status: "committed", termination_reason_code: "SCOPE_SOCIAL" } });
    await agent.reply("ok");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(agent.generatedPlan.value).toBeNull();
  });

  it("does not hand a week saved in a conversation left meanwhile to the one opened afterwards", async () => {
    const { fetch, agent } = setup();
    fetch.mockResolvedValueOnce({ id: 51, messages: [], plan_id: null });
    await agent.create("Dinners for two");
    const saved = deferred<unknown>();
    fetch.mockResolvedValueOnce({ id: 51, messages: [], plan_id: 9001, latest_run: { status: "committed", termination_reason_code: "PLAN_SAVED" } })
      .mockReturnValueOnce(saved.promise);
    const replied = agent.reply("确认");
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    agent.reset();
    saved.resolve({ id: 9001 });
    await replied;
    expect(agent.generatedPlan.value).toBeNull();
  });
});

describe("the household's words on their way", () => {
  const words = "Plan next week, 7 days, three meals a day, budget S$250";

  it.each(["create", "reply"] as const)("%s shows the message at once and until its answer arrives", async (method) => {
    const { fetch, agent } = setup();
    if (method === "reply") {
      fetch.mockResolvedValueOnce({ id: 51, messages: [] });
      await agent.create("Dinners for three");
    }
    const answer = deferred<unknown>();
    fetch.mockReturnValueOnce(answer.promise);
    const sending = agent[method](words);
    expect(agent.pending.value).toBe(words);
    expect(agent.isLoading.value).toBe(true);
    answer.resolve({ id: 51, messages: [{ id: 1, role: "user", content: words }] });
    await sending;
    expect(agent.pending.value).toBeNull();
    expect(agent.isLoading.value).toBe(false);
    expect(agent.session.value?.messages).toHaveLength(1);
  });

  it("goes with a failed request, whose error stays to be read, and the request answers null", async () => {
    const { fetch, agent } = setup();
    const answer = deferred<unknown>();
    fetch.mockReturnValueOnce(answer.promise);
    const sending = agent.create(words);
    expect(agent.pending.value).toBe(words);
    answer.reject({ data: { detail: "The planner could not be reached." } });
    expect(await sending).toBeNull();
    expect(agent.pending.value).toBeNull();
    expect(agent.isLoading.value).toBe(false);
    expect(agent.errorMessage.value).toBe("The planner could not be reached.");
  });

  it("are a typed answer's, never a tapped option's, and stay through a rename", async () => {
    const { fetch, agent } = setup();
    fetch.mockResolvedValueOnce({ id: 51, messages: [] });
    await agent.create("Dinners");
    const base = { question_id: "q", context_version: 1, plan_revision: null };
    const typed = deferred<unknown>();
    fetch.mockReturnValueOnce(typed.promise);
    const answering = agent.answerInteraction({ ...base, option_ids: [], free_text: "three of us" });
    expect(agent.pending.value).toBe("three of us");
    fetch.mockResolvedValueOnce({ id: 51, messages: [], title: "Dinners" });
    await agent.label(51, { title: "Dinners" });
    expect(agent.pending.value).toBe("three of us");
    typed.resolve({ id: 51, messages: [] });
    await answering;
    const tapped = deferred<unknown>();
    fetch.mockReturnValueOnce(tapped.promise);
    const choosing = agent.answerInteraction({ ...base, option_ids: ["household_size_3"], free_text: null });
    expect(agent.pending.value).toBeNull();
    tapped.resolve({ id: 51, messages: [] });
    await choosing;
  });

  it("are dropped with the conversation they were sent to", () => {
    const { fetch, agent } = setup();
    fetch.mockReturnValueOnce(new Promise(() => {}));
    void agent.create(words);
    agent.reset();
    expect(agent.pending.value).toBeNull();
  });
});
