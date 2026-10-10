// Switches for UI pieces that are built but not yet safe to expose.
// The theme toggle appears once every page uses the design tokens (until then, dark mode
// can still be previewed with ?theme=dark).
export const SHOW_THEME_TOGGLE = true

// Pages whose amounts go through useMoney(), so the hide-amounts switch covers them fully.
export const PRIVACY_READY_PATHS = ["/", "/holdings", "/brokers", "/signals"]
