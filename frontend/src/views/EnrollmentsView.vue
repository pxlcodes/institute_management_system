<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import { GraduationCap, Plus, Search, Calendar, UserCheck } from 'lucide-vue-next'
import TableSkeleton from '@/components/TableSkeleton.vue'

const enrollments = ref([])
const loading = ref(false)
const searchQuery = ref('')
const showModal = ref(false)

// Form State
const students = ref([])
const courses = ref([])
const form = ref({
  student_id: '',
  course_id: '',
  level: '',
  start_date: '2083/05/01',
  monthly_fee: 3000,
  admission_fee: 1000,
  discount: 0
})

onMounted(async () => {
  await loadEnrollments()
})

async function loadEnrollments() {
  loading.value = true
  try {
    const data = await api('/enrollments')
    enrollments.value = data || []
  } catch (err) {
    console.error(err)
  } finally {
    loading.value = false
  }
}

async function openCreateModal() {
  try {
    const [sData, cData] = await Promise.all([
      api('/students'),
      api('/courses')
    ])
    students.value = sData.students || sData || []
    courses.value = cData || []
    showModal.value = true
  } catch (err) {
    alert('Failed to load courses or students: ' + err.message)
  }
}

async function submitEnrollment() {
  try {
    await api('/enrollments', {
      method: 'POST',
      body: JSON.stringify({
        student_id: Number(form.value.student_id),
        course_id: Number(form.value.course_id),
        level: form.value.level,
        start_date: form.value.start_date,
        monthly_fee: Number(form.value.monthly_fee),
        admission_fee: Number(form.value.admission_fee),
        discount: Number(form.value.discount)
      })
    })
    alert('Enrollment created successfully!')
    showModal.value = false
    await loadEnrollments()
  } catch (err) {
    alert('Failed to enroll: ' + err.message)
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h2 class="text-2xl font-black text-slate-900">Course Enrollments</h2>
        <p class="text-sm text-slate-500">Student course assignments, batches, fee agreements, and duration</p>
      </div>
      <button 
        @click="openCreateModal"
        class="inline-flex items-center gap-2 px-3.5 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold rounded-lg shadow-sm"
      >
        <Plus class="w-4 h-4" /> Enroll Student
      </button>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3">ID</th>
            <th class="px-5 py-3">Student Name</th>
            <th class="px-5 py-3">Enrolled Course</th>
            <th class="px-5 py-3">Level / Batch</th>
            <th class="px-5 py-3">Start Date (BS)</th>
            <th class="px-5 py-3">Monthly Fee</th>
            <th class="px-5 py-3">Status</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="7" :rows="6" :colWidths="['w-10', 'w-36', 'w-28', 'w-20', 'w-24', 'w-24', 'w-16']" />
          <tr v-else-if="!enrollments.length">
            <td colspan="7" class="px-5 py-8 text-center text-slate-400">No active enrollments found.</td>
          </tr>
          <tr v-for="e in enrollments" :key="e.id" class="hover:bg-slate-50">
            <td class="px-5 py-3 text-xs text-slate-400 font-mono">#{{ e.id }}</td>
            <td class="px-5 py-3 font-bold text-slate-900">{{ e.student_name }}</td>
            <td class="px-5 py-3 font-medium text-sky-950">{{ e.course_name }}</td>
            <td class="px-5 py-3 text-xs text-slate-600">{{ e.level || 'Standard' }}</td>
            <td class="px-5 py-3 font-mono text-xs text-slate-600">{{ e.start_date }}</td>
            <td class="px-5 py-3 font-semibold text-slate-900">Rs. {{ Number(e.monthly_fee || 0).toLocaleString() }}</td>
            <td class="px-5 py-3">
              <span class="inline-flex px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                {{ e.status || 'Active' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create Enrollment Modal -->
    <div v-if="showModal" class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100">
        <h3 class="text-lg font-bold text-slate-900">New Course Enrollment</h3>
        <p class="text-xs text-slate-500 mt-1 mb-4">Assign a student to an academic program or tuition batch:</p>

        <form @submit.prevent="submitEnrollment" class="space-y-3">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Student *</label>
            <select v-model="form.student_id" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm">
              <option value="">Select student</option>
              <option v-for="s in students" :key="s.id" :value="s.id">{{ s.student_name || s.name }}</option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Course *</label>
            <select v-model="form.course_id" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm">
              <option value="">Select course</option>
              <option v-for="c in courses" :key="c.id" :value="c.id">{{ c.course_name }} (Rs. {{ c.default_fee }})</option>
            </select>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Level / Batch</label>
              <input type="text" v-model="form.level" placeholder="e.g. Grade 8 / Morning" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Start Date (BS) *</label>
              <input type="text" v-model="form.start_date" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Monthly Fee (Rs.)</label>
              <input type="number" v-model="form.monthly_fee" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Admission Fee (Rs.)</label>
              <input type="number" v-model="form.admission_fee" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
            </div>
          </div>

          <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
            <button type="button" @click="showModal = false" class="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
            <button type="submit" class="px-4 py-2 text-xs font-bold text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-sm">Save Enrollment</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
