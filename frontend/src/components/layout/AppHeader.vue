<script setup>
import { useAuthStore } from '@/stores/auth'
import { Menu } from 'lucide-vue-next'

const emit = defineEmits(['toggle-mobile'])
const authStore = useAuthStore()
</script>

<template>
  <header class="h-16 bg-white border-b border-slate-200 px-4 sm:px-8 flex items-center justify-between shrink-0">
    <div class="flex items-center gap-3">
      <!-- Mobile Hamburger Button -->
      <button 
        @click="emit('toggle-mobile')" 
        class="p-2 -ml-2 text-slate-600 hover:text-slate-900 rounded-lg lg:hidden"
        title="Open Navigation"
      >
        <Menu class="w-6 h-6" />
      </button>

      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
        <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
        FastAPI Live Sync
      </span>
    </div>

    <div class="flex items-center gap-4 text-sm">
      <span class="text-xs text-slate-500 font-medium hidden sm:inline">Bikram Sambat Academic Portal</span>
    </div>
  </header>
</template>
