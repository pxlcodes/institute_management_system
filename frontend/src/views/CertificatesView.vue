<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import { Award, FileText, CheckCircle2 } from 'lucide-vue-next'
import TableSkeleton from '@/components/TableSkeleton.vue'

const certificates = ref([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const res = await api('/certificates')
    certificates.value = res || []
  } catch (err) {
    console.error(err)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- Prestige Banner with Image -->
    <div class="bg-gradient-to-r from-indigo-950 via-slate-900 to-sky-950 rounded-2xl p-6 text-white shadow-md flex flex-col md:flex-row items-center justify-between gap-6 overflow-hidden">
      <div class="space-y-2 max-w-lg z-10">
        <span class="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-400/30">
          Official Institute Accreditation
        </span>
        <h2 class="text-2xl font-black text-white tracking-tight">Course Completion Certificates</h2>
        <p class="text-xs text-slate-300 leading-relaxed">
          Print-ready A4-landscape certificates issued exclusively for completed student courses. Each certificate is backed by a verifiable SHA-256 integrity checksum.
        </p>
      </div>

      <div class="w-28 h-28 md:w-36 md:h-36 shrink-0 relative z-10">
        <img 
          src="/images/certificate-hero.jpg" 
          alt="Certificate Diploma Crest" 
          class="w-full h-full object-cover rounded-2xl border-2 border-amber-400/50 shadow-2xl"
        />
      </div>
    </div>

    <!-- Certificates Registry Table -->
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3.5">Certificate #</th>
            <th class="px-5 py-3.5">Student Name</th>
            <th class="px-5 py-3.5">Course Completed</th>
            <th class="px-5 py-3.5">Issue Date (BS)</th>
            <th class="px-5 py-3.5 text-right">PDF Certificate</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="5" :rows="6" :colWidths="['w-28', 'w-36', 'w-28', 'w-24', 'w-24']" />
          <tr v-else-if="!certificates.length">
            <td colspan="5" class="px-5 py-8 text-center text-slate-400">No certificates issued yet.</td>
          </tr>
          <tr v-for="c in certificates" :key="c.id" class="hover:bg-slate-50">
            <td class="px-5 py-3.5 font-mono font-bold text-xs text-sky-900">{{ c.cert_no || 'CERT-2083-001' }}</td>
            <td class="px-5 py-3.5 font-bold text-slate-900">{{ c.student_name }}</td>
            <td class="px-5 py-3.5 text-slate-600">{{ c.course_name }}</td>
            <td class="px-5 py-3.5 text-slate-500 font-mono text-xs">{{ c.issue_date }}</td>
            <td class="px-5 py-3.5 text-right">
              <button class="inline-flex items-center gap-1.5 px-3 py-1 bg-sky-50 text-sky-700 text-xs font-bold rounded-lg border border-sky-200 hover:bg-sky-100">
                <FileText class="w-3.5 h-3.5" /> Download PDF
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
