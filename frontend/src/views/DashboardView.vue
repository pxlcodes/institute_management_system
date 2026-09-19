<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Users, GraduationCap, AlertCircle, CreditCard, Clock, Plus, ArrowRight } from 'lucide-vue-next'

const router = useRouter()

const stats = [
  { label: 'Active Students', value: '142', icon: Users, color: 'text-sky-600', bg: 'bg-sky-50' },
  { label: 'Running Courses', value: '8', icon: GraduationCap, color: 'text-emerald-600', bg: 'bg-emerald-50' },
  { label: 'Pending Dues', value: 'Rs. 45,200', icon: AlertCircle, color: 'text-rose-600', bg: 'bg-rose-50' },
  { label: 'Monthly Collection', value: 'Rs. 1,82,500', icon: CreditCard, color: 'text-indigo-600', bg: 'bg-indigo-50' },
]
</script>

<template>
  <div class="space-y-6">
    <!-- Visual Hero Banner with Image -->
    <div class="relative rounded-2xl overflow-hidden shadow-md bg-gradient-to-r from-sky-900 via-indigo-950 to-slate-900 text-white">
      <img 
        src="/images/dashboard-banner.jpg" 
        alt="Academy Campus" 
        class="absolute right-0 top-0 bottom-0 w-full sm:w-3/5 object-cover opacity-35 mix-blend-screen pointer-events-none"
      />
      <div class="absolute inset-0 bg-gradient-to-r from-slate-950 via-slate-950/80 to-transparent"></div>

      <div class="relative z-10 p-6 sm:p-8 max-w-xl space-y-3">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-sky-500/20 text-sky-300 border border-sky-400/30">
          Academic Year 2083 BS • Live Campus
        </span>
        <h2 class="text-2xl sm:text-3xl font-black tracking-tight text-white">
          Welcome to ELH Academy
        </h2>
        <p class="text-xs sm:text-sm text-slate-300 leading-relaxed">
          Operational control center for fee collections, student enrollments, biometric attendance synchronization, and faculty scheduling.
        </p>

        <div class="pt-2 flex flex-wrap gap-2.5">
          <button 
            @click="router.push('/bills')"
            class="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-white text-xs font-bold rounded-xl shadow-md flex items-center gap-1.5 transition-all"
          >
            <span>Manage Fee Dues</span>
            <ArrowRight class="w-3.5 h-3.5" />
          </button>
          <button 
            @click="router.push('/routines')"
            class="px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-xs font-bold rounded-xl border border-white/20 backdrop-blur-sm transition-all"
          >
            Class Routine
          </button>
        </div>
      </div>
    </div>

    <!-- KPI Metric Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div 
        v-for="s in stats" 
        :key="s.label"
        class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between hover:shadow-md transition-shadow"
      >
        <div>
          <p class="text-xs font-bold text-slate-400 uppercase tracking-wider">{{ s.label }}</p>
          <p class="text-2xl font-black text-slate-900 mt-1">{{ s.value }}</p>
        </div>
        <div :class="[s.bg, s.color, 'p-3.5 rounded-xl shadow-inner']">
          <component :is="s.icon" class="w-6 h-6" />
        </div>
      </div>
    </div>
  </div>
</template>
