<script setup>
defineProps({
  cols: { type: Number, default: 6 },
  rows: { type: Number, default: 6 },
  colWidths: { type: Array, default: () => ['w-12', 'w-36', 'w-24', 'w-28', 'w-28', 'w-16'] }
})
</script>

<template>
  <tr v-for="r in rows" :key="'skel-row-' + r" class="animate-pulse">
    <td 
      v-for="c in cols" 
      :key="'skel-col-' + c" 
      class="px-5 py-4"
    >
      <div 
        :class="[
          colWidths[(c - 1) % colWidths.length] || 'w-24',
          c === cols ? 'rounded-full h-5 ml-auto' : 'rounded h-4',
          'bg-slate-200 dark:bg-slate-700'
        ]"
      ></div>
    </td>
  </tr>
</template>
