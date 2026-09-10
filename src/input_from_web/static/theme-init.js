(function () {
    try {
      var th = localStorage.getItem("input-from-web-theme") || "auto";
      var root = document.documentElement;
      if (th === "dark") { root.setAttribute("data-theme", "dark"); root.style.colorScheme = "dark"; }
      else if (th === "light") { root.setAttribute("data-theme", "light"); root.style.colorScheme = "light"; }
      else { root.style.colorScheme = "light dark"; }
      // Pre-apply the saved accent's primary pair so it doesn't flash to the
      // default Material purple before <m3e-theme> upgrades and takes over.
      var tc = localStorage.getItem("input-from-web-theme-color");
      if (tc && tc !== "material") {
        var hx = tc.replace("#", "");
        var r = parseInt(hx.slice(0, 2), 16), g = parseInt(hx.slice(2, 4), 16), b = parseInt(hx.slice(4, 6), 16);
        var f = function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        var L = 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
        root.style.setProperty("--md-sys-color-primary", tc);
        root.style.setProperty("--md-sys-color-on-primary", L > 0.4 ? "#1d1b20" : "#ffffff");
      }
    } catch (e) {}
  })();
