# services/color-palette

32-color rainbow palette für visual identity von Picks + Regions. Index → CSS color string. Konsumiert vom svg-renderer (rect-borders), PickItem (color-dot), RegionItem (color-icon).

| Export           | Signature                         | Beschreibung                                                                                   |
| ---------------- | --------------------------------- | ---------------------------------------------------------------------------------------------- |
| `colorForIndex`  | `(idx: number) → string`          | Index → CSS-string (`hsl(...)`). Negative input → clamped, out-of-range → modulo PALETTE_SIZE. |
| `nextColorIndex` | `(currentCount: number) → number` | Helper für submit-time: gibt next palette-index zurück (modulo wrap).                          |
| `PALETTE`        | `readonly string[]`               | Eager array — useful für debug-swatch-rendering.                                               |
| `PALETTE_SIZE`   | `const number`                    | 32.                                                                                            |

## Construction

```
32 distinct HSL-tuples =
   hue via 5-bit bit-reversal (van-der-Corput-like)
   ×  4 lightness-groups (62, 50, 70, 42)
   = maximum contrast für adjacent indices
```

**Hue (bit-reversed)**:

```
idx  0 →  hue   0°   (bitReverse(0)=0)
idx  1 →  hue 180°   (bitReverse(1)=16)
idx  2 →  hue  90°   (bitReverse(2)=8)
idx  3 →  hue 270°   (bitReverse(3)=24)
idx  4 →  hue  45°   (bitReverse(4)=4)
idx  5 →  hue 225°   (bitReverse(5)=20)
...
```

Adjacent indices kriegen MAX entfernte hues → die ersten paar picks sehen sofort distinct aus, nicht "langsam durchs Spektrum wandern".

**Lightness-Gruppen (pro 8er-Block rotierend)**:

```
idx 0..7   →  L = 62%
idx 8..15  →  L = 50%
idx 16..23 →  L = 70%
idx 24..31 →  L = 42%
```

Saturation konstant 78% (kräftig genug für "Farbe ist Identität"-signal, nicht neon).

## Usage

Capture-time (in submitPick/submitRegion):

```ts
const colorIndex = nextColorIndex(this.picks.length);
this.picks = [...this.picks, { ...pick, color_index: colorIndex }];
```

Render-time:

```ts
const stroke = colorForIndex(pick.color_index ?? 0);
// fallback 0 für schema-pre-0.5.0 snapshots
```

## Wrap behavior

Modulo PALETTE_SIZE. 33ster pick reuses index 0 farbe. Keine warning — bei >32 items per session ist farbe-codierung sowieso nicht mehr nützlich.

## Cross-refs

- Schema 0.5.0+: `Pick.color_index` + `Region.color_index` (Pydantic state.py)
- svg-renderer: inline-style `stroke: ${colorForIndex(item.color_index)}`
