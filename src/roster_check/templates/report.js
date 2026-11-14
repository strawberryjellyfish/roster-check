// Counts the headline numbers up and starts each chart's animation when it
// scrolls into view. Without this script everything shows its final state.
(() => {
  "use strict";
  document.documentElement.classList.add("js");
  const animated = document.querySelectorAll(".animate");
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) {
    animated.forEach((section) => section.classList.add("in-view"));
    return;
  }
  const counters = [...document.querySelectorAll("[data-value]")].map((element) => ({
    element,
    target: Number(element.dataset.value),
    decimals: Number(element.dataset.decimals),
    finalText: element.textContent,
  }));
  const finish = () => counters.forEach((c) => { c.element.textContent = c.finalText; });
  let start = null;
  const step = (now) => {
    start ??= now;
    const progress = Math.min((now - start) / 900, 1);
    if (progress === 1) return finish();
    const eased = 1 - (1 - progress) ** 3;
    counters.forEach((c) => {
      const options = { minimumFractionDigits: c.decimals, maximumFractionDigits: c.decimals };
      c.element.textContent = (c.target * eased).toLocaleString("en-AU", options);
    });
    requestAnimationFrame(step);
  };
  addEventListener("beforeprint", () => { start = -Infinity; finish(); });
  requestAnimationFrame(step);
  const observer = new IntersectionObserver((entries) => {
    entries.filter((entry) => entry.isIntersecting).forEach((entry) => {
      entry.target.classList.add("in-view");
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.25 });
  animated.forEach((section) => observer.observe(section));
})();
