<script setup>
import { ref, onMounted } from 'vue'
import { Download, Smartphone, X, Check } from 'lucide-vue-next'

const deferredPrompt = ref(null)
const isInstallable = ref(false)
const isInstalled = ref(false)
const isIOS = ref(false)
const showIOSPrompt = ref(false)

onMounted(() => {
  // Check if running as standalone PWA app
  if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true) {
    isInstalled.value = true
    return
  }

  // Detect iOS
  const userAgent = window.navigator.userAgent.toLowerCase()
  if (/iphone|ipad|ipod/.test(userAgent) && !window.MSStream) {
    isIOS.value = true
  }

  // Listen for Chrome / Edge / Android install prompt
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    deferredPrompt.value = e
    isInstallable.value = true
  })

  window.addEventListener('appinstalled', () => {
    isInstalled.value = true
    isInstallable.value = false
    deferredPrompt.value = null
  })
})

async function promptInstall() {
  if (isIOS.value) {
    showIOSPrompt.value = true
    return
  }
  if (!deferredPrompt.value) {
    alert('To install on your device, tap your browser menu (⋮ or Share) and select "Install app" or "Add to Home Screen".')
    return
  }
  deferredPrompt.value.prompt()
  const choiceResult = await deferredPrompt.value.userChoice
  if (choiceResult.outcome === 'accepted') {
    isInstalled.value = true
  }
  deferredPrompt.value = null
  isInstallable.value = false
}
</script>

<template>
  <div v-if="!isInstalled">
    <!-- Action Button (fits nicely in sidebar or header) -->
    <button 
      @click="promptInstall"
      title="Install as native Mobile App"
      class="w-full flex items-center justify-between px-3 py-2 bg-gradient-to-r from-sky-600 to-indigo-600 text-white rounded-lg text-xs font-bold shadow-sm hover:from-sky-500 hover:to-indigo-500 transition-all cursor-pointer"
    >
      <div class="flex items-center gap-2">
        <Smartphone class="w-4 h-4 text-sky-200 animate-bounce" />
        <span>Install Mobile App</span>
      </div>
      <Download class="w-3.5 h-3.5 text-white/80" />
    </button>

    <!-- iOS Instructions Modal -->
    <div v-if="showIOSPrompt" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl max-w-sm w-full p-6 shadow-2xl border border-slate-100 text-slate-800 text-center">
        <div class="w-12 h-12 rounded-2xl bg-sky-100 text-sky-600 flex items-center justify-center mx-auto mb-3">
          <Smartphone class="w-6 h-6" />
        </div>
        <h3 class="text-base font-bold text-slate-900">Install on iPhone / iPad</h3>
        <p class="text-xs text-slate-500 mt-1 mb-4">Install ELH Academy to your Home Screen for the full fullscreen app experience:</p>

        <div class="bg-slate-50 p-3.5 rounded-xl text-xs text-left space-y-2 border border-slate-200">
          <div class="flex items-start gap-2">
            <span class="font-bold text-sky-600">1.</span>
            <span>Tap the <b>Share</b> button at the bottom of Safari (box with up arrow).</span>
          </div>
          <div class="flex items-start gap-2">
            <span class="font-bold text-sky-600">2.</span>
            <span>Scroll down and select <b>"Add to Home Screen"</b>.</span>
          </div>
          <div class="flex items-start gap-2">
            <span class="font-bold text-sky-600">3.</span>
            <span>Tap <b>Add</b> in the top-right corner.</span>
          </div>
        </div>

        <button 
          @click="showIOSPrompt = false"
          class="w-full mt-5 py-2.5 bg-slate-900 text-white font-bold text-xs rounded-xl shadow"
        >
          Got it
        </button>
      </div>
    </div>
  </div>
</template>
