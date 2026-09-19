<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import { Users, Plus, DollarSign, Wallet } from 'lucide-vue-next'
import TableSkeleton from '@/components/TableSkeleton.vue'

const staff = ref([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const res = await api('/teachers')
    staff.value = res || []
  } catch (err) {
    console.error(err)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-black text-slate-900">Staff, Faculty & Payroll</h2>
        <p class="text-sm text-slate-500">Teacher registers, salary payouts, advances, and contracts</p>
      </div>
      <button class="inline-flex items-center gap-2 px-3.5 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold rounded-lg shadow-sm">
        <Plus class="w-4 h-4" /> Add Staff Member
      </button>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3">ID</th>
            <th class="px-5 py-3">Staff Name</th>
            <th class="px-5 py-3">Type</th>
            <th class="px-5 py-3">Phone</th>
            <th class="px-5 py-3">Salary Type</th>
            <th class="px-5 py-3">Status</th>
            <th class="px-5 py-3 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="7" :rows="6" :colWidths="['w-10', 'w-36', 'w-24', 'w-24', 'w-20', 'w-16', 'w-16']" />
          <tr v-for="s in staff" :key="s.id" class="hover:bg-slate-50">
            <td class="px-5 py-3 text-xs text-slate-400 font-mono">#{{ s.id }}</td>
            <td class="px-5 py-3 font-bold text-slate-900">{{ s.teacher_name }}</td>
            <td class="px-5 py-3 text-xs text-slate-600">{{ s.staff_type || 'Teaching' }}</td>
            <td class="px-5 py-3 font-mono text-xs text-slate-600">{{ s.phone || '-' }}</td>
            <td class="px-5 py-3 font-medium text-slate-700">{{ s.salary_type || 'Monthly' }}</td>
            <td class="px-5 py-3">
              <span class="inline-flex px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                Active
              </span>
            </td>
            <td class="px-5 py-3 text-right space-x-2">
              <button class="text-xs font-bold text-sky-600 hover:text-sky-800">Disburse Salary</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
