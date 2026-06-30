import { mount } from 'svelte';

// Shared frontprompt design tokens — the primitive colour + typography scale the
// site consumes via app.css. The in-page overlay inlines its own token copy, so
// the marketing site and the overlay speak the same visual language.
import '../../frontend/src/lib/tokens/index.css';
import './app.css';

import App from './App.svelte';

const target = document.getElementById('app');
if (!target) throw new Error('#app mount target missing');

export default mount(App, { target });
