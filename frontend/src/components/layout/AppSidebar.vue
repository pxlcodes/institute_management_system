<script setup>
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import PwaInstallPrompt from '@/components/PwaInstallPrompt.vue'
import { 
  LayoutDashboard, 
  Clock, 
  CalendarDays, 
  Users, 
  GraduationCap, 
  Receipt, 
  UserCheck, 
  Briefcase, 
  Landmark, 
  Award, 
  Layers, 
  Settings, 
  LogOut,
  X
} from 'lucide-vue-next'

const props = defineProps({
  mobileOpen: { type: Boolean, default: false }
})
const emit = defineEmits(['close-mobile'])

const route = useRoute()
const authStore = useAuthStore()

const navigation = [
  { name: 'Dashboard', path: '/', icon: LayoutDashboard },
  { name: 'Class Routine', path: '/routines', icon: Clock },
  { name: 'Calendar (BS)', path: '/calendar', icon: CalendarDays },
  { name: 'Students', path: '/students', icon: Users },
  { name: 'Enrollments', path: '/enrollments', icon: GraduationCap },
  { name: 'Due Bills & Fees', path: '/bills', icon: Receipt },
  { name: 'Daily Attendance', path: '/attendance', icon: UserCheck },
  { name: 'Staff & Payroll', path: '/staff', icon: Briefcase },
  { name: 'Accounts & Ledgers', path: '/accounts', icon: Landmark },
  { name: 'Certificates', path: '/certificates', icon: Award },
  { name: 'Master Data', path: '/master-data', icon: Layers },
  { name: 'System Settings', path: '/settings', icon: Settings },
]

function isActive(path) {
  return route.path === path
}

function handleNavClick() {
  emit('close-mobile')
}
</script>

<template>
  <div>
    <!-- Mobile Backdrop -->
    <div 
      v-if="mobileOpen" 
      @click="emit('close-mobile')"
      class="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
    ></div>

    <!-- Sidebar Element -->
    <aside 
      :class="[
        mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        'fixed lg:static top-0 left-0 bottom-0 w-64 bg-slate-900 text-slate-300 flex flex-col shrink-0 min-h-screen border-r border-slate-800 z-50 transition-transform duration-300 ease-in-out'
      ]"
    >
      <div class="h-16 flex items-center justify-between px-6 border-b border-slate-800">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-lg bg-sky-500 flex items-center justify-center text-white font-black text-lg shadow-sm">
            E
          </div>
          <div>
            <h1 class="text-sm font-bold text-white tracking-wide">ELH Academy</h1>
            <p class="text-[11px] text-slate-400">Management System</p>
          </div>
        </div>
        <button 
          @click="emit('close-mobile')" 
          class="p-1 text-slate-400 hover:text-white lg:hidden"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Navigation Links -->
      <nav class="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        <router-link
          v-for="item in navigation"
          :key="item.name"
          :to="item.path"
          @click="handleNavClick"
          :class="[
            isActive(item.path) 
              ? 'bg-sky-600 text-white font-semibold shadow-sm' 
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200',
            'flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-colors'
          ]"
        >
          <component :is="item.icon" class="w-4 h-4 shrink-0" />
          <span>{{ item.name }}</span>
        </router-link>
      </nav>

      <!-- PWA Install Prompt in Sidebar -->
      <div class="p-3 border-t border-slate-800/80 bg-slate-950/20">
        <PwaInstallPrompt />
      </div>

      <!-- User Session Footer -->
      <div class="p-4 border-t border-slate-800 bg-slate-950/40">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs font-bold text-white">{{ authStore.username || 'Administrator' }}</div>
            <div class="text-[11px] text-slate-400 capitalize">{{ authStore.role || 'Super Admin' }}</div>
          </div>
          <button 
            @click="authStore.logout()"
            title="Sign out"
            class="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-800 rounded-md transition-colors"
          >
            <LogOut class="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  </div>
</template>
