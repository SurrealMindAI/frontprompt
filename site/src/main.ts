import { mount } from 'svelte';

// Shared frontprompt design tokens (the product's own design system) — primitive
// scale + dark theme. The site layers its own inspector/HUD aesthetic on top in
// app.css. Keeping these as the base means the marketing site and the in-page
// overlay speak the exact same visual language.
import '../../frontend/src/lib/tokens/index.css';
import '../../frontend/src/lib/theme/dark.css';
import './app.css';

import App from './App.svelte';

const target = document.getElementById('app');
if (!target) throw new Error('#app mount target missing');

export default mount(App, { target });
