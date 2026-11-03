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
    tooltip: { slots: { content: "font-sans bg-[#18181B] text-white ring-0 rounded-[6px] shadow-md text-xs font-medium px-2 py-1" } },
    // Not used yet: themed so a first use already matches the product. Values that a theme variant also sets go on
    // that variant, since variant classes come after the slot's and win.
    dropdownMenu: {
      slots: { content: "font-sans rounded-[12px] ring-1 ring-[#ECECEF] shadow-md p-1 bg-white text-[#27272A]", item: "h-8 items-center rounded-[8px] before:rounded-[8px] text-[#27272A]" },
      variants: { size: { md: { item: "text-[13.5px]" } } },
    },
    popover: { slots: { content: "font-sans rounded-[12px] ring-1 ring-[#ECECEF] shadow-md p-1 bg-white text-[#27272A]" } },
    modal: {
      slots: { content: "font-sans bg-white text-[#27272A]" },
      variants: {
        overlay: { true: { overlay: "bg-[rgba(15,15,18,.32)]" } },
        fullscreen: { false: { content: "w-[calc(100vw-2rem)] max-w-lg rounded-[16px] ring-1 ring-[#ECECEF] shadow-md" } },
      },
    },
    toast: { slots: { root: "font-sans rounded-[12px] ring-1 ring-[#ECECEF] shadow-md bg-white text-[#27272A]" } },
  },
});
