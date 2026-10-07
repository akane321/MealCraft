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
});
