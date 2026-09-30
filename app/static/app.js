// Small helpers. The panel works without JavaScript too.
document.addEventListener("DOMContentLoaded", () => {
  // Filters that submit when changed
  document.querySelectorAll("select[data-autosubmit]").forEach((el) =>
    el.addEventListener("change", () => el.form.submit())
  );
  // "Are you sure?" before cancelling
  document.querySelectorAll("form[data-confirm]").forEach((f) =>
    f.addEventListener("submit", (e) => {
      if (!window.confirm(f.dataset.confirm)) e.preventDefault();
    })
  );
  // Copy buttons
  document.querySelectorAll("[data-copy]").forEach((b) =>
    b.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        await navigator.clipboard.writeText(b.dataset.copy);
        const old = b.textContent;
        b.textContent = "کپی شد ✓";
        setTimeout(() => (b.textContent = old), 1500);
      } catch (_) { /* clipboard not allowed; the text is visible to copy by hand */ }
    })
  );
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
