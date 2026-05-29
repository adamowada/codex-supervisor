# HTML Report Format

In read-only, review-only, audit-only, no-edits, or no-mutation mode, return the proposed report
outline and target path instead of writing the HTML file.

Render architectural reviews as a single static HTML file. In `codex-supervisor` or spawned projects, write reports under `artifacts/architecture-reviews/` so they are ignored by git. If the repo has no ignored artifact path, use the OS temp directory and tell the user the absolute path.

Prefer no external network dependencies. Inline a small CSS layer and use inline SVG or hand-built boxes for diagrams. Mermaid via CDN is acceptable only when graph-shaped diagrams materially improve the report and network access is allowed; note the dependency in the report.

## Scaffold

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Architecture review - {{repo name}}</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f8f7f3;
        --ink: #18202f;
        --muted: #5f6b7a;
        --line: #d8d6ce;
        --accent: #0f766e;
        --warn: #b45309;
        --leak: #dc2626;
      }
      body { margin: 0; background: var(--bg); color: var(--ink); font-family: ui-sans-serif, system-ui, sans-serif; }
      main { max-width: 1100px; margin: 0 auto; padding: 48px 24px; }
      article { border: 1px solid var(--line); background: #fff; padding: 24px; margin: 28px 0; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
      .badge { display: inline-block; border: 1px solid var(--line); padding: 3px 8px; font-size: 12px; text-transform: uppercase; }
      .diagram { min-height: 260px; border: 1px solid var(--line); background: #fbfaf7; padding: 16px; }
      .module { border: 1px solid var(--ink); padding: 10px; margin: 8px; }
      .deep { background: #102a43; color: white; }
      .leak { color: var(--leak); }
    </style>
  </head>
  <body>
    <main>
      <header>...</header>
      <section id="candidates">...</section>
      <section id="top-recommendation">...</section>
    </main>
  </body>
</html>
```

## Header

Repo name, date, source-of-truth files read, and a compact legend: solid box = module, dashed line = seam, red arrow = leakage, dark box = deep module. No introduction paragraph; go straight into candidates.

## Candidate Card

The diagrams carry the weight. Prose is sparse, plain, and uses the glossary terms from [LANGUAGE.md](LANGUAGE.md).

Each candidate is one `<article>`:

- **Title** - short, names the deepening.
- **Badge row** - recommendation strength plus dependency category.
- **Files/modules** - monospaced list.
- **Before / after diagram** - side by side when space allows.
- **Problem** - one sentence.
- **Solution** - one sentence.
- **Wins** - bullets, six words or fewer when possible.
- **Decision callout** - one line when an existing decision is implicated.

No paragraphs of explanation. If the diagram needs a paragraph to be understood, redraw the diagram.

## Diagram Patterns

Pick the pattern that fits the candidate. Mix them.

### Boxes And Arrows

Modules as bordered boxes. Arrows as inline SVG `<line>` or `<path>` elements positioned over a relative container. Use this when the after diagram should feel like one deep module with faded internals.

### Cross-Section

Stack horizontal bands to show layers a call passes through. Before: several thin layers each doing little. After: one thick band labelled with the consolidated responsibility.

### Mass Diagram

Two rectangles per module: one for interface surface area, one for implementation. Before: interface rectangle is nearly as tall as the implementation rectangle. After: interface rectangle is short, implementation rectangle is tall.

### Call-Graph Collapse

Before: a tree of function calls rendered as nested boxes. After: the same tree collapsed into one box, with internal calls faded inside it.

### Mermaid Graph

Use Mermaid only when graph layout or sequence syntax is worth the CDN dependency. If used, include a note in the report header that the file loads Mermaid from the network.

## Style Guidance

- Lean editorial, not dashboard.
- Use generous whitespace and restrained color.
- Use one accent plus red for leakage and amber for warnings.
- Keep diagrams around 320px tall.
- Use module, interface, implementation, depth, deep, shallow, seam, adapter, leverage, and locality.
- Avoid substituting component, service, API, boundary, or wrapper when the glossary term is more precise.

## Top Recommendation

One larger card: candidate name, one sentence on why, and an anchor link to its card.