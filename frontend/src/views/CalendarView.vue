<script setup>
import { ref } from 'vue'

const currentMonth = ref('2083/05')
const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-black text-slate-900">{{ currentMonth }} Bikram Sambat Calendar</h2>
        <p class="text-sm text-slate-500">Academic events, fee due dates, and closures</p>
      </div>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
      <div class="grid grid-cols-7 gap-px bg-slate-200 rounded-lg overflow-hidden border border-slate-200">
        <div 
          v-for="day in weekdays" 
          :key="day" 
          class="bg-slate-100 py-2 text-center text-xs font-extrabold text-slate-700"
        >
          {{ day }}
        </div>

        <!-- 30 Days of BS month sample -->
        <div 
          v-for="d in 30" 
          :key="d" 
          class="bg-white p-3 h-28 flex flex-col justify-between hover:bg-sky-50/50 transition-colors"
        >
          <div class="font-bold text-sm text-slate-800">{{ d }}</div>
          <div v-if="d === 6 || d === 13 || d === 20 || d === 27" class="mt-1">
            <span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-700">
              Weekend
            </span>
          </div>
          <div v-if="d === 12" class="mt-1">
            <span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800">
              Janai Purnima
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
