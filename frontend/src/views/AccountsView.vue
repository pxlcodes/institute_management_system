<script setup>
import { ref } from 'vue'
import { Landmark, ArrowUpRight, ArrowDownRight, Wallet } from 'lucide-vue-next'

const accounts = ref([
  { id: 1, name: 'Main Cash Register', type: 'Cash', balance: 145000 },
  { id: 2, name: 'Nabil Bank Operational', type: 'Bank', balance: 485200 },
  { id: 3, name: 'eSewa QR Settlement', type: 'Wallet', balance: 34500 },
])
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-2xl font-black text-slate-900">Financial Accounts & Ledgers</h2>
      <p class="text-sm text-slate-500">Track institution liquidity, operational accounts, and vendor payables</p>
    </div>

    <!-- Account Cards Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div 
        v-for="acc in accounts" 
        :key="acc.id"
        class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between"
      >
        <div>
          <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">{{ acc.type }}</span>
          <h4 class="text-sm font-bold text-slate-900 mt-0.5">{{ acc.name }}</h4>
          <p class="text-2xl font-black text-slate-900 mt-2">Rs. {{ acc.balance.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-sky-50 text-sky-600 rounded-xl">
          <Landmark class="w-6 h-6" />
        </div>
      </div>
    </div>
  </div>
</template>
