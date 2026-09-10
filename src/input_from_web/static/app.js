try {
    await import('@m3e/web/core');
    await import('@m3e/web/icon');
    await import('@m3e/web/button');
    await import('@m3e/web/icon-button');
    await import('@m3e/web/switch');
    await import('@m3e/web/snackbar');
    await import('@m3e/web/bottom-sheet');
    await import('@m3e/web/button-group');
    await import('@m3e/web/theme');
  } catch (err) {
    // Surface CDN/boot failures visibly instead of leaving an unstyled, dead page.
    window.__M3E_BOOT_ERROR__ = String((err && err.message) || err);
    const banner = document.createElement('div');
    banner.textContent = 'Failed to load UI components: ' + window.__M3E_BOOT_ERROR__;
    banner.style.cssText = 'position:fixed;left:16px;right:16px;bottom:16px;background:#b3261e;color:#fff;'
      + 'padding:12px 16px;border-radius:12px;z-index:9999;font-size:14px;line-height:1.4';
    document.body.appendChild(banner);
    throw err;
  }

  // Make sure every <m3e-*> element on the DOM has finished upgrading
  // before the rest of this script runs.
  await Promise.all([
    customElements.whenDefined('m3e-button'),
    customElements.whenDefined('m3e-icon-button'),
    customElements.whenDefined('m3e-switch'),
    customElements.whenDefined('m3e-icon'),
    customElements.whenDefined('m3e-snackbar'),
    customElements.whenDefined('m3e-bottom-sheet'),
    customElements.whenDefined('m3e-button-group'),
    customElements.whenDefined('m3e-theme'),
  ]);

  // The theme element drives the entire dynamic-color palette + light/dark scheme.
  const appTheme = document.getElementById('app-theme');

  /* --- Mobile keyboard fit -------------------------------------------------
     When the virtual keyboard opens, keep the layout fitted to the visible
     area and stop the browser from panning the whole page upward (which
     made the textarea text and its floating label appear shifted). */
  const vv = window.visualViewport;
  if (vv) {
    // Clamp to innerHeight too: visualViewport can lag behind window resizes
    // (rotation, devtools), which would push bottom controls out of reach.
    const fitViewport = () => {
      const h = Math.round(Math.min(vv.height, window.innerHeight));
      document.documentElement.style.setProperty('--app-height', h + 'px');
      if (window.scrollY !== 0) window.scrollTo(0, 0);
    };
    vv.addEventListener('resize', fitViewport);
    vv.addEventListener('scroll', fitViewport);
    window.addEventListener('resize', fitViewport);
    fitViewport();
  }

const CONFIG = JSON.parse(document.getElementById('app-config').textContent);

/* --- i18n (Chinese / English) --- */
const I18N = {
  en: {
    title: "Input",
    label_type_here: "Type here...",
    autostart_label: "Auto-start on login (opens terminal with QR code)",
    sent: "Sent!",
    error_status: "Error ",
    network_error: "Network error",
    sending: "Sending...",
    offline: "Offline",
    send: "SEND",
    autostart_on: "Auto-start enabled",
    autostart_off: "Auto-start disabled",
    autostart_fail: "Failed: ",
    autostart_err: "Error: ",
    autostart_neterr: "Network error",
    enter_label: "Auto press Enter after send",
    enter_on: "Auto-Enter enabled",
    enter_off: "Auto-Enter disabled",
    paste_key_label: "Paste with Ctrl+Shift+V (default Ctrl+V)",
    paste_key_on: "Using Ctrl+Shift+V",
    paste_key_off: "Using Ctrl+V",
    settings_title: "Settings",
    clear_label: "Clear text",
    lang_label: "Switch language",
    prev_label: "Previous entry",
    next_label: "Next entry",
    method_label: "Clipboard mode (copy & paste, not direct typing)",
    method_on: "Clipboard mode",
    method_off: "Direct typing mode",
    auto_paste_label: "Auto-paste after copy (clipboard mode only)",
    auto_paste_on: "Auto-paste enabled",
    auto_paste_off: "Auto-paste disabled",
    voice_label: "Voice command: say 'send' to send",
    voice_on: "Voice command enabled",
    voice_off: "Voice command disabled",
    token_label: "Security token (URL secret)",
    token_on: "Security token enabled",
    token_off: "Security token DISABLED (trusted network only!)",
    lang_switch_label: "Language",
    theme_switch_label: "Theme",
    theme_light: "Light",
    theme_dark: "Dark",
    theme_auto: "Auto",
    theme_color_label: "Accent color",
    theme_material: "Material (system colors)",
    char_count_label: "chars",
  },
  zh: {
    title: "输入",
    label_type_here: "在此输入…",
    autostart_label: "开机自启（登录后自动弹终端显示二维码）",
    sent: "已发送！",
    error_status: "错误 ",
    network_error: "网络错误",
    sending: "发送中…",
    offline: "离线",
    send: "发送",
    autostart_on: "已开启开机自启",
    autostart_off: "已关闭开机自启",
    autostart_fail: "失败: ",
    autostart_err: "错误: ",
    autostart_neterr: "网络错误",
    enter_label: "发送后自动按 Enter",
    enter_on: "已开启自动 Enter",
    enter_off: "已关闭自动 Enter",
    paste_key_label: "粘贴快捷键使用 Ctrl+Shift+V（默认 Ctrl+V）",
    paste_key_on: "已切换为 Ctrl+Shift+V",
    paste_key_off: "已恢复 Ctrl+V",
    settings_title: "设置",
    clear_label: "清除文本",
    lang_label: "切换语言",
    prev_label: "上一条",
    next_label: "下一条",
    method_label: "剪贴板模式（复制粘贴，而非直接键入）",
    method_on: "已切换为剪贴板模式",
    method_off: "已切换为直接键入",
    auto_paste_label: "复制后自动粘贴（剪贴板模式下生效）",
    auto_paste_on: "已开启自动粘贴",
    auto_paste_off: "已关闭自动粘贴",
    voice_label: "语音指令：说 “send” 自动发送",
    voice_on: "已开启语音指令",
    voice_off: "已关闭语音指令",
    token_label: "启用安全令牌（URL 携带密钥）",
    token_on: "已启用安全令牌",
    token_off: "已关闭安全令牌（仅限可信网络！）",
    lang_switch_label: "界面语言",
    theme_switch_label: "主题",
    theme_light: "浅色",
    theme_dark: "深色",
    theme_auto: "自动",
    theme_color_label: "主题色",
    theme_material: "Material 系统配色",
    char_count_label: "字",
  },
};

const LANG_STORAGE_KEY = "input-from-web-lang";

function detectLang() {
  // 1. ?lang= override (also saved for next visit)
  const fromUrl = new URLSearchParams(location.search).get("lang");
  if (fromUrl === "zh" || fromUrl === "en") {
    localStorage.setItem(LANG_STORAGE_KEY, fromUrl);
    return fromUrl;
  }
  // 2. saved preference
  const saved = localStorage.getItem(LANG_STORAGE_KEY);
  if (saved === "zh" || saved === "en") return saved;
  // 3. auto from browser
  const nav = (navigator.language || "en").toLowerCase();
  return nav.startsWith("zh") ? "zh" : "en";
}

let LANG = detectLang();
function t(key) {
  const dict = I18N[LANG] || I18N.en;
  return dict[key] !== undefined ? dict[key] : (I18N.en[key] || key);
}

function applyStaticI18n() {
  document.documentElement.lang = LANG;
  document.title = t("title");
  // The textarea label lives on the hand-styled outlined field box.
  const label = document.querySelector('.field-box .flt-label');
  if (label) label.textContent = t("label_type_here");
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  // Accessible names for the icon-only buttons.
  const ariaMap = [
    ["settings-btn", "settings_title"],
    ["clear-btn", "clear_label"],
    ["nav-left", "prev_label"],
    ["nav-right", "next_label"],
  ];
  for (const [id, key] of ariaMap) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("aria-label", t(key));
  }
}

/* --- Token: URL query > localStorage > null --- */
const STORAGE_KEY = "input-from-web-token";
let token = new URLSearchParams(location.search).get("token");
if (token) {
  localStorage.setItem(STORAGE_KEY, token);
} else {
  token = localStorage.getItem(STORAGE_KEY);
}

const txt = document.getElementById("txt");
const btn = document.getElementById("btn");
const btnIcon = btn.querySelector('m3e-icon[slot="icon"]');
const btnLabel = btn.querySelector(".btn-label");
const clearBtn = document.getElementById("clear-btn");
const navLeft = document.getElementById("nav-left");
const navRight = document.getElementById("nav-right");
const navInfo = document.getElementById("nav-info");

// The centered nav slot shows the live character count while there is input,
// otherwise it falls back to the history navigation position ("pos / total").
function updateNavInfo() {
  if (txt.value.length > 0) {
    navInfo.textContent = txt.value.length + " " + t("char_count_label");
    return;
  }
  if (history.length > 0) {
    const pos = histIdx < history.length ? histIdx + 1 : history.length + 1;
    navInfo.textContent = pos + " / " + (history.length + 1);
  } else {
    navInfo.textContent = "";
  }
}

// m3e-button has no `icon` JS property — update the slotted <m3e-icon>'s `name` instead.
function setBtnIcon(name) {
  if (btnIcon) btnIcon.setAttribute("name", name);
}

// Set the text label and make it visible.
function setBtnLabel(text) {
  btnLabel.textContent = text;
  btnLabel.style.display = "";
}

// Expressive swap: current icon flies out (clipped by the button wrapper),
// then the new icon flies in. Falls back to an instant swap without motion.
function setBtnIconAnimated(name) {
  if (!btnIcon || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    setBtnIcon(name);
    return;
  }
  btnIcon.classList.remove("fly-in", "fly-out");
  // Force a style flush so re-adding the class restarts the animation.
  void btnIcon.offsetWidth;
  btnIcon.classList.add("fly-out");
  btnIcon.addEventListener("animationend", () => {
    setBtnIcon(name);
    btnIcon.classList.remove("fly-out");
    void btnIcon.offsetWidth;
    btnIcon.classList.add("fly-in");
  }, { once: true });
}

btn.addEventListener("click", doSend);
clearBtn.addEventListener("click", clearText);
navLeft.addEventListener("click", histBack);
navRight.addEventListener("click", histForward);

/* --- History --- */
const history = [];
let histIdx = 0;
let draft = "";

function updateNav() {
  navLeft.disabled = (histIdx === 0 && history.length === 0) || histIdx === 0;
  navRight.disabled = histIdx >= history.length;
  updateNavInfo();
}

function histBack() {
  if (histIdx <= 0) return;
  if (histIdx === history.length) draft = txt.value;
  histIdx--;
  txt.value = history[histIdx];
  txt.focus();
  updateNavInfo();
  updateNav();
}

function histForward() {
  if (histIdx >= history.length) return;
  histIdx++;
  txt.value = histIdx < history.length ? history[histIdx] : draft;
  txt.focus();
  updateNavInfo();
  updateNav();
}

updateNav();

/* --- Substitutions --- */
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const subEntries = Object.entries(CONFIG.substitutions || {})
  .sort((a, b) => b[0].length - a[0].length);

function applySubstitutions() {
  let text = txt.value;
  let changed = false;
  for (const [phrase, replacement] of subEntries) {
    const re = new RegExp("(^|\\s)" + escapeRegex(phrase) + "(?=\\s|$)", "gi");
    if (re.test(text)) {
      text = text.replace(re, function(m, before) { return before + replacement; });
      changed = true;
    }
  }
  if (changed) {
    const pos = txt.selectionStart;
    const diff = txt.value.length - text.length;
    txt.value = text;
    txt.selectionStart = txt.selectionEnd = Math.max(0, pos - diff);
  }
}

/* --- Voice send --- */
let voiceTimer = null;

function checkVoiceCommand() {
  const vs = CONFIG.voice_send;
  if (!vs || !vs.enabled) return;
  if (voiceTimer) { clearTimeout(voiceTimer); voiceTimer = null; }

  const text = txt.value.trimEnd();
  if (!text) return;

  const words = text.split(/\s+/);
  const lastWord = words[words.length - 1].toLowerCase();

  const sendWords = (vs.send_words || []).concat("发送").map(w => w.toLowerCase());
  const clearWords = (vs.clear_words || []).concat("清除").map(w => w.toLowerCase());

  let action = null;
  if (sendWords.includes(lastWord)) action = "send";
  else if (clearWords.includes(lastWord)) action = "clear";

  if (action) {
    const delay = (vs.delay_seconds || 1.5) * 1000;
    voiceTimer = setTimeout(() => {
      voiceTimer = null;
      const re = new RegExp("\\s*" + escapeRegex(lastWord) + "\\s*$", "i");
      txt.value = txt.value.replace(re, "");
      if (action === "send") doSend();
      else clearText();
    }, delay);
  }
}

txt.addEventListener("input", () => {
  applySubstitutions();
  checkVoiceCommand();
  updateNavInfo();
});

/* --- Actions --- */

function clearText() {
  txt.value = "";
  updateNavInfo();
  txt.focus();
}

async function doSend() {
  const text = txt.value;
  if (!text) return;
  isSending = true;
  transient = false;
  updateButtonState();
  try {
    const res = await fetch("/send?token=" + encodeURIComponent(token), {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: text})
    });
    if (res.ok) {
      history.push(text);
      histIdx = history.length;
      draft = "";
      txt.value = "";
      updateNavInfo();
      updateNav();
      // 已进入“已发送”状态：立即结束 sending，并用 transient 锁定显示，
      // 避免下方每秒一次的 ping 刷新把“已发送！”覆盖回“发送中…”。
      isSending = false;
      transient = true;
      setBtnIconAnimated("check");
      setBtnLabel(t("sent"));
      setTimeout(() => {
        transient = false;
        updateButtonState();
      }, 800);
      txt.focus();
    } else {
      isSending = false;
      transient = true;
      setBtnIcon("error");
      setBtnLabel(t("error_status") + res.status);
      setTimeout(() => {
        transient = false;
        updateButtonState();
      }, 2000);
    }
  } catch(e) {
    isSending = false;
    transient = true;
    setBtnIcon("error");
    setBtnLabel(t("network_error"));
    setTimeout(() => {
      transient = false;
      updateButtonState();
    }, 2000);
  }
}

/* --- Connection State --- */
let isConnected = false;
let isSending = false;
let transient = false;   // 发送成功/失败的短暂提示阶段，期间不被 ping 刷新覆盖

function updateButtonState() {
  if (isSending) {
    btn.disabled = true;
    setBtnIcon("hourglass_empty");
    setBtnLabel(t("sending"));
  } else if (transient) {
    // 成功/失败提示阶段：保留 setBtnLabel/setBtnIcon 已写入的内容，
    // 不被每秒一次的 ping（updateButtonState）覆盖回上一个状态。
    btn.disabled = true;
  } else if (!isConnected) {
    btn.disabled = true;
    setBtnIcon("wifi_off");
    setBtnLabel(t("offline"));
  } else {
    btn.disabled = false;
    setBtnIcon("send");
    setBtnLabel(t("send"));
  }
}

setInterval(async () => {
  try {
    const r = await fetch("/ping", {signal: AbortSignal.timeout(3000)});
    isConnected = r.ok;
  } catch(e) {
    isConnected = false;
  }
  updateButtonState();
}, 1000);

updateButtonState();
updateNavInfo();

/* --- Autostart toggle --- */
const autostartSwitch = document.getElementById("autostart-switch");

async function refreshAutostart() {
  try {
    const r = await fetch("/autostart?token=" + encodeURIComponent(token));
    if (r.ok) {
      const data = await r.json();
      autostartSwitch.checked = !!data.installed;
    }
  } catch (e) { /* ignore */ }
}

autostartSwitch.addEventListener("change", async () => {
  const want = autostartSwitch.checked;
  const action = want ? "install" : "uninstall";
  autostartSwitch.disabled = true;
  try {
    const r = await fetch("/autostart?token=" + encodeURIComponent(token), {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({action: action}),
    });
    if (r.ok) {
      const data = await r.json();
      if (data.ok) {
        window.M3eSnackbar.open(want ? t("autostart_on") : t("autostart_off"));
      } else {
        autostartSwitch.checked = !want;
        window.M3eSnackbar.open(t("autostart_fail") + (data.message || ""));
      }
    } else {
      autostartSwitch.checked = !want;
      window.M3eSnackbar.open(t("autostart_err") + r.status);
    }
  } catch (e) {
    autostartSwitch.checked = !want;
    window.M3eSnackbar.open(t("autostart_neterr"));
  } finally {
    autostartSwitch.disabled = false;
  }
});

refreshAutostart();

/* --- Settings toggles (unified) ---
   Each switch flips a profile field at runtime via /settings.
   `boolFields` send a boolean; `mapFields` translate on/off to a string. */
const methodSwitch = document.getElementById("method-switch");
const autoPasteSwitch = document.getElementById("auto-paste-switch");
const pasteKeySwitch = document.getElementById("paste-key-switch");
const enterSwitch = document.getElementById("enter-switch");
const voiceSwitch = document.getElementById("voice-switch");
const tokenSwitch = document.getElementById("token-switch");

// Switches whose effect only makes sense in clipboard mode.
const methodDependent = [autoPasteSwitch, pasteKeySwitch];

function syncMethodDependent() {
  const isClipboard = methodSwitch.checked;
  for (const sw of methodDependent) {
    sw.disabled = !isClipboard;
    sw.closest(".autostart-row").style.opacity = isClipboard ? "1" : "0.4";
  }
}

// Generic toggle handler: builds the POST body from `want`, shows the right
// snackbar, and reverts the switch on any failure.
function wireToggle(sw, bodyFn, okMsgFn) {
  sw.addEventListener("change", async () => {
    const want = sw.checked;
    sw.disabled = true;
    try {
      const r = await fetch("/settings?token=" + encodeURIComponent(token), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(bodyFn(want)),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok && !data.error) {
        window.M3eSnackbar.open(okMsgFn(want));
        if (sw === methodSwitch) syncMethodDependent();
      } else {
        sw.checked = !want;
        window.M3eSnackbar.open(t("autostart_err") + (data.error || r.status));
      }
    } catch (e) {
      sw.checked = !want;
      window.M3eSnackbar.open(t("autostart_neterr"));
    } finally {
      sw.disabled = false;
    }
  });
}

wireToggle(methodSwitch,
  (want) => ({method: want ? "clipboard" : "type"}),
  (want) => want ? t("method_on") : t("method_off"));

wireToggle(autoPasteSwitch,
  (want) => ({auto_paste: want}),
  (want) => want ? t("auto_paste_on") : t("auto_paste_off"));

wireToggle(pasteKeySwitch,
  (want) => ({paste_key: want ? "ctrl+shift+v" : "ctrl+v"}),
  (want) => want ? t("paste_key_on") : t("paste_key_off"));

wireToggle(enterSwitch,
  (want) => ({auto_press_enter: want}),
  (want) => want ? t("enter_on") : t("enter_off"));

wireToggle(voiceSwitch,
  (want) => ({voice_send_enabled: want}),
  (want) => want ? t("voice_on") : t("voice_off"));

wireToggle(tokenSwitch,
  (want) => ({use_security_token: want}),
  (want) => want ? t("token_on") : t("token_off"));

/* Pull the live state of every toggle from the server (reflects CLI/profile
   overrides too) so the sheet always shows the truth. */
async function refreshSettings() {
  try {
    const r = await fetch("/settings?token=" + encodeURIComponent(token));
    if (r.ok) {
      const d = await r.json();
      methodSwitch.checked = d.method === "clipboard";
      autoPasteSwitch.checked = !!d.auto_paste;
      pasteKeySwitch.checked = d.paste_key === "ctrl+shift+v";
      enterSwitch.checked = !!d.auto_press_enter;
      voiceSwitch.checked = !!d.voice_send_enabled;
      tokenSwitch.checked = !!d.use_security_token;
      syncMethodDependent();
    }
  } catch (e) { /* ignore */ }
}

refreshSettings();

/* --- Settings bottom sheet --- */
const settingsBtn = document.getElementById("settings-btn");
const settingsSheet = document.getElementById("settings-sheet");
const toggleSettings = (open) => {
  if (open) settingsSheet.show();
  else settingsSheet.hide();
  settingsBtn.setAttribute("aria-expanded", String(!!open));
};
settingsBtn.addEventListener("click", () => toggleSettings(true));
settingsSheet.addEventListener("opened", () => settingsBtn.setAttribute("aria-expanded", "true"));
settingsSheet.addEventListener("closed", () => settingsBtn.setAttribute("aria-expanded", "false"));

/* --- Language selector (connected button group inside the settings sheet) --- */
const langGroup = document.getElementById("lang-group");
// Mark the button matching the resolved UI language as selected (single-select,
// so every other button is explicitly unselected too).
function syncLangGroup() {
  for (const btn of langGroup.querySelectorAll("m3e-button")) {
    btn.selected = (btn.dataset.lang === LANG);
  }
}
// m3e-button-group listens to its children's `change` and keeps a single
// selection in non-multi mode; we just read back which one is now selected.
langGroup.addEventListener("change", () => {
  for (const btn of langGroup.querySelectorAll("m3e-button")) {
    if (btn.selected) {
      LANG = btn.dataset.lang;
      break;
    }
  }
  localStorage.setItem(LANG_STORAGE_KEY, LANG);
  applyStaticI18n();
  updateButtonState();
});
syncLangGroup();

/* --- Theme selector (light / dark / auto, follows the OS) ---
   Purely a UI preference, persisted in localStorage (no server round-trip). */
const THEME_STORAGE_KEY = "input-from-web-theme";
const themeGroup = document.getElementById("theme-group");
const themeMeta = document.querySelector('meta[name="theme-color"]');

function resolvedThemeIsDark(theme) {
  if (theme === "dark") return true;
  if (theme === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

// Apply a theme: toggle the data-theme attribute, the native color-scheme, and
// the mobile browser-chrome theme-color meta so everything matches.
function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "auto") {
    root.removeAttribute("data-theme");
    root.style.colorScheme = "light dark";
  } else {
    root.setAttribute("data-theme", theme);
    root.style.colorScheme = theme;
  }
  // Let <m3e-theme> generate the matching light/dark token set.
  if (appTheme) appTheme.scheme = theme;
  if (themeMeta) {
    const lightMeta = (themeColor && themeColor !== "material") ? themeColor : "#6750A4";
    themeMeta.setAttribute("content", resolvedThemeIsDark(theme) ? "#1a1a1a" : lightMeta);
  }
}

function syncThemeGroup() {
  for (const btn of themeGroup.querySelectorAll("m3e-button")) {
    btn.selected = (btn.dataset.theme === THEME);
  }
}

themeGroup.addEventListener("change", () => {
  for (const btn of themeGroup.querySelectorAll("m3e-button")) {
    if (btn.selected) {
      THEME = btn.dataset.theme;
      break;
    }
  }
  localStorage.setItem(THEME_STORAGE_KEY, THEME);
  applyTheme(THEME);
});

// Re-evaluate "auto" when the OS theme changes (only matters while in auto mode).
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (THEME === "auto") applyTheme("auto");
});

let THEME = localStorage.getItem(THEME_STORAGE_KEY) || "auto";
const THEME_COLOR_KEY = "input-from-web-theme-color";
let themeColor = localStorage.getItem(THEME_COLOR_KEY) || "material";
applyTheme(THEME);
syncThemeGroup();

/* --- Accent color (theme color) ---
   A grid of preset default colors plus a "Material" option that restores the
   system Material baseline palette. The full palette is derived from the seed
   color by <m3e-theme> (see applyThemeColor). */
const PRESET_COLORS = ["#6750A4", "#4F6FED", "#2E7D32", "#E53935", "#FF6600", "#00897B"];
const themeColorGrid = document.getElementById("theme-color-grid");
const themeMaterialBtn = document.getElementById("theme-material-btn");

// Apply a custom accent (hex) or fall back to the Material baseline ("material").
// The full primary/secondary/tertiary/neutral/surface palette is generated by
// <m3e-theme> from the seed color, so we only need to feed it the seed.
function applyThemeColor(color) {
  if (!appTheme) return;
  if (!color || color === "material") {
    appTheme.color = "#6750A4"; // Material default seed
  } else {
    appTheme.color = color;
  }
}

function syncThemeColorUI() {
  for (const sw of themeColorGrid.querySelectorAll(".swatch")) {
    sw.classList.toggle("selected", sw.dataset.color === themeColor);
  }
  themeMaterialBtn.selected = (themeColor === "material");
}

// Build the preset swatch grid from PRESET_COLORS.
for (const color of PRESET_COLORS) {
  const b = document.createElement("button");
  b.className = "swatch";
  b.dataset.color = color;
  b.style.background = color;
  b.setAttribute("aria-label", color);
  b.addEventListener("click", () => {
    themeColor = color;
    localStorage.setItem(THEME_COLOR_KEY, themeColor);
    applyThemeColor(themeColor);
    syncThemeColorUI();
    applyTheme(THEME); // refresh browser-chrome theme-color meta
  });
  themeColorGrid.appendChild(b);
}
themeMaterialBtn.addEventListener("change", () => {
  if (themeMaterialBtn.selected) {
    themeColor = "material";
    localStorage.setItem(THEME_COLOR_KEY, themeColor);
    applyThemeColor(themeColor);
    syncThemeColorUI();
    applyTheme(THEME);
  }
});

applyThemeColor(themeColor);
syncThemeColorUI();

applyStaticI18n();
updateButtonState();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}
