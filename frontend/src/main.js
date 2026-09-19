import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import './assets/main.css'

const app = createApp(App)

app.use(createPinia())

app.mount('#app')

// Register PWA Service Worker
if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then((registration) => {
        console.log('ELH PWA ServiceWorker registered with scope:', registration.scope);
      })
      .catch((error) => {
        console.warn('ELH PWA ServiceWorker registration failed:', error);
      });
  });
}
