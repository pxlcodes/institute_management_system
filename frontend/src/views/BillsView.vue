<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { 
  Receipt, 
  Search, 
  Plus, 
  CreditCard, 
  FileText, 
  Printer, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  Trash2,
  History,
  ShieldCheck,
  ShieldAlert
} from 'lucide-vue-next'
import TableSkeleton from '@/components/TableSkeleton.vue'

const authStore = useAuthStore()

const bills = ref([])
const loading = ref(false)
const filterTab = ref('all')
const searchQuery = ref('')
const selectedBills = ref([])

// Payment Modal State
const showPayModal = ref(false)
const activeBill = ref(null)
const payAmount = ref(0)
const payDiscount = ref(0)
const payMethod = ref('Cash')
const payDate = ref('2083/05/10')
const payRemarks = ref('')

// Generate Modal State
const showGenModal = ref(false)
const enrollments = ref([])
const selectedEnrollmentIds = ref([])
const startMonth = ref('2083/05')
const endMonth = ref('2083/05')

// Bill Payments List Modal & Admin Deletion State
const showPaymentsModal = ref(false)
const activeBillPayments = ref([])
const loadingPayments = ref(false)
const deletingPaymentId = ref(null)
const deletingBillId = ref(null)

// Payment Records Tab State
const paymentRecords = ref([])
const loadingPaymentRecords = ref(false)

onMounted(async () => {
  await loadBills()
})

async function loadBills() {
  loading.value = true
  try {
    const data = await api('/due-bills')
    bills.value = data.bills || data || []
  } catch (err) {
    console.error(err)
  } finally {
    loading.value = false
  }
}

const filteredBills = computed(() => {
  return bills.value.filter(b => {
    if (filterTab.value === 'due') {
      if (b.status === 'Paid' || b.balance <= 0) return false
    } else if (filterTab.value === 'paid') {
      if (b.status !== 'Paid' && b.balance > 0) return false
    }
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      return (
        (b.student_name && b.student_name.toLowerCase().includes(q)) ||
        (b.bill_number && b.bill_number.toLowerCase().includes(q)) ||
        (b.course_name && b.course_name.toLowerCase().includes(q)) ||
        (b.class_name && b.class_name.toLowerCase().includes(q))
      )
    }
    return true
  })
})

const stats = computed(() => {
  const totalBilled = bills.value.reduce((acc, b) => acc + (Number(b.total_amount) || 0), 0)
  const totalDue = bills.value.reduce((acc, b) => acc + (Number(b.balance) || 0), 0)
  const totalPaid = bills.value.reduce((acc, b) => acc + (Number(b.paid_amount) || 0), 0)
  return { totalBilled, totalDue, totalPaid }
})

function openPayment(bill) {
  activeBill.value = bill
  payAmount.value = bill.balance || bill.total_amount
  payDiscount.value = 0
  showPayModal.value = true
}

async function submitPayment() {
  if (!activeBill.value) return
  try {
    await api(`/due-bills/${activeBill.value.id}/payments`, {
      method: 'POST',
      body: JSON.stringify({
        amount: Number(payAmount.value),
        discount: Number(payDiscount.value),
        payment_method: payMethod.value,
        payment_date: payDate.value,
        remarks: payRemarks.value
      })
    })
    alert('Payment recorded successfully!')
    showPayModal.value = false
    await loadBills()
  } catch (err) {
    alert('Payment failed: ' + err.message)
  }
}

async function openGenerateModal() {
  try {
    const data = await api('/enrollments')
    enrollments.value = data.filter(e => e.status === 'Active')
    showGenModal.value = true
  } catch (err) {
    alert('Could not load enrollments: ' + err.message)
  }
}

async function submitGenerate() {
  if (!selectedEnrollmentIds.value.length) {
    alert('Please select at least one enrollment.')
    return
  }
  try {
    const res = await api('/bills/generate', {
      method: 'POST',
      body: JSON.stringify({
        enrollment_ids: selectedEnrollmentIds.value,
        start_month: startMonth.value,
        end_month: endMonth.value,
        issue_date: '2083/05/10',
        due_date: '2083/05/15'
      })
    })
    alert(`Generated ${res.created || 1} bill(s) successfully!`)
    showGenModal.value = false
    await loadBills()
  } catch (err) {
    alert('Generation error: ' + err.message)
  }
}

function setFilterTab(tab) {
  filterTab.value = tab
  if (tab === 'payments') {
    loadPaymentRecords()
  }
}

async function loadPaymentRecords() {
  loadingPaymentRecords.value = true
  try {
    const data = await api('/student-payments')
    paymentRecords.value = data.payments || []
  } catch (err) {
    console.error('Failed to load payment records:', err)
  } finally {
    loadingPaymentRecords.value = false
  }
}

const filteredPaymentRecords = computed(() => {
  if (!searchQuery.value) return paymentRecords.value
  const q = searchQuery.value.toLowerCase()
  return paymentRecords.value.filter(p => {
    return (
      (p.student_name && p.student_name.toLowerCase().includes(q)) ||
      (p.receipt_no && p.receipt_no.toLowerCase().includes(q)) ||
      (p.particular && p.particular.toLowerCase().includes(q)) ||
      (p.account_name && p.account_name.toLowerCase().includes(q)) ||
      (p.payment_method && p.payment_method.toLowerCase().includes(q))
    )
  })
})

async function openPaymentsModal(bill) {
  activeBill.value = bill
  showPaymentsModal.value = true
  await loadPaymentsForBill(bill.id)
}

async function loadPaymentsForBill(billId) {
  loadingPayments.value = true
  try {
    const res = await api(`/due-bills/${billId}/payments`)
    activeBillPayments.value = res.payments || []
  } catch (err) {
    console.error('Failed to load bill payments:', err)
    activeBillPayments.value = []
  } finally {
    loadingPayments.value = false
  }
}

async function deletePayment(payment, bill = null) {
  if (!authStore.isAdmin) {
    alert('Access Denied: Only administrators are authorized to delete payment records.')
    return
  }

  const targetBillId = bill?.id || activeBill.value?.id || 0
  const confirmMsg = 
    `⚠️ ADMINISTRATOR PAYMENT DELETION\n\n` +
    `Are you sure you want to permanently delete Payment #${payment.id}?\n\n` +
    `• Student: ${payment.student_name || activeBill.value?.student_name || 'Student'}\n` +
    `• Paid Amount: Rs. ${Number(payment.payment_amount || 0).toLocaleString()}\n` +
    `• Discount: Rs. ${Number(payment.discount_amount || 0).toLocaleString()}\n` +
    `• Receipt #: ${payment.receipt_no || '—'}\n` +
    `• Particular: ${payment.particular || 'Bill Payment'}\n\n` +
    `This action will automatically:\n` +
    `1. Revert paid amount & discount on associated due bills.\n` +
    `2. Reverse matching General Ledger entries and decrement account balances.\n` +
    `3. Restore student due balances.\n` +
    `4. Clean up SMS logs and log an administrative audit entry.\n\n` +
    `Proceed with deletion?`

  if (!confirm(confirmMsg)) return

  deletingPaymentId.value = payment.id
  try {
    const endpoint = targetBillId 
      ? `/due-bills/${targetBillId}/payments/${payment.id}` 
      : `/student-transactions/${payment.id}`
    const res = await api(endpoint, { method: 'DELETE' })
    alert(res.message || 'Payment record deleted successfully and ledger reversed.')

    await loadBills()
    if (showPaymentsModal.value && activeBill.value) {
      const updated = bills.value.find(b => b.id === activeBill.value.id)
      if (updated) {
        activeBill.value = updated
      }
      await loadPaymentsForBill(activeBill.value.id)
    }
    if (filterTab.value === 'payments') {
      await loadPaymentRecords()
    }
  } catch (err) {
    alert('Failed to delete payment: ' + err.message)
  } finally {
    deletingPaymentId.value = null
  }
}

async function deleteBill(bill) {
  if (!authStore.isAdmin) {
    alert('Access Denied: Only administrators are authorized to delete bills.')
    return
  }

  const isPaid = Number(bill.paid_amount || 0) > 0
  let confirmMsg = ''
  if (isPaid) {
    confirmMsg = 
      `⚠️ ADMINISTRATOR ACTION: DELETE PAID BILL\n\n` +
      `Are you sure you want to permanently delete Bill #${bill.bill_number} for ${bill.student_name}?\n\n` +
      `• Total Invoiced: Rs. ${Number(bill.total_amount || 0).toLocaleString()}\n` +
      `• Recorded Payments: Rs. ${Number(bill.paid_amount || 0).toLocaleString()}\n` +
      `• Billing Period: ${bill.billing_period || 'N/A'}\n\n` +
      `This operation will automatically:\n` +
      `1. Permanently delete the bill and its line items\n` +
      `2. Reverse and remove all associated student payment records\n` +
      `3. Reverse corresponding General Ledger entries and adjust account balances\n` +
      `4. Reconcile student accounts in FIFO chronological order\n` +
      `5. Log an administrative audit record\n\n` +
      `Proceed with deleting this PAID bill?`
  } else {
    confirmMsg = `Are you sure you want to permanently delete unpaid Bill #${bill.bill_number} for ${bill.student_name}?`
  }

  if (!confirm(confirmMsg)) return

  deletingBillId.value = bill.id
  try {
    const res = await api(`/due-bills/${bill.id}`, { method: 'DELETE' })
    alert(res.message || `Bill #${bill.bill_number} deleted successfully.`)
    await loadBills()
    if (filterTab.value === 'payments') {
      await loadPaymentRecords()
    }
  } catch (err) {
    alert('Failed to delete bill: ' + err.message)
  } finally {
    deletingBillId.value = null
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h2 class="text-2xl font-black text-slate-900">Student Due Bills & Billing</h2>
        <p class="text-sm text-slate-500">Monthly billing cycles, invoices, payments, and print receipts</p>
      </div>
      <div class="flex items-center gap-2">
        <button 
          @click="openGenerateModal"
          class="inline-flex items-center gap-2 px-3.5 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold rounded-lg shadow-sm"
        >
          <Plus class="w-4 h-4" /> Generate Due Bills
        </button>
      </div>
    </div>

    <!-- Stat Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex justify-between items-center">
        <div>
          <p class="text-xs font-bold text-slate-400 uppercase">Total Invoiced</p>
          <p class="text-xl font-black text-slate-900 mt-1">Rs. {{ stats.totalBilled.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-slate-100 text-slate-600 rounded-xl">
          <Receipt class="w-5 h-5" />
        </div>
      </div>
      <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex justify-between items-center">
        <div>
          <p class="text-xs font-bold text-emerald-600 uppercase">Total Collected</p>
          <p class="text-xl font-black text-emerald-700 mt-1">Rs. {{ stats.totalPaid.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-emerald-50 text-emerald-600 rounded-xl">
          <CheckCircle2 class="w-5 h-5" />
        </div>
      </div>
      <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex justify-between items-center">
        <div>
          <p class="text-xs font-bold text-rose-600 uppercase">Outstanding Dues</p>
          <p class="text-xl font-black text-rose-700 mt-1">Rs. {{ stats.totalDue.toLocaleString() }}</p>
        </div>
        <div class="p-3 bg-rose-50 text-rose-600 rounded-xl">
          <AlertCircle class="w-5 h-5" />
        </div>
      </div>
    </div>

    <!-- Filter Tabs & Search -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="p-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div class="flex items-center gap-2">
          <button 
            @click="setFilterTab('all')"
            :class="[filterTab === 'all' ? 'bg-slate-900 text-white font-bold' : 'text-slate-600 hover:bg-slate-100', 'px-3 py-1.5 rounded-lg text-xs font-medium']"
          >
            All Bills ({{ bills.length }})
          </button>
          <button 
            @click="setFilterTab('due')"
            :class="[filterTab === 'due' ? 'bg-amber-600 text-white font-bold' : 'text-slate-600 hover:bg-slate-100', 'px-3 py-1.5 rounded-lg text-xs font-medium']"
          >
            ⚠️ Due / Overdue
          </button>
          <button 
            @click="setFilterTab('paid')"
            :class="[filterTab === 'paid' ? 'bg-emerald-600 text-white font-bold' : 'text-slate-600 hover:bg-slate-100', 'px-3 py-1.5 rounded-lg text-xs font-medium']"
          >
            ✓ Settled
          </button>
          <button 
            @click="setFilterTab('payments')"
            :class="[filterTab === 'payments' ? 'bg-sky-600 text-white font-bold' : 'text-slate-600 hover:bg-slate-100', 'px-3 py-1.5 rounded-lg text-xs font-medium']"
          >
            💳 Payment Records
          </button>
        </div>

        <div class="relative w-full sm:w-72 flex items-center">
          <Search class="w-4 h-4 text-slate-400 absolute left-3 pointer-events-none z-10" />
          <input 
            type="text" 
            v-model="searchQuery" 
            :placeholder="filterTab === 'payments' ? 'Search payment, student, receipt...' : 'Search student, bill #...'" 
            class="w-full pr-4 py-1.5 border border-slate-200 rounded-lg text-xs focus:outline-none focus:border-sky-500"
            style="padding-left: 2.5rem !important;"
          />
        </div>
      </div>

      <!-- Payment Records View (when filterTab === 'payments') -->
      <table v-if="filterTab === 'payments'" class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3.5">Date</th>
            <th class="px-5 py-3.5">Receipt #</th>
            <th class="px-5 py-3.5">Student</th>
            <th class="px-5 py-3.5">Particulars</th>
            <th class="px-5 py-3.5">Method</th>
            <th class="px-5 py-3.5">Account</th>
            <th class="px-5 py-3.5">Paid Amount</th>
            <th class="px-5 py-3.5">Discount</th>
            <th class="px-5 py-3.5 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="loadingPaymentRecords">
            <td colspan="9" class="px-5 py-8 text-center text-slate-400">Loading payment records...</td>
          </tr>
          <tr v-else-if="!filteredPaymentRecords.length">
            <td colspan="9" class="px-5 py-8 text-center text-slate-400">No payment records found.</td>
          </tr>
          <tr v-for="p in filteredPaymentRecords" :key="p.id" class="hover:bg-slate-50">
            <td class="px-5 py-3.5 font-mono text-xs text-slate-700">{{ p.transaction_date }}</td>
            <td class="px-5 py-3.5 font-mono text-xs font-bold text-slate-800">{{ p.receipt_no || '—' }}</td>
            <td class="px-5 py-3.5 font-bold text-slate-900">
              {{ p.student_name }}
              <span v-if="p.class_name" class="ml-1 text-[11px] font-normal text-slate-500">({{ p.class_name }})</span>
            </td>
            <td class="px-5 py-3.5 text-xs text-slate-600">{{ p.particular }}</td>
            <td class="px-5 py-3.5 text-xs text-slate-700">{{ p.payment_method || 'Cash' }}</td>
            <td class="px-5 py-3.5 text-xs text-slate-500">{{ p.account_name || '—' }}</td>
            <td class="px-5 py-3.5 font-bold text-emerald-700">Rs. {{ Number(p.payment_amount || 0).toLocaleString() }}</td>
            <td class="px-5 py-3.5 text-xs font-semibold text-amber-700">
              {{ Number(p.discount_amount) > 0 ? `Rs. ${Number(p.discount_amount).toLocaleString()}` : '—' }}
            </td>
            <td class="px-5 py-3.5 text-right">
              <button 
                v-if="authStore.isAdmin"
                @click="deletePayment(p)"
                :disabled="deletingPaymentId === p.id"
                class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-md shadow-sm disabled:opacity-50"
                title="Delete Payment Record (Administrator Only)"
              >
                <Trash2 class="w-3.5 h-3.5" />
                {{ deletingPaymentId === p.id ? 'Deleting...' : 'Delete' }}
              </button>
              <span v-else class="text-xs text-slate-400 italic">Admin Only</span>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Due Bills View (when filterTab !== 'payments') -->
      <table v-else class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase">
          <tr>
            <th class="px-5 py-3.5">Bill #</th>
            <th class="px-5 py-3.5">Student</th>
            <th class="px-5 py-3.5">Class</th>
            <th class="px-5 py-3.5">Course / Month</th>
            <th class="px-5 py-3.5">Total</th>
            <th class="px-5 py-3.5">Due Balance</th>
            <th class="px-5 py-3.5">Status</th>
            <th class="px-5 py-3.5 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <TableSkeleton v-if="loading" :cols="8" :rows="7" :colWidths="['w-16', 'w-36', 'w-20', 'w-32', 'w-24', 'w-24', 'w-16', 'w-20']" />
          <tr v-else-if="!filteredBills.length">
            <td colspan="8" class="px-5 py-8 text-center text-slate-400">No bills matching filter.</td>
          </tr>
          <tr v-for="b in filteredBills" :key="b.id" class="hover:bg-slate-50">
            <td class="px-5 py-3.5 font-mono text-xs font-bold text-slate-800">{{ b.bill_number }}</td>
            <td class="px-5 py-3.5 font-bold text-slate-900">{{ b.student_name }}</td>
            <td class="px-5 py-3.5 text-xs text-slate-600">
              <span v-if="b.class_name" class="inline-flex px-1.5 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">
                {{ b.class_name }}
              </span>
              <span v-else class="text-slate-400">—</span>
            </td>
            <td class="px-5 py-3.5 text-slate-600 text-xs">{{ b.course_name }} ({{ b.billing_period }})</td>
            <td class="px-5 py-3.5 font-semibold text-slate-800">Rs. {{ Number(b.total_amount || 0).toLocaleString() }}</td>
            <td class="px-5 py-3.5 font-bold text-rose-600">Rs. {{ Number(b.balance || 0).toLocaleString() }}</td>
            <td class="px-5 py-3.5">
              <span 
                :class="[
                  b.status === 'Paid' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-rose-50 text-rose-700 border-rose-200',
                  'inline-flex px-2 py-0.5 rounded text-[11px] font-bold border'
                ]"
              >
                {{ b.status }}
              </span>
            </td>
            <td class="px-5 py-3.5 text-right space-x-1.5">
              <button 
                v-if="b.balance > 0"
                @click="openPayment(b)"
                class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-md shadow-sm"
              >
                <CreditCard class="w-3.5 h-3.5" /> Pay
              </button>
              <button 
                v-if="Number(b.paid_amount) > 0"
                @click="openPaymentsModal(b)"
                class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-sky-700 bg-sky-50 hover:bg-sky-100 rounded-md border border-sky-200"
                title="View payments & delete if administrator"
              >
                <History class="w-3.5 h-3.5" /> Payments
              </button>
              <a 
                :href="`/due-bills/${b.id}/pdf`" 
                target="_blank"
                class="inline-flex items-center gap-1 px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-md border border-slate-200"
              >
                <FileText class="w-3.5 h-3.5" /> PDF
              </a>
              <button 
                v-if="authStore.isAdmin"
                @click="deleteBill(b)"
                :disabled="deletingBillId === b.id"
                class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold text-rose-700 bg-rose-50 hover:bg-rose-100 rounded-md border border-rose-200 disabled:opacity-50"
                :title="Number(b.paid_amount) > 0 ? 'Delete Paid Bill & Revert Payments (Admin Only)' : 'Delete Unpaid Bill (Admin Only)'"
              >
                <Trash2 class="w-3.5 h-3.5" />
                {{ deletingBillId === b.id ? 'Deleting...' : 'Delete' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Receive Payment Modal -->
    <div v-if="showPayModal" class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100">
        <h3 class="text-lg font-bold text-slate-900">Receive Bill Payment</h3>
        <p class="text-xs text-slate-500 mt-1 mb-4">
          Student: <b>{{ activeBill?.student_name }}</b> <span v-if="activeBill?.class_name" class="font-semibold text-slate-700">({{ activeBill?.class_name }})</span> (Bill: {{ activeBill?.bill_number }})
        </p>

        <form @submit.prevent="submitPayment" class="space-y-3.5">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Amount to Pay (Rs.) *</label>
            <input type="number" step="0.01" v-model="payAmount" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-bold text-emerald-700" />
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Discount (Rs.)</label>
            <input type="number" step="0.01" v-model="payDiscount" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Payment Method</label>
              <select v-model="payMethod" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm">
                <option>Cash</option>
                <option>Bank</option>
                <option>Wallet</option>
                <option>Other</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Date (BS)</label>
              <input type="text" v-model="payDate" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Remarks</label>
            <input type="text" v-model="payRemarks" placeholder="Transaction ref / notes" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
          </div>

          <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
            <button type="button" @click="showPayModal = false" class="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
            <button type="submit" class="px-4 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-sm">Save Payment</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Generate Bill Modal -->
    <div v-if="showGenModal" class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100">
        <h3 class="text-lg font-bold text-slate-900">Generate Due Bills</h3>
        <p class="text-xs text-slate-500 mt-1 mb-4">Select active student enrollments to issue billing cycles:</p>

        <form @submit.prevent="submitGenerate" class="space-y-3.5">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Select Enrollments *</label>
            <select multiple size="6" v-model="selectedEnrollmentIds" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs">
              <option v-for="e in enrollments" :key="e.id" :value="e.id">
                {{ e.student_name }} — {{ e.course_name }} ({{ e.level || 'Standard' }})
              </option>
            </select>
            <small class="text-slate-400 text-[11px]">Hold Ctrl or Shift to select multiple students.</small>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Start Month (BS) *</label>
              <input type="text" v-model="startMonth" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">End Month (BS) *</label>
              <input type="text" v-model="endMonth" required class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" />
            </div>
          </div>

          <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
            <button type="button" @click="showGenModal = false" class="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
            <button type="submit" class="px-4 py-2 text-xs font-bold text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-sm">Generate Bills</button>
          </div>
        </form>
      </div>
    </div>

    <!-- View Bill Payments Modal -->
    <div v-if="showPaymentsModal" class="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-100 flex flex-col max-h-[90vh]">
        <div class="flex items-center justify-between pb-3 border-b border-slate-100">
          <div>
            <h3 class="text-lg font-bold text-slate-900 flex items-center gap-2">
              <History class="w-5 h-5 text-sky-600" />
              Bill Payment Records
            </h3>
            <p class="text-xs text-slate-500 mt-0.5">
              Bill: <span class="font-mono font-bold text-slate-800">{{ activeBill?.bill_number }}</span> • 
              Student: <span class="font-bold text-slate-800">{{ activeBill?.student_name }}</span>
            </p>
          </div>
          <div class="flex items-center gap-2">
            <span v-if="authStore.isAdmin" class="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200">
              <ShieldCheck class="w-3.5 h-3.5 text-amber-600" /> Administrator Mode
            </span>
            <span v-else class="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold bg-slate-50 text-slate-500 border border-slate-200">
              <ShieldAlert class="w-3.5 h-3.5 text-slate-400" /> View Only
            </span>
          </div>
        </div>

        <!-- Bill Financial Summary Bar -->
        <div class="grid grid-cols-4 gap-2 my-3 p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs text-center">
          <div>
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Total Invoiced</span>
            <span class="font-bold text-slate-800">Rs. {{ Number(activeBill?.total_amount || 0).toLocaleString() }}</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Discount</span>
            <span class="font-bold text-amber-700">Rs. {{ Number(activeBill?.discount || 0).toLocaleString() }}</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Total Paid</span>
            <span class="font-bold text-emerald-700">Rs. {{ Number(activeBill?.paid_amount || 0).toLocaleString() }}</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[10px] uppercase font-bold">Balance Due</span>
            <span class="font-bold text-rose-700">Rs. {{ Number(activeBill?.balance || 0).toLocaleString() }}</span>
          </div>
        </div>

        <!-- Payment History Table -->
        <div class="overflow-y-auto flex-1 border border-slate-200 rounded-xl">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-600 uppercase sticky top-0">
              <tr>
                <th class="px-3 py-2.5">Date</th>
                <th class="px-3 py-2.5">Receipt #</th>
                <th class="px-3 py-2.5">Method</th>
                <th class="px-3 py-2.5">Amount</th>
                <th class="px-3 py-2.5">Discount</th>
                <th class="px-3 py-2.5">Account</th>
                <th class="px-3 py-2.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-if="loadingPayments">
                <td colspan="7" class="px-4 py-8 text-center text-slate-400">Loading payments...</td>
              </tr>
              <tr v-else-if="!activeBillPayments.length">
                <td colspan="7" class="px-4 py-8 text-center text-slate-400">No payment records found for this bill.</td>
              </tr>
              <tr v-for="p in activeBillPayments" :key="p.id" class="hover:bg-slate-50">
                <td class="px-3 py-2.5 font-mono text-slate-700">{{ p.transaction_date }}</td>
                <td class="px-3 py-2.5 font-mono font-semibold text-slate-800">{{ p.receipt_no || '—' }}</td>
                <td class="px-3 py-2.5 text-slate-600">{{ p.payment_method || 'Cash' }}</td>
                <td class="px-3 py-2.5 font-bold text-emerald-700">Rs. {{ Number(p.payment_amount || 0).toLocaleString() }}</td>
                <td class="px-3 py-2.5 text-amber-700 font-semibold">{{ Number(p.discount_amount) > 0 ? `Rs. ${Number(p.discount_amount).toLocaleString()}` : '—' }}</td>
                <td class="px-3 py-2.5 text-slate-500">{{ p.account_name || '—' }}</td>
                <td class="px-3 py-2.5 text-right">
                  <button 
                    v-if="authStore.isAdmin"
                    @click="deletePayment(p, activeBill)"
                    :disabled="deletingPaymentId === p.id"
                    class="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-bold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded disabled:opacity-50"
                    title="Delete Payment (Administrator only)"
                  >
                    <Trash2 class="w-3 h-3" />
                    {{ deletingPaymentId === p.id ? 'Deleting...' : 'Delete' }}
                  </button>
                  <span v-else class="text-[11px] text-slate-400 italic">Protected</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="flex items-center justify-between pt-3 mt-3 border-t border-slate-100">
          <p class="text-[11px] text-slate-400">
            * Deleting a payment rolls back bill paid totals, reverses ledger entries, and logs an administrative audit record.
          </p>
          <button 
            type="button" 
            @click="showPaymentsModal = false" 
            class="px-4 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg border border-slate-200"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
