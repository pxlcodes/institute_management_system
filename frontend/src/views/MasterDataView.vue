<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import { BookOpen, School, Layers, Plus } from 'lucide-vue-next'
import TableSkeleton from '@/components/TableSkeleton.vue'

const activeTab = ref('courses')
const courses = ref([])
const schools = ref([])
const subjects = ref([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const [c, s, sub] = await Promise.all([
      api('/courses'),
      api('/schools'),
      api('/subjects'),
    ])
    courses.value = c || []
    schools.value = s || []
    subjects.value = sub || []
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
        <h2 class="text-2xl font-black text-slate-900">Academic Master Data</h2>
        <p class="text-sm text-slate-500">Manage course catalogs, affiliated schools, and curriculum subjects</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex border-b border-slate-200 gap-4">
      <button 
        @click="activeTab = 'courses'" 
        :class="[activeTab === 'courses' ? 'border-sky-600 text-sky-600 font-bold border-b-2' : 'text-slate-500 font-medium', 'pb-3 text-sm flex items-center gap-2']"
      >
        <BookOpen class="w-4 h-4" /> Course Catalog ({{ courses.length }})
      </button>
      <button 
        @click="activeTab = 'subjects'" 
        :class="[activeTab === 'subjects' ? 'border-sky-600 text-sky-600 font-bold border-b-2' : 'text-slate-500 font-medium', 'pb-3 text-sm flex items-center gap-2']"
      >
        <Layers class="w-4 h-4" /> Subjects & Electives ({{ subjects.length }})
      </button>
      <button 
        @click="activeTab = 'schools'" 
        :class="[activeTab === 'schools' ? 'border-sky-600 text-sky-600 font-bold border-b-2' : 'text-slate-500 font-medium', 'pb-3 text-sm flex items-center gap-2']"
      >
        <School class="w-4 h-4" /> Schools Master ({{ schools.length }})
      </button>
    </div>

    <!-- Courses Table -->
    <div v-if="activeTab === 'courses'" class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3">ID</th>
            <th class="px-5 py-3">Course Name</th>
            <th class="px-5 py-3">Category</th>
            <th class="px-5 py-3">Default Fee</th>
            <th class="px-5 py-3">Instructor</th>
            <th class="px-5 py-3">Status</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="6" :rows="5" :colWidths="['w-10', 'w-36', 'w-20', 'w-24', 'w-24', 'w-16']" />
          <template v-else>
            <tr v-for="c in courses" :key="c.id" class="hover:bg-slate-50">
              <td class="px-5 py-3 text-xs text-slate-400 font-mono">#{{ c.id }}</td>
              <td class="px-5 py-3 font-bold text-slate-900">{{ c.course_name }}</td>
              <td class="px-5 py-3 text-xs text-slate-600">{{ c.category || 'Tuition' }}</td>
              <td class="px-5 py-3 font-semibold text-slate-800">Rs. {{ Number(c.default_fee || 0).toLocaleString() }}</td>
              <td class="px-5 py-3 text-slate-700">{{ c.instructor_name || '—' }}</td>
              <td class="px-5 py-3">
                <span class="inline-flex px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  Active
                </span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Subjects Table -->
    <div v-if="activeTab === 'subjects'" class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3">Code</th>
            <th class="px-5 py-3">Subject Name</th>
            <th class="px-5 py-3">Type</th>
            <th class="px-5 py-3">Class / Level</th>
            <th class="px-5 py-3">Status</th>
            <th class="px-5 py-3">Remarks</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="6" :rows="5" :colWidths="['w-16', 'w-40', 'w-24', 'w-24', 'w-16', 'w-32']" />
          <template v-else>
            <tr v-for="sub in subjects" :key="sub.id" class="hover:bg-slate-50">
              <td class="px-5 py-3 font-mono font-bold text-xs text-slate-700">{{ sub.subject_code }}</td>
              <td class="px-5 py-3 font-bold text-slate-900">{{ sub.subject_name }}</td>
              <td class="px-5 py-3">
                <span :class="[
                  sub.subject_type === 'Optional' || sub.subject_type === 'Elective'
                    ? 'bg-amber-50 text-amber-700 border-amber-200'
                    : 'bg-sky-50 text-sky-700 border-sky-200',
                  'inline-flex px-2 py-0.5 rounded text-[11px] font-bold border'
                ]">
                  {{ sub.subject_type }}
                </span>
              </td>
              <td class="px-5 py-3 text-slate-600 text-xs">{{ sub.class_name || 'All Levels' }}</td>
              <td class="px-5 py-3">
                <span class="inline-flex px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  {{ sub.status }}
                </span>
              </td>
              <td class="px-5 py-3 text-xs text-slate-500">{{ sub.remarks || '—' }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Schools Table -->
    <div v-if="activeTab === 'schools'" class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3">ID</th>
            <th class="px-5 py-3">School Name</th>
            <th class="px-5 py-3">EMIS Code</th>
            <th class="px-5 py-3">Address</th>
            <th class="px-5 py-3">Contact</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="5" :rows="5" :colWidths="['w-10', 'w-40', 'w-24', 'w-36', 'w-24']" />
          <template v-else>
            <tr v-for="s in schools" :key="s.id" class="hover:bg-slate-50">
              <td class="px-5 py-3 text-xs text-slate-400 font-mono">#{{ s.id }}</td>
              <td class="px-5 py-3 font-bold text-slate-900">{{ s.school_name }}</td>
              <td class="px-5 py-3 font-mono text-xs text-slate-500">{{ s.emis_id || '—' }}</td>
              <td class="px-5 py-3 text-slate-600 text-xs">{{ s.address || '—' }}</td>
              <td class="px-5 py-3 font-mono text-xs text-slate-600">{{ s.contact || '—' }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>
