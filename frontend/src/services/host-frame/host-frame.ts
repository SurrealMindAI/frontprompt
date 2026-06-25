/**
 * host-frame — rückt den Host-Seiten-Inhalt in den minimierten Overlay-Rahmen ein.
 *
 * Service-zweck: Standardmäßig schwebt das Overlay (``position:fixed; inset:0``)
 * nur ÜBER der Seite. Damit der echte Seiteninhalt VOM Overlay umrahmt ("gewrapped")
 * wird, rücken wir ``<html>`` um die minimierten Panel-Margins ein — der Inhalt
 * fließt responsiv in das innere Rechteck um (Reflow, pixel-scharf, kein Skalieren).
 *
 * Der Inset ist KONSTANT: er entspricht den ``tabThickness``-Werten der vier Panels,
 * die in JEDEM Panel-Zustand als Laschen sichtbar bleiben (offen, collapsed, hide-all,
 * inspector-/region-force-collapse). Panel-EXPANSION schiebt den Inhalt deshalb nicht
 * weiter — expandierte Panels legen sich nur über den (konstant eingerückten) Inhalt.
 *
 * Technik: Inline-Style mit ``!important``-Priorität direkt auf ``document.documentElement``.
 * Inline-``!important`` schlägt jedes Author-Stylesheet der Host-Seite (auch deren
 * ``html { padding:0 !important }``) und ist deterministisch — keine Cascade-Race mit
 * asynchron nachgeladenen Site-Styles, wie sie ein injizierter ``<style>``-Tag hätte.
 * ``box-sizing:border-box`` hält die html-Box = Viewport (Content-Box = Inner-Rect) und
 * verhindert horizontalen Überlauf.
 *
 * Bewusst akzeptierte Limitierungen (Reflow-Ansatz): Host-eigene ``position:fixed``/
 * ``sticky``-Elemente und ``100vw``/``100vh``-Layouts ankern am echten Viewport und
 * können über die Rahmenkanten leaken; die native Seiten-Scrollbar bleibt am
 * Viewport-Rand hinter der rechten Lasche (Wheel-/Keyboard-Scroll bleibt normal).
 */

import { PANEL_CONFIGS } from '../../backend-state/panel-state.svelte';

export interface FrameInsets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/**
 * Konstanter Frame-Inset, abgeleitet aus den Panel-``tabThickness``-Werten.
 * DRY: ``PANEL_CONFIGS`` bleibt die einzige Quelle für die minimierten Margins —
 * ändert sich dort eine ``tabThickness``, wandert der Wert automatisch hierher.
 */
export const FRAME_INSETS: FrameInsets = {
  top: PANEL_CONFIGS.top.tabThickness,
  right: PANEL_CONFIGS.right.tabThickness,
  bottom: PANEL_CONFIGS.bottom.tabThickness,
  left: PANEL_CONFIGS.left.tabThickness,
};

const INSET_PROPS = ['box-sizing', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left'];

/**
 * Rückt den Host-Seiten-Inhalt in das innere Rechteck ein. Idempotent — wiederholtes
 * Anwenden überschreibt dieselben Deklarationen. Wird in ``main.ts`` beim Mount
 * (nach jedem Dokument-Load inkl. Cross-Origin-Navigation) aufgerufen.
 */
export function applyHostFrameInset(insets: FrameInsets = FRAME_INSETS): void {
  const el = document.documentElement;
  if (!el) return;
  el.style.setProperty('box-sizing', 'border-box', 'important');
  el.style.setProperty('padding-top', `${insets.top}px`, 'important');
  el.style.setProperty('padding-right', `${insets.right}px`, 'important');
  el.style.setProperty('padding-bottom', `${insets.bottom}px`, 'important');
  el.style.setProperty('padding-left', `${insets.left}px`, 'important');
}

/** Macht {@link applyHostFrameInset} rückgängig (für Teardown/Tests). */
export function removeHostFrameInset(): void {
  const el = document.documentElement;
  if (!el) return;
  for (const prop of INSET_PROPS) {
    el.style.removeProperty(prop);
  }
}
