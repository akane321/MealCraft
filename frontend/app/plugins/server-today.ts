import { setServerToday } from "~/lib/meal-plan-format";
import type { HealthResponse } from "~/types/system";

export interface ServerClock {
  today: string;
  // The simulated now (debugging and demos), or null on the real clock.
  simulated: string | null;
}

// Today is the server's (Singapore, or a simulated day): the browser's clock and timezone no longer decide which
// day is "today" in the week view, so the page and the planner always agree.
export default defineNuxtPlugin(async () => {
  const config = useRuntimeConfig();
  const clock = useState<ServerClock | null>("server-clock", () => null);
  if (!clock.value) {
    const apiBase = import.meta.server ? config.apiBase : config.public.apiBase;
    try {
      const health = await $fetch<HealthResponse>(`${apiBase}/api/health`, { timeout: 2000 });
      if (health.today) clock.value = { today: health.today, simulated: health.simulated_today ?? null };
    }
    catch {
      // The browser's own date stands in.
    }
  }
  setServerToday(clock.value?.today ?? null);
});
