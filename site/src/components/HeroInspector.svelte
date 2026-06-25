<script lang="ts">
  // A faux page being annotated by frontprompt: a pick (accent, with corner
  // handles + selector readout), a region marquee (magenta), and a relation
  // line drawn between them. Pure CSS/SVG, decorative.
</script>

<div class="frame" aria-hidden="true">
  <div class="chrome">
    <span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
    <span class="url">example.com</span>
    <span class="badge">frontprompt · live</span>
  </div>

  <div class="canvas">
    <!-- faux page content -->
    <div class="row title"></div>
    <div class="row w70"></div>
    <div class="row w55"></div>

    <!-- a PICK -->
    <div class="pick">
      <div class="bar"></div>
      <span class="handle tl"></span><span class="handle tr"></span>
      <span class="handle bl"></span><span class="handle br"></span>
      <span class="tag pick-tag">button.cta · pick&nbsp;#1</span>
    </div>

    <div class="row w60"></div>

    <!-- a REGION -->
    <div class="region">
      <div class="row w80 ghost"></div>
      <div class="row w65 ghost"></div>
      <span class="tag region-tag">region · pricing</span>
    </div>

    <!-- relation line: pick → region, hugging the left edge, ending AT the
         region's top border (never slashing across the box) -->
    <svg class="relation" viewBox="0 0 100 100" preserveAspectRatio="none">
      <path d="M16 33 C 10 42, 11 49, 17 55" />
    </svg>
    <span class="tag rel-tag">relation: drives</span>
  </div>
</div>

<style>
  .frame {
    position: relative;
    border: 1px solid var(--line-strong);
    border-radius: var(--radius);
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    box-shadow:
      0 1px 0 rgba(255, 255, 255, 0.03) inset,
      0 40px 90px -40px rgba(0, 0, 0, 0.9),
      0 0 0 1px rgba(91, 157, 255, 0.06);
    overflow: hidden;
    transform: perspective(1400px) rotateY(-10deg) rotateX(3deg);
    transform-origin: center right;
  }

  .chrome {
    display: flex;
    align-items: center;
    gap: 0.5ch;
    padding: 0.7rem 0.9rem;
    border-bottom: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.015);
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    display: inline-block;
  }
  .dot.r {
    background: #ff5f57;
  }
  .dot.y {
    background: #febc2e;
  }
  .dot.g {
    background: #28c840;
  }
  .url {
    margin-left: 0.8ch;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--text-mute);
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 0.2em 0.9em;
  }
  .badge {
    margin-left: auto;
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--accent);
  }

  .canvas {
    position: relative;
    padding: 1.5rem 1.4rem 2.2rem;
    min-height: 320px;
  }
  .row {
    height: 12px;
    border-radius: 6px;
    background: rgba(148, 163, 184, 0.12);
    margin: 0.7rem 0;
  }
  .row.title {
    height: 20px;
    width: 52%;
    background: rgba(148, 163, 184, 0.22);
  }
  .w55 {
    width: 55%;
  }
  .w60 {
    width: 60%;
  }
  .w65 {
    width: 65%;
  }
  .w70 {
    width: 70%;
  }
  .w80 {
    width: 80%;
  }
  .ghost {
    opacity: 0.55;
  }

  /* PICK selection box */
  .pick {
    position: relative;
    margin: 1.3rem 0;
    padding: 0.55rem 0.7rem;
    border: 1.5px dashed var(--accent);
    border-radius: 7px;
    background: var(--accent-subtle);
    width: 46%;
    animation: breathe 3.6s ease-in-out infinite;
  }
  .pick .bar {
    height: 14px;
    border-radius: 5px;
    background: linear-gradient(90deg, var(--accent), var(--accent-deep));
    width: 64%;
  }
  .handle {
    position: absolute;
    width: 7px;
    height: 7px;
    background: var(--bg);
    border: 1.5px solid var(--accent);
    border-radius: 1px;
  }
  .handle.tl {
    top: -4px;
    left: -4px;
  }
  .handle.tr {
    top: -4px;
    right: -4px;
  }
  .handle.bl {
    bottom: -4px;
    left: -4px;
  }
  .handle.br {
    bottom: -4px;
    right: -4px;
  }

  /* REGION marquee */
  .region {
    position: relative;
    margin-top: 1.5rem;
    padding: 0.9rem 0.8rem 1.1rem;
    border: 1.5px dashed var(--select);
    border-radius: 7px;
    background: var(--select-soft);
    width: 72%;
  }

  /* floating mono readouts */
  .tag {
    position: absolute;
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.03em;
    white-space: nowrap;
    padding: 0.18em 0.5em;
    border-radius: 4px;
    color: #06101f;
  }
  .pick-tag {
    top: -0.95rem;
    left: -0.1rem;
    background: var(--accent);
  }
  .region-tag {
    top: -0.95rem;
    right: -0.1rem;
    background: var(--select);
    color: #1a0510;
    color: #fff;
  }
  .rel-tag {
    top: 47%;
    left: 1.1rem;
    background: var(--panel);
    color: var(--accent-bright);
    border: 1px solid rgba(91, 157, 255, 0.4);
  }

  .relation {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }
  .relation path {
    fill: none;
    stroke: var(--accent);
    stroke-width: 0.5;
    stroke-dasharray: 2 1.6;
    opacity: 0.7;
    animation: flow 1.6s linear infinite;
  }

  @keyframes breathe {
    0%,
    100% {
      box-shadow: 0 0 0 0 var(--accent-subtle);
    }
    50% {
      box-shadow: 0 0 0 4px var(--accent-subtle);
    }
  }
  @keyframes flow {
    to {
      stroke-dashoffset: -7.2;
    }
  }

  @media (max-width: 900px) {
    .frame {
      transform: none;
    }
  }
</style>
