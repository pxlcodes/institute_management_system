import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/', component: () => import('@/views/DashboardView.vue') },
  { path: '/routines', component: () => import('@/views/RoutineView.vue') },
  { path: '/calendar', component: () => import('@/views/CalendarView.vue') },
  { path: '/students', component: () => import('@/views/StudentsView.vue') },
  { path: '/enrollments', component: () => import('@/views/EnrollmentsView.vue') },
  { path: '/bills', component: () => import('@/views/BillsView.vue') },
  { path: '/attendance', component: () => import('@/views/AttendanceView.vue') },
  { path: '/staff', component: () => import('@/views/StaffView.vue') },
  { path: '/accounts', component: () => import('@/views/AccountsView.vue') },
  { path: '/certificates', component: () => import('@/views/CertificatesView.vue') },
  { path: '/master-data', component: () => import('@/views/MasterDataView.vue') },
  { path: '/settings', component: () => import('@/views/SettingsView.vue') },
  { path: '/login', component: () => import('@/views/LoginView.vue'), meta: { public: true } }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  if (!to.meta.public && !authStore.isAuthenticated) {
    next('/login')
  } else {
    next()
  }
})

export default router
