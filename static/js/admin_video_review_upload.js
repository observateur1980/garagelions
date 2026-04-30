(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function fmtBytes(b) {
    if (!isFinite(b) || b < 0) return "0 B";
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
    return b.toFixed(b < 10 && i > 0 ? 1 : 0) + " " + u[i];
  }

  function fmtTime(s) {
    if (!isFinite(s) || s < 0) return "—";
    s = Math.round(s);
    if (s < 60) return s + "s";
    const m = Math.floor(s / 60);
    const r = s % 60;
    if (m < 60) return m + "m " + r + "s";
    const h = Math.floor(m / 60);
    return h + "h " + (m % 60) + "m";
  }

  function buildOverlay() {
    const wrap = document.createElement("div");
    wrap.className = "vr-upload-overlay";
    wrap.innerHTML = `
      <div class="vr-upload-card">
        <div class="vr-upload-head">
          <div class="vr-upload-title">Uploading video review</div>
          <div class="vr-upload-pct">0%</div>
        </div>
        <div class="vr-upload-file" data-file>—</div>
        <div class="vr-upload-bar"><div class="vr-upload-fill" data-fill></div></div>
        <div class="vr-upload-stats">
          <span data-loaded>0 B</span>
          <span data-total>/ 0 B</span>
          <span class="vr-sep">•</span>
          <span data-speed>— /s</span>
          <span class="vr-sep">•</span>
          <span data-eta>ETA —</span>
        </div>
        <div class="vr-upload-status" data-status>Preparing upload…</div>
      </div>
    `;
    document.body.appendChild(wrap);
    return {
      root: wrap,
      pct: wrap.querySelector(".vr-upload-pct"),
      fill: wrap.querySelector("[data-fill]"),
      file: wrap.querySelector("[data-file]"),
      loaded: wrap.querySelector("[data-loaded]"),
      total: wrap.querySelector("[data-total]"),
      speed: wrap.querySelector("[data-speed]"),
      eta: wrap.querySelector("[data-eta]"),
      status: wrap.querySelector("[data-status]"),
    };
  }

  function findVideoForm() {
    // VideoReview admin add/change page form
    const form = document.getElementById("videoreview_form");
    if (!form) return null;
    const fileInput = form.querySelector('input[type="file"][name="video"]');
    if (!fileInput) return null;
    return { form, fileInput };
  }

  function attach(form, fileInput) {
    let clickedSubmitter = null;
    form.querySelectorAll('input[type="submit"], button[type="submit"]').forEach(btn => {
      btn.addEventListener("click", () => { clickedSubmitter = btn; });
    });

    form.addEventListener("submit", function (e) {
      // Only intercept when a new video file is actually selected
      if (!fileInput.files || fileInput.files.length === 0) return;

      e.preventDefault();

      const ui = buildOverlay();
      const file = fileInput.files[0];
      ui.file.textContent = file.name + " (" + fmtBytes(file.size) + ")";
      ui.total.textContent = "/ " + fmtBytes(file.size);

      const fd = new FormData(form);
      const submitter = e.submitter || clickedSubmitter;
      if (submitter && submitter.name) {
        fd.set(submitter.name, submitter.value || "");
      }

      const xhr = new XMLHttpRequest();
      const action = form.getAttribute("action") || window.location.href;
      const startedAt = performance.now();
      let lastT = startedAt;
      let lastLoaded = 0;
      let smoothedSpeed = 0;

      xhr.upload.addEventListener("progress", function (ev) {
        if (!ev.lengthComputable) {
          ui.status.textContent = "Uploading…";
          return;
        }
        const pct = (ev.loaded / ev.total) * 100;
        ui.pct.textContent = Math.floor(pct) + "%";
        ui.fill.style.width = pct.toFixed(2) + "%";
        ui.loaded.textContent = fmtBytes(ev.loaded);

        const now = performance.now();
        const dt = (now - lastT) / 1000;
        if (dt > 0.25) {
          const inst = (ev.loaded - lastLoaded) / dt;
          smoothedSpeed = smoothedSpeed ? smoothedSpeed * 0.7 + inst * 0.3 : inst;
          lastT = now;
          lastLoaded = ev.loaded;
          ui.speed.textContent = fmtBytes(smoothedSpeed) + "/s";
          const remaining = ev.total - ev.loaded;
          const eta = smoothedSpeed > 0 ? remaining / smoothedSpeed : Infinity;
          ui.eta.textContent = "ETA " + fmtTime(eta);
        }

        ui.status.textContent = pct >= 100 ? "Processing on server…" : "Uploading…";
      });

      xhr.addEventListener("load", function () {
        ui.fill.style.width = "100%";
        ui.pct.textContent = "100%";
        const finalUrl = xhr.responseURL || "";
        const submitUrl = new URL(action, window.location.href).href;

        if (xhr.status >= 200 && xhr.status < 400 && finalUrl && finalUrl !== submitUrl) {
          // server redirected → save succeeded, follow the redirect
          ui.status.textContent = "Saved. Redirecting…";
          window.location.href = finalUrl;
        } else if (xhr.status >= 200 && xhr.status < 400) {
          // form re-rendered (validation errors) — replace page with response
          ui.status.textContent = "Server returned a response, reloading…";
          document.open();
          document.write(xhr.responseText);
          document.close();
        } else {
          ui.root.classList.add("is-error");
          ui.status.textContent = "Upload failed (HTTP " + xhr.status + "). Please try again.";
        }
      });

      xhr.addEventListener("error", function () {
        ui.root.classList.add("is-error");
        ui.status.textContent = "Network error during upload. Please try again.";
      });

      xhr.addEventListener("abort", function () {
        ui.root.classList.add("is-error");
        ui.status.textContent = "Upload cancelled.";
      });

      // Disable submit buttons while in flight
      form.querySelectorAll('input[type="submit"], button[type="submit"]').forEach(b => b.disabled = true);

      xhr.open(form.getAttribute("method") || "POST", action, true);
      xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      xhr.send(fd);
    });
  }

  ready(function () {
    const found = findVideoForm();
    if (!found) return;
    attach(found.form, found.fileInput);
  });
})();
