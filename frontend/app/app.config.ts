// Nuxt UI theme: zinc neutrals, a violet accent for focus and links, pill buttons.
// Tooltips, menus, popovers, modals and toasts render in a portal outside .mc-shell, where the body text is the
// landing's navy, so each of their slots sets its own colours.
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
    tooltip: { slots: { content: "bg-[#18181B] text-white ring-0 rounded-md shadow-md text-xs font-medium px-2 py-1" } },
    // Not used yet: themed so a first use already matches the product.
    dropdownMenu: { slots: { content: "rounded-xl ring-1 ring-[#ECECEF] shadow-md p-1 bg-white text-[#27272A]", item: "h-8 items-center rounded-lg text-[13.5px] text-[#27272A]" } },
    popover: { slots: { content: "rounded-xl ring-1 ring-[#ECECEF] shadow-md p-1 bg-white text-[#27272A]" } },
    modal: { slots: { overlay: "bg-[rgba(15,15,18,.32)] backdrop-blur-[2px]", content: "rounded-2xl ring-1 ring-[#ECECEF] shadow-md bg-white text-[#27272A]" } },
    toast: { slots: { root: "rounded-xl ring-1 ring-[#ECECEF] shadow-md bg-white text-[#27272A]" } },
  },
});
