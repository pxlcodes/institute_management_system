<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import { Users, Search, Download } from 'lucide-vue-next'
import TableSkeleton from '@/components/TableSkeleton.vue'

const students = ref([])
const loading = ref(false)
const searchQuery = ref('')

onMounted(async () => {
  loading.value = true
  try {
    const res = await api('/students')
    students.value = res.students || res || []
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
        <h2 class="text-2xl font-black text-slate-900">Student Profiles & Records</h2>
        <p class="text-sm text-slate-500">Manage admissions, classes, guardians, and contact information</p>
      </div>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="p-4 border-b border-slate-200 flex items-center justify-between gap-4">
        <div class="relative flex-1 max-w-sm flex items-center">
          <Search class="w-4 h-4 text-slate-400 absolute left-3 pointer-events-none z-10" />
          <input 
            type="text" 
            v-model="searchQuery"
            placeholder="Search students by name, contact, class..." 
            class="w-full pr-4 py-2 border border-slate-200 rounded-lg text-xs focus:outline-none focus:border-sky-500"
            style="padding-left: 2.5rem !important;"
          />
        </div>
      </div>

      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3">ID</th>
            <th class="px-5 py-3">Student Name</th>
            <th class="px-5 py-3">Class</th>
            <th class="px-5 py-3">Contact</th>
            <th class="px-5 py-3">Guardian</th>
            <th class="px-5 py-3">Status</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="6" :rows="6" :colWidths="['w-10', 'w-36', 'w-20', 'w-28', 'w-28', 'w-16']" />
          <tr v-else-if="!students.length">
            <td colspan="6" class="px-5 py-8 text-center text-slate-400">No student records found.</td>
          </tr>
          <tr v-for="s in students" :key="s.id" class="hover:bg-slate-50">
            <td class="px-5 py-3 text-xs text-slate-400 font-mono">#{{ s.id }}</td>
            <td class="px-5 py-3 font-bold text-slate-900">{{ s.student_name || s.name }}</td>
            <td class="px-5 py-3 text-slate-600">{{ s.class_name || '-' }}</td>
            <td class="px-5 py-3 text-slate-600 font-mono text-xs">{{ s.contact || '-' }}</td>
            <td class="px-5 py-3 text-slate-600">{{ s.parent_name || '-' }}</td>
            <td class="px-5 py-3">
              <span class="inline-flex px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                Active
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
