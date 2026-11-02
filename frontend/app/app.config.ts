// Nuxt UI theme: zinc neutrals, a violet accent for focus and links, pill buttons.
export default defineAppConfig({
  ui: {
    colors: { primary: "violet", neutral: "zinc" },
    button: {
      slots: { base: "rounded-full font-medium" },
      variants: {
        size: {
          sm: { base: "h-8 px-3 text-[13px] gap-1.5" },
          md: { base: "h-9 px-4 text-sm gap-2" },
        },
      },
    },
    kbd: { base: "rounded-[5px] normal-case bg-[#F4F4F5] ring-1 ring-inset ring-[#E4E4E7] text-[#71717A]" },
    tooltip: { slots: { content: "bg-[#18181B] text-white ring-0 rounded-md shadow-md" } },
  },
});
