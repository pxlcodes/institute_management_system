<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import { Plus, Copy, Printer, CheckCircle2, XCircle, Clock } from 'lucide-vue-next'
import TableSkeleton from '@/components/TableSkeleton.vue'

const loading = ref(false)
const routines = ref([])
const activeDay = ref('Sunday')
const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

// Copy Modal State
const showCopyModal = ref(false)
const selectedRoutine = ref(null)
const targetDays = ref([])

onMounted(async () => {
  await fetchRoutines()
})

async function fetchRoutines() {
  loading.value = true
  try {
    const data = await api('/class-routines')
    routines.value = data.routines || data || []
  } catch (err) {
    console.error('Failed to load routines:', err)
  } finally {
    loading.value = false
  }
}

function openCopy(routine) {
  selectedRoutine.value = routine
  targetDays.value = []
  showCopyModal.value = true
}

async function executeCopy() {
  if (!targetDays.value.length) {
    alert('Please select at least one day.')
    return
  }
  try {
    for (const day of targetDays.value) {
      await api('/class-routines', {
        method: 'POST',
        body: JSON.stringify({
          ...selectedRoutine.value,
          day_of_week: day
        })
      })
    }
    showCopyModal.value = false
    alert(`Successfully copied period to ${targetDays.value.join(', ')}!`)
    await fetchRoutines()
  } catch (err) {
    alert('Copy failed: ' + err.message)
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h2 class="text-2xl font-black text-slate-900 tracking-tight">Class Routine Timetable</h2>
        <p class="text-sm text-slate-500">Weekly academic schedules with live attendance sync</p>
      </div>

      <div class="flex items-center gap-2">
        <button class="inline-flex items-center gap-2 px-3.5 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold rounded-lg shadow-sm transition-all">
          <Plus class="w-4 h-4" /> Add Period
        </button>
      </div>
    </div>

    <!-- Day Selector Tabs -->
    <div class="flex border-b border-slate-200 overflow-x-auto gap-2">
      <button
        v-for="d in days"
        :key="d"
        @click="activeDay = d"
        :class="[
          activeDay === d
            ? 'border-sky-600 text-sky-700 font-bold border-b-2'
            : 'text-slate-500 hover:text-slate-700 font-medium',
          'px-4 py-2.5 text-sm whitespace-nowrap transition-colors'
        ]"
      >
        {{ d }}
      </button>
    </div>

    <!-- Timetable Cards / Grid -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase tracking-wider">
          <tr>
            <th class="px-5 py-3.5">Period</th>
            <th class="px-5 py-3.5">Time</th>
            <th class="px-5 py-3.5">Class / Level</th>
            <th class="px-5 py-3.5">Subject</th>
            <th class="px-5 py-3.5">Teacher / Faculty</th>
            <th class="px-5 py-3.5 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="6" :rows="6" :colWidths="['w-20', 'w-32', 'w-28', 'w-36', 'w-24', 'w-16']" />
          <tr v-else-if="!routines.length" class="hover:bg-slate-50">
            <td colspan="6" class="px-5 py-12 text-center text-slate-400">
              No periods scheduled for {{ activeDay }}. Click "Add Period" to create one.
            </td>
          </tr>
          <tr 
            v-for="r in routines" 
            :key="r.id"
            class="hover:bg-slate-50 transition-colors"
          >
            <td class="px-5 py-3 font-semibold text-slate-900">{{ r.period_label || '-' }}</td>
            <td class="px-5 py-3 text-slate-600 font-mono text-xs">{{ r.start_time || '--:--' }} - {{ r.end_time || '--:--' }}</td>
            <td class="px-5 py-3 font-bold text-sky-950">{{ r.class_name }}</td>
            <td class="px-5 py-3 font-semibold text-slate-800">{{ r.subject_name }}</td>
            <td class="px-5 py-3">
              <span class="inline-flex items-center gap-1.5 font-medium text-slate-800">
                <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                {{ r.teacher_name || 'Unassigned' }}
              </span>
            </td>
            <td class="px-5 py-3 text-right">
              <button 
                @click="openCopy(r)"
                title="Copy / Duplicate Record"
                class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-sky-700 bg-sky-50 hover:bg-sky-100 rounded-md border border-sky-200 transition-colors"
              >
                <Copy class="w-3.5 h-3.5" /> Duplicate
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Duplicate Period Modal -->
    <div v-if="showCopyModal" class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100">
        <h3 class="text-lg font-bold text-slate-900">Duplicate Routine Period</h3>
        <p class="text-xs text-slate-500 mt-1 mb-4">
          Duplicate <b>{{ selectedRoutine?.subject_name }} ({{ selectedRoutine?.class_name }})</b> to other days:
        </p>

        <div class="grid grid-cols-2 gap-2.5 my-4">
          <label 
            v-for="d in days" 
            :key="d"
            class="flex items-center gap-2 p-2.5 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer text-xs font-medium"
          >
            <input type="checkbox" :value="d" v-model="targetDays" class="rounded text-sky-600 focus:ring-sky-500" />
            <span>{{ d }}</span>
          </label>
        </div>

        <div class="flex items-center justify-end gap-2 mt-6 pt-4 border-t border-slate-100">
          <button 
            @click="showCopyModal = false"
            class="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
          >
            Cancel
          </button>
          <button 
            @click="executeCopy"
            class="px-4 py-2 text-xs font-bold text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-sm"
          >
            Duplicate to Selected Days
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
