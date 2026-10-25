<script setup lang="ts">
import { useScreeningStore } from '../stores/screening'

const store = useScreeningStore()
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <div v-for="toast in store.toasts" :key="toast.id" class="toast">{{ toast.message }}</div>
  </div>
</template>
