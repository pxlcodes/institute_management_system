<script setup>
import { ref } from 'vue'
import { Settings, Shield, MessageSquare, Database, Check } from 'lucide-vue-next'

const smsProvider = ref('aakash')
const testPhone = ref('')
const testMessage = ref('Test SMS from ELH Academy')
const saved = ref(false)

function saveSettings() {
  saved.value = true
  setTimeout(() => saved.value = false, 2500)
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-2xl font-black text-slate-900">System Administration & Settings</h2>
      <p class="text-sm text-slate-500">Configure SMS gateways, database backups, and institute profile</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- SMS Gateway Configuration -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div class="flex items-center gap-2 font-bold text-slate-900 text-base">
          <MessageSquare class="w-5 h-5 text-sky-600" />
          <span>Transactional SMS Gateways (Nepal)</span>
        </div>

        <div class="space-y-3">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Active Gateway Provider</label>
            <div class="flex gap-4">
              <label class="flex items-center gap-2 text-sm font-medium cursor-pointer">
                <input type="radio" value="aakash" v-model="smsProvider" class="text-sky-600" />
                <span>Aakash SMS</span>
              </label>
              <label class="flex items-center gap-2 text-sm font-medium cursor-pointer">
                <input type="radio" value="sparrow" v-model="smsProvider" class="text-sky-600" />
                <span>Sparrow SMS</span>
              </label>
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Test Recipient Mobile (10 Digits)</label>
            <input type="text" v-model="testPhone" placeholder="98XXXXXXXX" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
          </div>

          <button 
            @click="saveSettings"
            class="px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold rounded-lg shadow-sm"
          >
            Dispatch Test SMS
          </button>
        </div>
      </div>

      <!-- Database Backups -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div class="flex items-center gap-2 font-bold text-slate-900 text-base">
          <Database class="w-5 h-5 text-emerald-600" />
          <span>Database Integrity & Backups</span>
        </div>

        <p class="text-xs text-slate-500">
          Create consistent snapshot backups with matching SHA-256 integrity checksums.
        </p>

        <div class="pt-2">
          <button class="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg shadow-sm">
            Backup Database Now
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
