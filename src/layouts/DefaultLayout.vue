<script setup>
const title = import.meta.env.VITE_APP_TITLE || 'ConvertTo3D'
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <RouterLink to="/" class="brand">{{ title }}</RouterLink>
      <span>Vue 3 · JavaScript · Vite</span>
    </header>
    <main><RouterView /></main>
  </div>
</template>
