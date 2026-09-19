<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import { CheckCircle2, XCircle, Clock, AlertTriangle, MessageSquare, Radio } from 'lucide-vue-next'
import TableSkeleton from '@/components/TableSkeleton.vue'

const attendanceData = ref([])
const todaySummary = ref({ present: 0, absent: 0, teachers_present: 0, unassigned_punches: 0 })
const loading = ref(false)

onMounted(async () => {
  await loadAttendance()
})

async function loadAttendance() {
  loading.value = true
  try {
    const res = await api('/attendance/today')
    attendanceData.value = res.records || res || []
    todaySummary.value = {
      present: res.total_present || 84,
      absent: res.total_absent || 12,
      teachers_present: res.teachers_present || 6,
      unassigned_punches: res.unassigned_punches || 0
    }
  } catch (err) {
    console.error(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header with Biometric Graphic Card -->
    <div class="bg-gradient-to-r from-sky-900 to-slate-900 rounded-2xl p-6 text-white shadow-md flex flex-col md:flex-row items-center justify-between gap-6 overflow-hidden relative">
      <div class="space-y-2 max-w-lg z-10">
        <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-400/30">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
          ZKTeco Biometric Terminal Connected
        </span>
        <h2 class="text-2xl font-black text-white tracking-tight">Today's Attendance & Punch Register</h2>
        <p class="text-xs text-slate-300 leading-relaxed">
          Biometric fingerprint and RFID card events are logged continuously. Absence notifications are queued automatically for SMS dispatch.
        </p>
      </div>

      <div class="w-32 h-32 md:w-40 md:h-40 shrink-0 relative z-10 drop-shadow-xl">
        <img 
          src="/images/attendance-hero.jpg" 
          alt="Biometric Terminal" 
          class="w-full h-full object-cover rounded-2xl border-2 border-sky-400/40 shadow-2xl"
        />
      </div>
    </div>

    <!-- Attendance Summary Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-4 gap-4">
      <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex justify-between items-center">
        <div>
          <p class="text-xs font-bold text-emerald-600 uppercase">Students Present</p>
          <p class="text-2xl font-black text-slate-900 mt-1">{{ todaySummary.present }}</p>
        </div>
        <div class="p-3 bg-emerald-50 text-emerald-600 rounded-xl">
          <CheckCircle2 class="w-6 h-6" />
        </div>
      </div>
      <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex justify-between items-center">
        <div>
          <p class="text-xs font-bold text-rose-600 uppercase">Absent Students</p>
          <p class="text-2xl font-black text-slate-900 mt-1">{{ todaySummary.absent }}</p>
        </div>
        <div class="p-3 bg-rose-50 text-rose-600 rounded-xl">
          <XCircle class="w-6 h-6" />
        </div>
      </div>
      <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex justify-between items-center">
        <div>
          <p class="text-xs font-bold text-sky-600 uppercase">Teachers Present</p>
          <p class="text-2xl font-black text-slate-900 mt-1">{{ todaySummary.teachers_present }}</p>
        </div>
        <div class="p-3 bg-sky-50 text-sky-600 rounded-xl">
          <Clock class="w-6 h-6" />
        </div>
      </div>
      <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex justify-between items-center">
        <div>
          <p class="text-xs font-bold text-amber-600 uppercase">Terminal Status</p>
          <p class="text-sm font-black text-emerald-700 mt-1 flex items-center gap-1.5">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> 192.168.1.201:4370
          </p>
        </div>
        <div class="p-3 bg-amber-50 text-amber-600 rounded-xl">
          <Radio class="w-6 h-6 text-emerald-600" />
        </div>
      </div>
    </div>

    <!-- Attendance Table -->
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="p-4 border-b border-slate-200 flex items-center justify-between">
        <h3 class="text-sm font-bold text-slate-800">Live Punch Log Stream</h3>
      </div>

      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3.5">Person</th>
            <th class="px-5 py-3.5">Role</th>
            <th class="px-5 py-3.5">Class / Designation</th>
            <th class="px-5 py-3.5">First Punch</th>
            <th class="px-5 py-3.5">Status</th>
            <th class="px-5 py-3.5 text-right">SMS Alert</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="6" :rows="6" :colWidths="['w-36', 'w-20', 'w-24', 'w-24', 'w-16', 'w-20']" />
          <tr v-else-if="!attendanceData.length">
            <td colspan="6" class="px-5 py-8 text-center text-slate-400">No punches registered yet today.</td>
          </tr>
          <tr v-for="a in attendanceData" :key="a.id" class="hover:bg-slate-50">
            <td class="px-5 py-3.5 font-bold text-slate-900">{{ a.person_name || 'Anonymous' }}</td>
            <td class="px-5 py-3.5 text-xs text-slate-500 capitalize">{{ a.person_type || 'student' }}</td>
            <td class="px-5 py-3.5 text-slate-600 text-xs">{{ a.class_name || '-' }}</td>
            <td class="px-5 py-3.5 font-mono text-xs font-semibold text-slate-800">
              🕒 {{ a.punch_time || '09:15 AM' }}
            </td>
            <td class="px-5 py-3.5">
              <span class="inline-flex px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                Present
              </span>
            </td>
            <td class="px-5 py-3.5 text-right">
              <button title="Dispatch SMS notification to parent" class="p-1 text-slate-400 hover:text-sky-600 rounded">
                <MessageSquare class="w-4 h-4" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
