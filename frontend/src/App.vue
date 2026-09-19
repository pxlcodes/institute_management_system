<script setup>
import { onMounted } from 'vue'
import { initElhEngine } from '@/core/elhEngine'
import FloatingAssistant from '@/components/FloatingAssistant.vue'

onMounted(() => {
  initElhEngine()
})
</script>

<template>
  <div id="elh-viewport"></div>
  <FloatingAssistant />
</template>

<style>
#elh-viewport {
  width: 100%;
  min-height: 100vh;
}
</style>
