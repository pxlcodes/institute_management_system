<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Sparkles, ShieldCheck, ArrowRight } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')

async function handleLogin() {
  error.value = ''
  const ok = await authStore.login(username.value, password.value)
  if (ok) {
    router.push('/')
  } else {
    error.value = authStore.error || 'Invalid credentials'
  }
}
</script>

<template>
  <div class="min-h-screen bg-slate-950 flex flex-col md:flex-row">
    <!-- Left Hero Image Section -->
    <div class="relative md:w-1/2 lg:w-3/5 bg-slate-900 overflow-hidden flex flex-col justify-between p-8 md:p-12">
      <!-- Background Image -->
      <img 
        src="/images/login-hero.jpg" 
        alt="ELH Learning Academy" 
        class="absolute inset-0 w-full h-full object-cover opacity-60 mix-blend-luminosity hover:mix-blend-normal transition-all duration-700 hover:scale-105"
      />
      <!-- Gradient Overlay -->
      <div class="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/70 to-slate-900/40"></div>

      <!-- Top Branding -->
      <div class="relative z-10 flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-sky-500 text-white font-black text-xl flex items-center justify-center shadow-lg shadow-sky-500/30">
          E
        </div>
        <div>
          <h1 class="text-white font-black text-lg tracking-tight">ELH Academy</h1>
          <p class="text-sky-300 text-xs font-semibold">Institute ERP & Management Portal</p>
        </div>
      </div>

      <!-- Bottom Welcome Text -->
      <div class="relative z-10 max-w-lg mt-12 md:mt-0">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-sky-500/20 text-sky-300 border border-sky-400/30 mb-4 backdrop-blur-md">
          <Sparkles class="w-3.5 h-3.5" /> Next-Gen Educational ERP
        </span>
        <h2 class="text-2xl sm:text-3xl md:text-4xl font-extrabold text-white tracking-tight leading-tight">
          Empowering institute operations with precision.
        </h2>
        <p class="text-slate-300 text-xs sm:text-sm mt-3 leading-relaxed">
          Integrated Bikram Sambat billing cycles, real-time biometric attendance sync, automated parent SMS dispatches, and course completion accreditation.
        </p>
      </div>
    </div>

    <!-- Right Sign-in Form Section -->
    <div class="md:w-1/2 lg:w-2/5 bg-white flex items-center justify-center p-8 sm:p-12 md:p-16">
      <div class="w-full max-w-sm space-y-6">
        <div>
          <h3 class="text-2xl font-black text-slate-900 tracking-tight">Sign in to your portal</h3>
          <p class="text-xs text-slate-500 mt-1">Enter your assigned administrative or faculty credentials</p>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-4">
          <div v-if="error" class="p-3 bg-red-50 text-red-700 text-xs font-medium rounded-xl border border-red-200">
            {{ error }}
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Username</label>
            <input 
              type="text" 
              v-model="username" 
              required 
              class="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition-all font-medium"
              placeholder="e.g. admin or operator"
            />
          </div>

          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider">Password</label>
            </div>
            <input 
              type="password" 
              v-model="password" 
              required 
              class="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition-all font-medium"
              placeholder="••••••••"
            />
          </div>

          <button 
            type="submit" 
            :disabled="authStore.loading"
            class="w-full py-3.5 bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white font-bold text-sm rounded-xl shadow-lg shadow-sky-600/25 flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <span>{{ authStore.loading ? 'Authenticating...' : 'Sign in to Dashboard' }}</span>
            <ArrowRight class="w-4 h-4" />
          </button>
        </form>

        <div class="pt-4 border-t border-slate-100 flex items-center justify-center gap-2 text-xs text-slate-400">
          <ShieldCheck class="w-4 h-4 text-emerald-500" />
          <span>Encrypted Session • PBKDF2 Password Protection</span>
        </div>
      </div>
    </div>
  </div>
</template>
