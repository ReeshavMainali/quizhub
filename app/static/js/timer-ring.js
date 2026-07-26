/**
 * Drives an SVG countdown ring. Expects markup like:
 *   <svg><circle class="ring-track" .../><circle class="ring-progress" .../></svg>
 *   <span class="ring-label"></span>
 * Server state is authoritative (duration/remaining/status); between updates
 * this animates smoothly on the client via requestAnimationFrame.
 */
class TimerRing {
  constructor(svgEl, labelEl, radius) {
    this.svg = svgEl;
    this.label = labelEl;
    this.radius = radius;
    this.circumference = 2 * Math.PI * radius;
    this.circle = svgEl.querySelector(".ring-progress");
    this.circle.style.strokeDasharray = `${this.circumference}`;
    this.duration = 0;
    this.remaining = 0;
    this.status = "stopped";
    this.raf = null;
  }

  set(duration, remaining, status) {
    cancelAnimationFrame(this.raf);
    this.duration = duration || 0;
    this.remaining = remaining == null ? 0 : remaining;
    this.status = status;
    this._render();
    if (status === "running") this._tick();
  }

  _tick() {
    const start = performance.now();
    const startRemaining = this.remaining;
    const step = (now) => {
      const elapsed = (now - start) / 1000;
      this.remaining = Math.max(0, startRemaining - elapsed);
      this._render();
      if (this.remaining > 0 && this.status === "running") {
        this.raf = requestAnimationFrame(step);
      }
    };
    this.raf = requestAnimationFrame(step);
  }

  _render() {
    const frac = this.duration ? Math.max(0, Math.min(1, this.remaining / this.duration)) : 0;
    const offset = this.circumference * (1 - frac);
    this.circle.style.strokeDashoffset = offset;
    if (this.label) this.label.textContent = Math.ceil(this.remaining);

    const urgent = this.remaining <= 5 && this.remaining > 0 && this.status === "running";
    this.circle.classList.toggle("stroke-lightning", urgent);
    this.circle.classList.toggle("stroke-primary", !urgent);
    this.svg.classList.toggle("animate-ring-urgent", urgent);
  }

  stop() {
    cancelAnimationFrame(this.raf);
  }
}
