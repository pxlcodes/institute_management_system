<script setup>
defineProps({
  type: { type: String, default: 'table' } // 'dashboard', 'table', 'calendar', 'cards'
})
</script>

<template>
  <div class="space-y-6 animate-pulse">
    <!-- Header skeleton -->
    <div class="space-y-2">
      <div class="h-7 bg-slate-200 dark:bg-slate-700 rounded-lg w-64"></div>
      <div class="h-4 bg-slate-200 dark:bg-slate-700 rounded w-96"></div>
    </div>

    <!-- KPI Cards skeleton if type is dashboard or cards -->
    <div v-if="type === 'dashboard' || type === 'cards'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div v-for="n in 4" :key="n" class="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm flex items-center justify-between">
        <div class="space-y-2 flex-1">
          <div class="h-3 bg-slate-200 dark:bg-slate-700 rounded w-20"></div>
          <div class="h-7 bg-slate-200 dark:bg-slate-700 rounded-lg w-28"></div>
        </div>
        <div class="w-12 h-12 rounded-xl bg-slate-200 dark:bg-slate-700"></div>
      </div>
    </div>

    <!-- Table skeleton if type is table or dashboard -->
    <div class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden p-4 space-y-4">
      <div class="flex items-center justify-between gap-4">
        <div class="h-9 bg-slate-200 dark:bg-slate-700 rounded-lg w-72"></div>
        <div class="flex gap-2">
          <div class="h-9 bg-slate-200 dark:bg-slate-700 rounded-lg w-24"></div>
          <div class="h-9 bg-slate-200 dark:bg-slate-700 rounded-lg w-28"></div>
        </div>
      </div>
      <div class="space-y-3 pt-2">
        <div v-for="n in 6" :key="n" class="h-10 bg-slate-100 dark:bg-slate-700/50 rounded-lg w-full flex items-center px-4 justify-between">
          <div class="h-4 bg-slate-200 dark:bg-slate-600 rounded w-16"></div>
          <div class="h-4 bg-slate-200 dark:bg-slate-600 rounded w-40"></div>
          <div class="h-4 bg-slate-200 dark:bg-slate-600 rounded w-28"></div>
          <div class="h-4 bg-slate-200 dark:bg-slate-600 rounded w-20"></div>
        </div>
      </div>
    </div>
  </div>
</template>
